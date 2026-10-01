"""Tempo (BPM) detection."""

from __future__ import annotations

import numpy as np
import librosa

from redline import config
from .loudness import to_mono

# Fast path: same tempo estimator beat_track uses internally, but at a coarser
# hop (1024 vs 512) and skipping the beat-frame decoding beat_track also does
# (we only need the global tempo). ~3x cheaper, same estimate on real material.
_FAST_HOP_LENGTH = 1024


def detect_bpm(signal: np.ndarray, sr: int) -> float:
    mono = to_mono(signal).astype(np.float32)
    if config.is_enabled("ENABLE_FAST_ANALYSIS"):
        return _detect_bpm_fast(mono, sr)
    tempo, _ = librosa.beat.beat_track(y=mono, sr=sr)
    # librosa >=0.10 returns a 0-d/1-element array instead of a scalar
    return float(np.atleast_1d(tempo)[0])


def _detect_bpm_fast(mono: np.ndarray, sr: int) -> float:
    """Cheaper global-tempo estimate: onset envelope + autocorrelation tempo at
    a coarser hop. Same estimator family as beat_track (including its
    aggregate=np.median onset envelope), so the result stays within musical
    tolerance while avoiding the beat-frame decoding."""
    onset_env = librosa.onset.onset_strength(
        y=mono, sr=sr, hop_length=_FAST_HOP_LENGTH, aggregate=np.median,
    )
    tempo = librosa.feature.rhythm.tempo(
        onset_envelope=onset_env, sr=sr, hop_length=_FAST_HOP_LENGTH, aggregate=np.mean,
    )
    return float(np.atleast_1d(tempo)[0])
