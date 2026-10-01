"""Caching behaviour for loudness analysis helpers.

The Meter cache must be bit-identical (filter coefficients are deterministic
per sample rate), and the optional spectral cache must be a pure memoization
layer: default (cache=None) behaviour is unchanged."""

import numpy as np
import pyloudnorm as pyln
import pytest

from redline.analysis.loudness import integrated_lufs, spectral_band_energies


class _CountingMeterProxy:
    """Stands in for pyln.Meter and counts constructions."""

    constructions = 0

    def __init__(self, sr: int):
        _CountingMeterProxy.constructions += 1
        self._inner = _RealMeter(sr)

    def integrated_loudness(self, signal):
        return self._inner.integrated_loudness(signal)


# Captured before any monkeypatching so the proxy can delegate to the real one.
_RealMeter = pyln.Meter


def test_integrated_lufs_reuses_meter_per_sample_rate(monkeypatch):
    """Two calls at the same sr must construct exactly one Meter."""
    monkeypatch.setattr(pyln, "Meter", _CountingMeterProxy)
    _CountingMeterProxy.constructions = 0

    sr = 44100
    rng = np.random.default_rng(42)
    signal = (rng.standard_normal((sr, 2)) * 0.1).astype(np.float32)

    integrated_lufs(signal, sr)
    integrated_lufs(signal, sr)

    assert _CountingMeterProxy.constructions == 1


def test_integrated_lufs_cached_value_bit_identical():
    """Cached Meter must return the exact same value as a fresh Meter."""
    sr = 44100
    rng = np.random.default_rng(7)
    signal = (rng.standard_normal((sr, 2)) * 0.1).astype(np.float32)

    expected = float(pyln.Meter(sr).integrated_loudness(signal))
    first = integrated_lufs(signal, sr)
    second = integrated_lufs(signal, sr)

    assert first == expected
    assert second == expected


def test_spectral_band_energies_cache_matches_uncached():
    """Passing a cache dict must not change the result."""
    sr = 44100
    rng = np.random.default_rng(13)
    signal = (rng.standard_normal((sr, 2)) * 0.1).astype(np.float32)

    uncached = spectral_band_energies(signal, sr)
    cache: dict = {}
    cached = spectral_band_energies(signal, sr, cache=cache)

    assert cached == uncached
    assert cache  # something was actually stored


def test_spectral_band_energies_cache_hit_returns_identical_dict():
    """Second call with the same cache returns the memoized dict."""
    sr = 44100
    rng = np.random.default_rng(13)
    signal = (rng.standard_normal((sr, 2)) * 0.1).astype(np.float32)

    cache: dict = {}
    first = spectral_band_energies(signal, sr, cache=cache)
    second = spectral_band_energies(signal, sr, cache=cache)

    assert second is first


def test_spectral_band_energies_cache_invalidated_by_mutation():
    """In-place mutation of the signal must not serve a stale entry."""
    sr = 44100
    rng = np.random.default_rng(13)
    signal = (rng.standard_normal((sr, 2)) * 0.1).astype(np.float32)

    cache: dict = {}
    first = spectral_band_energies(signal, sr, cache=cache)
    signal *= 2.0  # same shape, same id, different content
    second = spectral_band_energies(signal, sr, cache=cache)

    assert second != first


def test_spectral_band_energies_default_none_unchanged():
    """cache=None (default) must behave exactly like the uncached call."""
    sr = 44100
    rng = np.random.default_rng(13)
    signal = (rng.standard_normal((sr, 2)) * 0.1).astype(np.float32)

    assert spectral_band_energies(signal, sr) == spectral_band_energies(signal, sr, cache=None)