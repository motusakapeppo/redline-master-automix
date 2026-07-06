"""Adaptive resonance suppression: instead of always cutting a fixed
~250-300Hz "mud" band, measure where THIS stem's energy actually piles up
in the mud range and cut only there, only if it's a real accumulation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import welch

MUD_LOW_HZ = 120.0
MUD_HIGH_HZ = 500.0
PROMINENCE_THRESHOLD_DB = 3.5  # peak must stick out this much above the band median to count as a resonance
# Was 5.0 -- in practice most real mud accumulations sit in the 3-4.5dB
# range, not the sharp 5dB+ spike this originally required, so the cut was
# almost never actually firing on real material.
MAX_CUT_DB = 4.0


@dataclass
class ResonanceCut:
    freq: float
    gain_db: float
    q: float = 3.5


def find_resonance(signal: np.ndarray, sr: int) -> ResonanceCut | None:
    mono = signal.mean(axis=1) if signal.ndim == 2 else signal
    mono = mono.astype(np.float64)
    if mono.size < sr:
        return None

    freqs, psd = welch(mono, fs=sr, nperseg=min(8192, mono.size))
    band_mask = (freqs >= MUD_LOW_HZ) & (freqs <= MUD_HIGH_HZ)
    if not np.any(band_mask):
        return None

    band_freqs = freqs[band_mask]
    band_psd_db = 10.0 * np.log10(psd[band_mask] + 1e-15)

    peak_idx = int(np.argmax(band_psd_db))
    peak_db = band_psd_db[peak_idx]
    median_db = float(np.median(band_psd_db))

    prominence = peak_db - median_db
    if prominence < PROMINENCE_THRESHOLD_DB:
        return None  # no meaningful resonance, don't cut anything

    cut_db = -min(MAX_CUT_DB, prominence * 0.5)
    return ResonanceCut(freq=float(band_freqs[peak_idx]), gain_db=cut_db, q=3.5)
