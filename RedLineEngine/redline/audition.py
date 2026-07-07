"""Neural Monitor (Live Audition): plays short before/after chunks through
the real audio hardware via sounddevice/PortAudio, so a user can actually
hear what a DSP stage did instead of only reading numbers. Deliberately
kept free of any pywebview/UI concerns -- this module only knows how to
turn a numpy array into sound safely; app/api.py owns when to call it and
how to reflect state back to the GUI."""

from __future__ import annotations

import numpy as np
import sounddevice as sd

from redline.logging_setup import get_logger
from redline import config

logger = get_logger(__name__)


TARGET_PEAK = 0.85  # -1.4dBFS — loud enough to hear over desktop speakers,
                     # but leaves headroom so a DSP spike can't clip.


class AudioDriver:
    def __init__(self) -> None:
        # WASAPI would be lower-latency, but on many Windows systems it
        # only supports 48000 Hz while the engine may produce 44100 Hz
        # audio — the resulting "Invalid sample rate" error silences the
        # Neural Monitor entirely. Stick with the system default (MME),
        # which handles sample rate conversion transparently.
        pass

    def play_chunk(self, audio_array: np.ndarray, sr: int, fade_ms: float = 50) -> None:
        """Blocking playback with anti-click safety: peak-normalizes so a
        DSP bug can never blast the user's speakers, and fades the edges
        in/out so a hard cut doesn't produce an audible pop. Also applies a
        gentle makeup gain so quiet signals (e.g. a -18dBFS mix) are audible
        without requiring the user to max out their system volume."""
        if audio_array is None or len(audio_array) == 0:
            return

        audio_array = np.array(audio_array, dtype=np.float32, copy=True)

        peak = np.max(np.abs(audio_array))
        if peak > 1.0:
            # Safety clamp: a DSP bug must never blast the speakers.
            audio_array = audio_array / peak
        elif peak > 0.0 and peak < TARGET_PEAK:
            # Makeup gain: quiet signals (typical mix at -18dBFS) are boosted
            # to a comfortable listening level so the user can actually hear
            # the A/B comparison without cranking their system volume.
            gain = TARGET_PEAK / peak
            audio_array = audio_array * gain

        fade_samples = int((fade_ms / 1000.0) * sr)
        if len(audio_array) > fade_samples * 2 > 0:
            fade_in = np.linspace(0.0, 1.0, fade_samples, dtype=np.float32)
            fade_out = np.linspace(1.0, 0.0, fade_samples, dtype=np.float32)
            if audio_array.ndim == 1:
                audio_array[:fade_samples] *= fade_in
                audio_array[-fade_samples:] *= fade_out
            else:
                for ch in range(audio_array.shape[1]):
                    audio_array[:fade_samples, ch] *= fade_in
                    audio_array[-fade_samples:, ch] *= fade_out

        # channels was missing entirely -- PortAudio needs to be told how many
        # output channels to open (1 for mono, 2 for stereo) or it silently
        # opens a stream that doesn't match the array shape and produces no
        # audible output at all, with no exception raised. Also drop the
        # explicit `device=sd.default.device` -- passing that tuple back in
        # as `device` is redundant (omitting it already selects the system
        # default) and was one more way this call could mismatch.
        channels = 1 if audio_array.ndim == 1 else audio_array.shape[1]
        if audio_array.ndim > 1 and not audio_array.flags['C_CONTIGUOUS']:
            audio_array = np.ascontiguousarray(audio_array)

        try:
            with sd.OutputStream(
                samplerate=sr,
                channels=channels,
                blocksize=512,
                latency='low',
            ) as stream:
                stream.write(audio_array)
        except Exception as exc:
            # A missing/busy audio device must never take down the render --
            # audition is a nice-to-have, not a pipeline dependency.
            logger.exception("Audio playback failed — missing or busy device")


def extract_smart_chunk(audio_array: np.ndarray, sr: int, duration_sec: float = 2.0) -> np.ndarray:
    """Finds the `duration_sec`-long window with the highest RMS energy
    (the loudest/densest moment, usually the chorus/hook) instead of just
    grabbing the first N seconds -- comparing a compressor's effect on
    near-silence would show nothing useful."""
    chunk_samples = int(duration_sec * sr)
    if len(audio_array) <= chunk_samples:
        return audio_array

    hop_length = sr  # scan in 1-second steps -- coarse but fast enough for a UI-triggered scan
    max_rms = -1.0
    best_start = 0
    for start in range(0, len(audio_array) - chunk_samples, hop_length):
        window = audio_array[start : start + chunk_samples]
        rms = float(np.sqrt(np.mean(window.astype(np.float64) ** 2)))
        if rms > max_rms:
            max_rms = rms
            best_start = start

    return audio_array[best_start : best_start + chunk_samples]


def _estimate_lag_samples(probe: np.ndarray, recording: np.ndarray) -> int | None:
    """Pure correlation logic, kept separate from the hardware I/O so it can
    be unit-tested with synthetic signals -- no speakers/mic required.
    Returns None if the recording doesn't contain a plausible echo of the
    probe (e.g. no loopback connected, silence recorded)."""
    if recording.size == 0 or np.max(np.abs(recording)) < 1e-6:
        return None
    correlation = np.correlate(recording, probe, mode="full")
    lag = int(np.argmax(correlation)) - (len(probe) - 1)
    return lag if lag >= 0 else None


def measure_loopback_latency_ms(sr: int = 44100, duration_sec: float = 0.5) -> float | None:
    """Delay-compensated loopback: plays a short windowed tone out through
    the real output device and records it back through the input device,
    then cross-correlates to measure the actual round-trip hardware+driver
    latency (DAC + ADC + OS buffering) -- something a synthetic test can
    never measure, only real hardware can. Requires a physical loopback (a
    cable from output to input, or a mic placed near the speakers) and is
    gated behind ENABLE_LIVE_AUDITION so it only ever runs when the user has
    explicitly opted into real playback for this session -- never as part
    of an automated test run.

    Returns latency in milliseconds, or None if the flag is off, no
    loopback is connected, or the device is unavailable."""
    if not config.is_enabled("ENABLE_LIVE_AUDITION"):
        logger.warning("Loopback latency measurement skipped — ENABLE_LIVE_AUDITION is off")
        return None

    n = int(sr * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)
    window = np.hanning(n).astype(np.float32)
    probe = (0.5 * np.sin(2 * np.pi * 1000.0 * t)).astype(np.float32) * window

    try:
        recording = sd.playrec(probe, samplerate=sr, channels=1, blocking=True)
    except Exception:
        logger.exception("Loopback latency measurement failed — check device/loopback cabling")
        return None

    lag_samples = _estimate_lag_samples(probe, recording[:, 0])
    if lag_samples is None:
        logger.warning("Loopback latency measurement found no usable echo — is a loopback connected?")
        return None
    return float(lag_samples / sr * 1000.0)


driver = AudioDriver()
