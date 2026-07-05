"""Fundamental-frequency estimation, used to make the vocal high-pass filter
adaptive instead of a fixed 100Hz cut that guts a baritone/bass voice."""

from __future__ import annotations

import numpy as np
import librosa

from .loudness import to_mono


def estimate_fundamental(signal: np.ndarray, sr: int, fmin: float = 60.0, fmax: float = 500.0) -> float:
    """Median voiced f0 in Hz, or a sane default (110Hz) if nothing voiced
    is detected (silence, pure noise/percussive content)."""
    mono = to_mono(signal).astype(np.float32)
    if mono.size < sr // 4:
        return 110.0
    try:
        f0 = librosa.yin(mono, fmin=fmin, fmax=fmax, sr=sr)
    except Exception:
        return 110.0
    voiced = f0[np.isfinite(f0) & (f0 > 0)]
    if voiced.size == 0:
        return 110.0
    return float(np.median(voiced))
