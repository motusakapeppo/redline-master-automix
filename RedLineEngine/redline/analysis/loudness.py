"""Loudness, dynamics and spectral-balance measurements shared by both the
mixing and mastering stages, and used as inputs to genre detection."""

from __future__ import annotations

import numpy as np
import librosa
import pyloudnorm as pyln
from scipy.signal import butter, sosfiltfilt

# BPM/key/spectral-shape detection don't need broadcast-quality resolution —
# downsampling before those (comparatively expensive) analyses cuts their
# cost roughly in proportion to sr, with no meaningful effect on the result.
# LUFS is kept at the source sample rate since it feeds mastering targets.
ANALYSIS_SR = 22050

# Sub-bass -> air, matches the bands the old (broken) RuleEngine tried to use
SPECTRAL_BANDS = [
    ("sub_bass", 20.0, 60.0),
    ("bass", 60.0, 120.0),
    ("low_mid", 120.0, 400.0),
    ("mid", 400.0, 1000.0),
    ("high_mid", 1000.0, 4000.0),
    ("air", 4000.0, 20000.0),
]


def to_mono(signal: np.ndarray) -> np.ndarray:
    return signal.mean(axis=1) if signal.ndim == 2 else signal


def to_mono_downsampled(signal: np.ndarray, sr: int, target_sr: int = ANALYSIS_SR) -> tuple[np.ndarray, int]:
    """Mono mixdown resampled to a lower rate for cheaper BPM/key/spectral
    analysis. No-op if the source is already at or below target_sr."""
    mono = to_mono(signal).astype(np.float32)
    if sr <= target_sr:
        return mono, sr
    resampled = librosa.resample(mono, orig_sr=sr, target_sr=target_sr)
    return resampled, target_sr


# Meters are deterministic per sample rate (the K-weighting filter
# coefficients only depend on sr), so one instance per sr is reused across
# calls instead of being rebuilt on every measurement.
_METERS: dict[int, pyln.Meter] = {}


def integrated_lufs(signal: np.ndarray, sr: int) -> float:
    """ITU-R BS.1770-4 integrated loudness via pyloudnorm."""
    meter = _METERS.get(sr)
    if meter is None:
        meter = pyln.Meter(sr)
        _METERS[sr] = meter
    try:
        return float(meter.integrated_loudness(signal))
    except ValueError:
        # pyloudnorm raises if the signal is (near-)silent or too short
        return -70.0


def crest_factor(signal: np.ndarray) -> float:
    mono = to_mono(signal)
    rms = np.sqrt(np.mean(mono**2)) + 1e-9
    peak = np.max(np.abs(mono)) + 1e-9
    return float(peak / rms)


def spectral_band_energies(signal: np.ndarray, sr: int, *, cache: dict | None = None) -> dict[str, float]:
    """Returns each band's share of total energy (sums to ~1.0).

    When `cache` is a dict, results are memoized under a key combining sr,
    signal shape and a cheap content fingerprint, guarding against in-place
    mutation of the same array. `cache=None` (default) computes as before."""
    if cache is not None:
        key = (sr, signal.shape, id(signal), float(signal.sum()))
        hit = cache.get(key)
        if hit is not None:
            return hit

    mono = to_mono(signal).astype(np.float64)
    nyquist = sr / 2.0

    energies: dict[str, float] = {}
    for name, low, high in SPECTRAL_BANDS:
        low_n = max(low / nyquist, 1e-5)
        high_n = min(high / nyquist, 0.999)
        sos = butter(4, [low_n, high_n], btype="bandpass", output="sos")
        filtered = sosfiltfilt(sos, mono)
        energies[name] = float(np.sum(filtered**2))

    total = sum(energies.values()) + 1e-12
    result = {name: e / total for name, e in energies.items()}

    if cache is not None:
        cache[key] = result
    return result


def sub_bass_ratio(band_energies: dict[str, float]) -> float:
    """Fraction of total energy sitting in sub-bass + bass — this replaces the
    old plugin's hardcoded `subBassRatio = 0.15f` placeholder with a real
    measurement so genre detection actually responds to the audio."""
    return band_energies["sub_bass"] + band_energies["bass"]
