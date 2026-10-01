"""Bit-exactness equivalence tests for the accelerated lag-search kernel in
correlometer.measure_bass_phase_shift_deg.

The reference implementation below is a verbatim copy of the original
pure-Python lag loop (numpy np.dot per candidate lag, float64 throughout).
The optimized module must return EXACTLY (==) the same float64 for every
input -- not approximately, bit-for-bit -- because downstream threshold
comparisons and cached reports depend on stable numbers."""

from __future__ import annotations

import numpy as np
import pytest

from redline.correlometer import (
    _MAX_LAG_SAMPLES,
    measure_bass_phase_shift_deg,
    measure_bass_phase_shift_deg_abs,
)


def _reference_lag_loop(left: np.ndarray, right: np.ndarray) -> int:
    """Verbatim copy of the ORIGINAL lag-search loop from
    measure_bass_phase_shift_deg (pre-optimization). Do not 'fix' or
    modernize this -- its exact float behavior is the specification."""
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
    return best_lag


def _reference_phase_deg(
    signal: np.ndarray, sr: int, band_hz: tuple[float, float]
) -> float:
    """Full reference pipeline: verbatim copy of the ORIGINAL
    measure_bass_phase_shift_deg (pre-optimization) -- early-return guards,
    identical scipy bandpass calls, the lag loop, and the lag->degrees
    conversion. Do not 'fix' or modernize this -- its exact float behavior
    is the specification."""
    from scipy.signal import butter, sosfiltfilt

    if signal.ndim == 1 or signal.shape[1] < 2:
        return 0.0

    nyquist = sr / 2.0
    low = max(band_hz[0] / nyquist, 1e-6)
    high = min(band_hz[1] / nyquist, 0.999)
    sos = butter(4, [low, high], btype="band", output="sos")
    left = sosfiltfilt(sos, signal[:, 0].astype(np.float64))
    right = sosfiltfilt(sos, signal[:, 1].astype(np.float64))

    if np.max(np.abs(left)) < 1e-9 or np.max(np.abs(right)) < 1e-9:
        return 0.0

    best_lag = _reference_lag_loop(left, right)

    center_freq_hz = (band_hz[0] + band_hz[1]) / 2.0
    lag_seconds = best_lag / sr
    return float(360.0 * center_freq_hz * lag_seconds)


def _bass_tone(n=8820, sr=44100, freq=40.0):
    t = np.linspace(0, n / sr, n, endpoint=False)
    return np.sin(2 * np.pi * freq * t).astype(np.float64), sr


def _cases():
    """The required >=6 signal cases, each (name, stereo-or-mono signal, sr)."""
    sr = 44100
    rng = np.random.default_rng(20261001)
    cases = []

    # 1. L/R correlated (identical channels)
    mono, sr = _bass_tone()
    cases.append(("correlated", np.stack([mono, mono], axis=1), sr))

    # 2. L/R phase-shifted (20-sample delay on the right channel)
    mono, sr = _bass_tone(freq=40.0)
    right = np.roll(mono, 20)
    right[:20] = 0.0
    cases.append(("phase_shifted", np.stack([mono, right], axis=1), sr))

    # 3. Mono (1-D) input
    mono, sr = _bass_tone()
    cases.append(("mono_1d", mono.copy(), sr))

    # 4. Digital silence
    cases.append(("silence", np.zeros((4410, 2)), sr))

    # 5. White noise, uncorrelated channels
    noise = rng.standard_normal((22050, 2))
    cases.append(("white_noise", noise, sr))

    # 6. Very short signal (a few hundred samples)
    short = rng.standard_normal((300, 2))
    cases.append(("very_short", short, sr))

    # 7. Anti-correlated channels (worst case for the lag search)
    mono, sr = _bass_tone()
    cases.append(("anti_correlated", np.stack([mono, -mono], axis=1), sr))

    # 8. Longer full-track-sized signal with a small random offset between
    #    channels (exercises the lag window on realistic lengths)
    base = rng.standard_normal(44100)
    offset = np.roll(base, 7) + 0.01 * rng.standard_normal(44100)
    cases.append(("long_noisy_offset", np.stack([base, offset], axis=1), sr))

    return cases


@pytest.mark.parametrize("name,signal,sr", _cases(), ids=[c[0] for c in _cases()])
def test_phase_shift_matches_reference_exactly(name, signal, sr):
    expected = _reference_phase_deg(signal, sr, (20.0, 60.0))
    got = measure_bass_phase_shift_deg(signal, sr)
    assert got == expected


@pytest.mark.parametrize("name,signal,sr", _cases(), ids=[c[0] for c in _cases()])
def test_phase_shift_abs_matches_reference_exactly(name, signal, sr):
    expected = abs(_reference_phase_deg(signal, sr, (20.0, 60.0)))
    got = measure_bass_phase_shift_deg_abs(signal, sr)
    assert got == expected


def test_custom_band_matches_reference_exactly():
    sr = 48000
    rng = np.random.default_rng(7)
    base = rng.standard_normal(24000)
    right = np.roll(base, 11)
    stereo = np.stack([base, right], axis=1)
    band = (30.0, 80.0)
    expected = _reference_phase_deg(stereo, sr, band)
    got = measure_bass_phase_shift_deg(stereo, sr, band)
    assert got == expected