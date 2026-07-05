"""Tempo (BPM) detection."""

from __future__ import annotations

import numpy as np
import librosa

from .loudness import to_mono


def detect_bpm(signal: np.ndarray, sr: int) -> float:
    mono = to_mono(signal).astype(np.float32)
    tempo, _ = librosa.beat.beat_track(y=mono, sr=sr)
    # librosa >=0.10 returns a 0-d/1-element array instead of a scalar
    return float(np.atleast_1d(tempo)[0])
