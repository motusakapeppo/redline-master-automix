"""Phase-shift measurement between L/R channels in the sub-bass region.

Distinct from qc.py's `_mono_compatibility` (a broadband energy-ratio check):
this measures an actual *phase angle* below 60Hz specifically, because comb-
filtering/cancellation risk in the low end is a phase-alignment problem, not
just an energy-imbalance one -- two channels can have identical energy and
still cancel badly in mono if they're out of phase down low."""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfiltfilt

DEFAULT_BAND_HZ = (20.0, 60.0)
DEFAULT_PHASE_THRESHOLD_DEG = 5.0
_MAX_LAG_SAMPLES = 64  # generous for sub-bass wavelengths at typical sample rates


def _bandpass(signal: np.ndarray, sr: int, low_hz: float, high_hz: float) -> np.ndarray:
    nyquist = sr / 2.0
    low = max(low_hz / nyquist, 1e-6)
    high = min(high_hz / nyquist, 0.999)
    sos = butter(4, [low, high], btype="band", output="sos")
    return sosfiltfilt(sos, signal.astype(np.float64))


def measure_bass_phase_shift_deg(
    signal: np.ndarray, sr: int, band_hz: tuple[float, float] = DEFAULT_BAND_HZ
) -> float:
    """Estimates the L/R phase shift (degrees) in `band_hz` via the sample
    lag that maximizes cross-correlation, converted to a phase angle at the
    band's center frequency. Returns 0.0 for mono or silent input."""
    if signal.ndim == 1 or signal.shape[1] < 2:
        return 0.0

    left = _bandpass(signal[:, 0], sr, *band_hz)
    right = _bandpass(signal[:, 1], sr, *band_hz)

    if np.max(np.abs(left)) < 1e-9 or np.max(np.abs(right)) < 1e-9:
        return 0.0

    # Only ever care about lags within +/-_MAX_LAG_SAMPLES (sub-bass phase
    # shift is at most a handful of samples), so compute the dot product
    # directly for that small window of candidate lags instead of
    # `np.correlate(..., mode="full")`, which is O(n^2) over the *entire*
    # signal length -- on a full mastered track that's tens of billions of
    # multiply-adds to answer a question that only needs ~129 of them.
    best_lag = 0
    best_score = -np.inf
    for lag in range(-_MAX_LAG_SAMPLES, _MAX_LAG_SAMPLES + 1):
        if lag >= 0:
            a, b = left[lag:], right[: len(right) - lag if lag > 0 else None]
        else:
            a, b = left[: len(left) + lag], right[-lag:]
        n = min(len(a), len(b))
        if n == 0:
            continue
        score = float(np.dot(a[:n], b[:n]))
        if score > best_score:
            best_score = score
            best_lag = lag
    lag_samples = best_lag

    center_freq_hz = (band_hz[0] + band_hz[1]) / 2.0
    lag_seconds = lag_samples / sr
    phase_deg = 360.0 * center_freq_hz * lag_seconds
    return float(phase_deg)


def measure_bass_phase_shift_deg_abs(
    signal: np.ndarray, sr: int, band_hz: tuple[float, float] = DEFAULT_BAND_HZ
) -> float:
    """Absolute value of measure_bass_phase_shift_deg -- convenience for
    threshold comparisons where only the magnitude of the misalignment
    matters, not its sign/direction."""
    return abs(measure_bass_phase_shift_deg(signal, sr, band_hz))
