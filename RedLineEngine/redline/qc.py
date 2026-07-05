"""Post-render quality-control pass: measures the finished master against
approximate genre-reference spectral shapes and applies one bounded
corrective EQ nudge if something's clearly off — an automated "does this
actually look right" check instead of trusting the fixed recipe blindly.

The reference shapes below are approximate genre tendencies (rough energy
distribution across the same 6 analysis bands used elsewhere), not a
certified mastering-reference curve — good enough to catch a gross
imbalance (e.g. way too much low-mid mud), not meant to replace critical
listening.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from pedalboard import Pedalboard, PeakFilter, LowShelfFilter, HighShelfFilter

from .analysis.loudness import spectral_band_energies, SPECTRAL_BANDS

# name -> approximate target energy ratio per band (sub_bass, bass, low_mid, mid, high_mid, air)
TARGET_BAND_RATIOS: dict[str, dict[str, float]] = {
    "EDM / Urban": dict(sub_bass=0.22, bass=0.20, low_mid=0.12, mid=0.14, high_mid=0.16, air=0.16),
    "Hip-Hop": dict(sub_bass=0.25, bass=0.20, low_mid=0.12, mid=0.13, high_mid=0.15, air=0.15),
    "Pop / Rock": dict(sub_bass=0.12, bass=0.16, low_mid=0.15, mid=0.20, high_mid=0.20, air=0.17),
    "Acoustic / Classical": dict(sub_bass=0.08, bass=0.12, low_mid=0.18, mid=0.24, high_mid=0.20, air=0.18),
    "Jazz / Vintage": dict(sub_bass=0.10, bass=0.15, low_mid=0.18, mid=0.22, high_mid=0.18, air=0.17),
    "Balanced": dict(sub_bass=0.14, bass=0.16, low_mid=0.16, mid=0.18, high_mid=0.18, air=0.18),
}

DEVIATION_THRESHOLD = 0.05  # ratio points (e.g. 0.05 = 5 percentage points) before correcting
MAX_CORRECTION_DB = 3.0

_BAND_CENTER_HZ = {name: (low + high) / 2.0 for name, low, high in SPECTRAL_BANDS}


@dataclass
class QcReport:
    lufs: float
    true_peak_db: float
    mono_compatibility: float  # 1.0 = perfect, lower = more cancellation risk
    band_deviations: dict[str, float]
    corrections_applied: list[str]
    passed: bool


def _mono_compatibility(signal: np.ndarray) -> float:
    """Ratio of mono-summed energy to stereo energy — well below 1.0 flags
    real cancellation risk (out-of-phase content)."""
    if signal.ndim == 1:
        return 1.0
    stereo_energy = np.mean(signal[:, 0] ** 2) + np.mean(signal[:, 1] ** 2)
    mono = (signal[:, 0] + signal[:, 1]) * 0.5
    mono_energy = np.mean(mono**2) * 2.0  # *2 so in-phase identical channels score 1.0
    if stereo_energy < 1e-12:
        return 1.0
    return float(np.clip(mono_energy / stereo_energy, 0.0, 1.5))


def _build_correction_board(deviations: dict[str, float]) -> tuple[Pedalboard | None, list[str]]:
    fx = []
    notes = []
    for band_name, delta in deviations.items():
        if abs(delta) < DEVIATION_THRESHOLD:
            continue
        gain_db = float(np.clip(-delta * 30.0, -MAX_CORRECTION_DB, MAX_CORRECTION_DB))
        freq = _BAND_CENTER_HZ[band_name]
        if band_name == "sub_bass":
            fx.append(LowShelfFilter(cutoff_frequency_hz=freq, gain_db=gain_db, q=0.7))
        elif band_name == "air":
            fx.append(HighShelfFilter(cutoff_frequency_hz=freq, gain_db=gain_db, q=0.7))
        else:
            fx.append(PeakFilter(cutoff_frequency_hz=freq, gain_db=gain_db, q=1.0))
        notes.append(f"{band_name} ({freq:.0f}Hz) {gain_db:+.1f}dB")

    if not fx:
        return None, []
    return Pedalboard(fx), notes


def run_qc(
    mastered: np.ndarray,
    sr: int,
    genre_name: str,
    target_lufs: float,
    true_peak_ceiling_db: float,
) -> tuple[np.ndarray, QcReport]:
    """Measures the mastered mix and applies one bounded corrective EQ pass
    if a band is clearly off the genre's approximate reference shape.
    Returns (possibly-corrected audio, report) — the report is always
    returned, including any deviation that couldn't be fully corrected, so
    the result is never silently claimed to be "perfect" when it isn't."""
    from . import analysis as _analysis_pkg  # local import avoids a cycle at module load

    mono = mastered.mean(axis=1) if mastered.ndim == 2 else mastered
    lufs = _analysis_pkg.integrated_lufs(mastered, sr)
    true_peak_db = 20.0 * np.log10(np.max(np.abs(mastered)) + 1e-12)
    mono_compat = _mono_compatibility(mastered)

    bands = spectral_band_energies(mastered, sr)
    target = TARGET_BAND_RATIOS.get(genre_name, TARGET_BAND_RATIOS["Balanced"])
    deviations = {name: bands[name] - target[name] for name in target}

    board, notes = _build_correction_board(deviations)
    corrected = mastered
    if board is not None:
        corrected = board(mastered.T, sr).T
        # Re-measure after correction so the report reflects reality, not intent
        bands_after = spectral_band_energies(corrected, sr)
        deviations = {name: bands_after[name] - target[name] for name in target}

    passed = (
        abs(lufs - target_lufs) < 1.0
        and true_peak_db <= true_peak_ceiling_db + 0.1
        and mono_compat > 0.6
        and all(abs(d) < DEVIATION_THRESHOLD * 2 for d in deviations.values())
    )

    report = QcReport(
        lufs=lufs,
        true_peak_db=true_peak_db,
        mono_compatibility=mono_compat,
        band_deviations=deviations,
        corrections_applied=notes,
        passed=passed,
    )
    return corrected, report
