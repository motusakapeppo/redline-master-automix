"""RT60 Light: estimates a room's decay time from a reference track's own
ambience (typically a snare tail) via onset detection + linear regression,
then tunes the Room/Plate reverb buses to match it. No Demucs/stem
separation here on purpose — onset detection on the full mix is enough to
find a transient-into-decay window, and this needs to stay cheap."""

from __future__ import annotations

import numpy as np
import librosa

MIN_RT60_S = 0.15  # anything shorter reads as no real room (dead/DI signal)
MAX_RT60_S = 4.0  # anything longer is almost certainly a bad fit, not a real hall
DECAY_WINDOW_S = 0.8  # how much audio after each onset we analyze for decay
FRAME_MS = 10.0  # short-time RMS frame size for the decay envelope

# Anchors tying the bus system's room_size (0-1) to real RT60 seconds —
# taken from reverbbus.py's own defaults (Room ~0.6s, Plate ~1.8s, Hall ~3s+),
# so calibration stays consistent with what those buses already sound like.
_ROOM_SIZE_ANCHORS_RT60 = np.array([0.6, 1.8, 3.0])
_ROOM_SIZE_ANCHORS_SIZE = np.array([0.25, 0.55, 0.9])


def _decay_envelope_db(signal: np.ndarray, sr: int, frame_ms: float = FRAME_MS) -> np.ndarray:
    frame_len = max(int(sr * frame_ms / 1000.0), 1)
    n_frames = len(signal) // frame_len
    if n_frames < 2:
        return np.array([])
    trimmed = signal[: n_frames * frame_len].reshape(n_frames, frame_len)
    rms = np.sqrt(np.mean(trimmed.astype(np.float64) ** 2, axis=1) + 1e-15)
    return 20.0 * np.log10(rms + 1e-12)


def _fit_rt60_from_decay(db_envelope: np.ndarray, frame_ms: float) -> float | None:
    """Fits a line to the envelope's monotonic decay (dB vs time) and
    extrapolates the time needed to drop 60dB — the standard RT60
    definition, applied to a partial decay instead of a full 60dB drop
    (real signals never decay that far before the noise floor takes over)."""
    if len(db_envelope) < 4:
        return None
    peak_idx = int(np.argmax(db_envelope))
    decay = db_envelope[peak_idx:]
    if len(decay) < 4:
        return None

    times = np.arange(len(decay)) * (frame_ms / 1000.0)
    slope, _intercept = np.polyfit(times, decay, 1)
    if slope >= -0.5:  # not actually decaying (flat/rising) -> unusable fit
        return None

    rt60 = -60.0 / slope
    return rt60


def estimate_rt60(audio: np.ndarray, sr: int, max_onsets: int = 8) -> float | None:
    """Returns a median RT60 estimate in seconds across several detected
    onsets (usually drum hits), or None if no reliable decay could be
    measured — callers must treat None as "keep the default bus settings",
    never crash the pipeline over a bad reference track."""
    mono = audio.mean(axis=1) if audio.ndim == 2 else audio
    mono = mono.astype(np.float32)

    onset_frames = librosa.onset.onset_detect(y=mono, sr=sr, units="samples")
    if len(onset_frames) == 0:
        return None

    window_len = int(sr * DECAY_WINDOW_S)
    estimates: list[float] = []
    for onset in onset_frames[:max_onsets]:
        segment = mono[onset : onset + window_len]
        if len(segment) < window_len // 2:
            continue
        envelope = _decay_envelope_db(segment, sr)
        rt60 = _fit_rt60_from_decay(envelope, FRAME_MS)
        if rt60 is not None and MIN_RT60_S <= rt60 <= MAX_RT60_S:
            estimates.append(rt60)

    if not estimates:
        return None
    return float(np.median(estimates))


def room_size_for_rt60(rt60_seconds: float) -> float:
    """Maps a target RT60 (seconds) onto pedalboard's Reverb room_size
    (0-1) via interpolation between the bus system's own known anchor
    points, clamped so calibration can never push a bus outside a sane
    algorithmic-reverb range."""
    size = float(np.interp(rt60_seconds, _ROOM_SIZE_ANCHORS_RT60, _ROOM_SIZE_ANCHORS_SIZE))
    return float(np.clip(size, 0.05, 1.0))


def calibrate_room_plate(rt60_seconds: float) -> dict[str, float]:
    """RT60 Light only recalibrates Room and Plate (the buses meant to
    track a real space) — Hall stays fixed as the deliberately oversized
    "far away" bus, unrelated to the reference track's actual room."""
    size = room_size_for_rt60(rt60_seconds)
    # Plate conventionally reads ~3x longer than Room for the same "room_size"
    # dial in this bus system's own defaults (0.6s vs 1.8s) -- preserve that
    # ratio rather than giving both buses the identical size.
    plate_rt60 = rt60_seconds * 1.6
    plate_size = room_size_for_rt60(plate_rt60)
    return {"room": size, "plate": plate_size}
