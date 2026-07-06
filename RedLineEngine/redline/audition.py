"""Neural Monitor (Live Audition): plays short before/after chunks through
the real audio hardware via sounddevice/PortAudio, so a user can actually
hear what a DSP stage did instead of only reading numbers. Deliberately
kept free of any pywebview/UI concerns -- this module only knows how to
turn a numpy array into sound safely; app/api.py owns when to call it and
how to reflect state back to the GUI."""

from __future__ import annotations

import numpy as np
import sounddevice as sd


class AudioDriver:
    def __init__(self) -> None:
        # WASAPI is the more stable/lower-latency host API on Windows; if
        # this particular sounddevice/PortAudio build doesn't expose it,
        # fall back silently to whatever the system default already is --
        # this is a preference, not a requirement.
        try:
            sd.default.hostapi = "WASAPI"
        except (ValueError, AttributeError):
            pass

    def play_chunk(self, audio_array: np.ndarray, sr: int, fade_ms: float = 50) -> None:
        """Blocking playback with anti-click safety: peak-normalizes so a
        DSP bug can never blast the user's speakers, and fades the edges
        in/out so a hard cut doesn't produce an audible pop."""
        if audio_array is None or len(audio_array) == 0:
            return

        audio_array = np.array(audio_array, dtype=np.float32, copy=True)

        peak = np.max(np.abs(audio_array))
        if peak > 1.0:
            audio_array = audio_array / peak

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

        try:
            sd.play(audio_array, samplerate=sr)
            sd.wait()
        except Exception as exc:
            # A missing/busy audio device must never take down the render --
            # audition is a nice-to-have, not a pipeline dependency.
            print(f"[AUDITION ERROR] {exc}")
            sd.stop()


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


driver = AudioDriver()
