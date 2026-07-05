"""Transient/onset density — distinguishes genres that share crest factor and
sub-bass ratio but differ in rhythmic character (e.g. sharp, dense trap hi-hats
vs long sustained sub-bass hits)."""

from __future__ import annotations

import numpy as np
import librosa

from .loudness import to_mono


def onset_density(signal: np.ndarray, sr: int) -> float:
    """Onsets per second in the signal — a rough proxy for rhythmic density."""
    mono = to_mono(signal).astype(np.float32)
    duration_s = mono.shape[0] / float(sr)
    if duration_s < 1.0:
        return 0.0
    onsets = librosa.onset.onset_detect(y=mono, sr=sr, units="time")
    return float(len(onsets) / duration_s)
