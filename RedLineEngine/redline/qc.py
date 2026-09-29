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
from scipy.signal import butter, sosfiltfilt

from .analysis.loudness import spectral_band_energies, SPECTRAL_BANDS
from .targets import load_measured_target
from .correlometer import measure_bass_phase_shift_deg_abs, DEFAULT_PHASE_THRESHOLD_DEG, DEFAULT_BAND_HZ

# name -> approximate target energy ratio per band (sub_bass, bass, low_mid, mid, high_mid, air)
# These are the FALLBACK heuristics — if a measured reference profile exists
# (redline/targets/target_<slug>.json, built by profile_targets.py from real
# commercial tracks), resolve_target() uses that instead.
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
MAX_QC_ITERATIONS = 3  # bounded feedback loop: measure -> correct -> re-measure
MAX_CUMULATIVE_CORRECTION_DB = 4.5  # per band, across all iterations combined -- stricter than
# a single pass's MAX_CORRECTION_DB so repeated small nudges can't stack into a large, unsafe EQ move

_BAND_CENTER_HZ = {name: (low + high) / 2.0 for name, low, high in SPECTRAL_BANDS}


def resolve_target(genre_name: str) -> dict[str, float]:
    """Measured reference profile for the genre if one exists, else the
    built-in heuristic. Falls back to 'Balanced' for unknown genres."""
    measured = load_measured_target(genre_name)
    if measured is not None:
        return measured
    return TARGET_BAND_RATIOS.get(genre_name, TARGET_BAND_RATIOS["Balanced"])


@dataclass
class QcReport:
    lufs: float
    true_peak_db: float
    mono_compatibility: float  # 1.0 = perfect, lower = more cancellation risk
    bass_phase_shift_deg: float  # L/R phase misalignment below 60Hz, see correlometer.py
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


def _mono_fold_bass(signal: np.ndarray, sr: int, cutoff_hz: float) -> np.ndarray:
    """Forces everything below `cutoff_hz` to mono (L=R in that band only),
    leaving the rest of the spectrum untouched. This is the standard, blunt
    mastering fix for L/R phase misalignment in the sub-bass -- there's no
    earlier pipeline state worth "rolling back" to at this point (mastering
    already ran), so instead of an ineffective revert this applies the
    actual corrective DSP move and re-measures to confirm it worked."""
    if signal.ndim == 1 or signal.shape[1] < 2:
        return signal
    nyquist = sr / 2.0
    sos = butter(4, cutoff_hz / nyquist, btype="low", output="sos")
    low_l = sosfiltfilt(sos, signal[:, 0].astype(np.float64))
    low_r = sosfiltfilt(sos, signal[:, 1].astype(np.float64))
    low_mono = (low_l + low_r) * 0.5
    corrected = signal.astype(np.float64).copy()
    corrected[:, 0] += low_mono - low_l
    corrected[:, 1] += low_mono - low_r
    return corrected.astype(np.float32)


def _build_correction_board(
    deviations: dict[str, float], cumulative_db: dict[str, float] | None = None
) -> tuple[Pedalboard | None, list[str]]:
    """cumulative_db tracks how much correction has already been applied to
    each band across prior iterations of the feedback loop in run_qc, so a
    band that's still off after two nudges gets a smaller allowance on the
    third instead of the loop being able to stack unbounded EQ moves."""
    cumulative_db = cumulative_db if cumulative_db is not None else {}
    fx = []
    notes = []
    for band_name, delta in deviations.items():
        if abs(delta) < DEVIATION_THRESHOLD:
            continue
        already = cumulative_db.get(band_name, 0.0)
        remaining = MAX_CUMULATIVE_CORRECTION_DB - abs(already)
        if remaining <= 0.1:
            continue
        gain_db = float(np.clip(-delta * 30.0, -MAX_CORRECTION_DB, MAX_CORRECTION_DB))
        gain_db = float(np.clip(gain_db, -remaining, remaining))
        if abs(gain_db) < 0.1:
            continue
        cumulative_db[band_name] = already + gain_db
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


def assess_qc_pass(
    lufs: float,
    target_lufs: float,
    true_peak_db: float,
    ceiling_db: float,
    mono_compatibility: float,
    bass_phase_shift_deg: float,
    deviations: dict[str, float],
) -> bool:
    """Pure pass/fail decision for a QC measurement — the exact boolean logic
    run_qc uses to set QcReport.passed, extracted so callers that re-measure
    the final audio (e.g. masterengine.render_master after its own feedback
    loop) can recompute `passed` against reality instead of quoting a stale
    decision made before their corrections ran.

    Thresholds (unchanged from run_qc's original inline expression):
      - LUFS within 1.0 LU of target
      - true peak at or below ceiling + 0.1dB
      - mono compatibility above 0.6
      - bass phase shift at or below DEFAULT_PHASE_THRESHOLD_DEG
      - every spectral deviation under DEVIATION_THRESHOLD * 2
    """
    return (
        abs(lufs - target_lufs) < 1.0
        and true_peak_db <= ceiling_db + 0.1
        and mono_compatibility > 0.6
        and bass_phase_shift_deg <= DEFAULT_PHASE_THRESHOLD_DEG
        and all(abs(d) < DEVIATION_THRESHOLD * 2 for d in deviations.values())
    )


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
    bass_phase_shift = measure_bass_phase_shift_deg_abs(mastered, sr)

    bands = spectral_band_energies(mastered, sr)
    target = resolve_target(genre_name)
    deviations = {name: bands[name] - target[name] for name in target}

    from . import analysis as _analysis_pkg2  # local import avoids a cycle at module load

    # Bounded feedback loop: measure -> correct -> re-measure, up to
    # MAX_QC_ITERATIONS passes. Most tracks converge (or hit the "nothing left
    # worth correcting" case) in 1 pass; a couple more passes lets a track
    # that's off on several bands at once settle closer to target than a
    # single fixed-size nudge could, while cumulative_db (see
    # _build_correction_board) keeps the total EQ move per band bounded no
    # matter how many iterations run.
    corrected = mastered
    final_lufs = lufs
    notes: list[str] = []
    cumulative_db: dict[str, float] = {}
    iterations_run = 0
    for iteration in range(MAX_QC_ITERATIONS):
        board, iter_notes = _build_correction_board(deviations, cumulative_db)
        if board is None:
            break
        iterations_run += 1
        corrected = board(corrected.T, sr).T
        notes.extend(iter_notes if iteration == 0 else [f"iter{iteration + 1}: {n}" for n in iter_notes])

        # The corrective EQ changes overall energy, which drifts loudness
        # away from the target that was already hit — re-measure and trim
        # gain back to the target instead of just reporting the drift.
        # Found in practice: without this, a genre with a sizeable spectral
        # correction could land 2+ LUFS off its own stated target.
        final_lufs = _analysis_pkg2.integrated_lufs(corrected, sr)
        makeup_db = float(np.clip(target_lufs - final_lufs, -3.0, 3.0))
        if abs(makeup_db) > 0.1:
            corrected = corrected * (10.0 ** (makeup_db / 20.0))
            final_lufs = _analysis_pkg2.integrated_lufs(corrected, sr)
            notes.append(f"loudness trim {makeup_db:+.1f}dB (post-EQ drift correction, iter {iteration + 1})")

        # Re-measure spectral deviations and true peak against the corrected,
        # gain-trimmed signal so the next iteration (or the final report)
        # reflects reality, not intent.
        bands_after = spectral_band_energies(corrected, sr)
        deviations = {name: bands_after[name] - target[name] for name in target}
        true_peak_db = 20.0 * np.log10(np.max(np.abs(corrected)) + 1e-12)

        if all(abs(d) < DEVIATION_THRESHOLD for d in deviations.values()):
            break  # converged -- no point spending another iteration

    if iterations_run > 1:
        notes.append(f"QC converged after {iterations_run} iterations")

    if bass_phase_shift > DEFAULT_PHASE_THRESHOLD_DEG:
        corrected = _mono_fold_bass(corrected, sr, DEFAULT_BAND_HZ[1])
        bass_phase_shift = measure_bass_phase_shift_deg_abs(corrected, sr)
        notes.append(f"bass mono-fold below {DEFAULT_BAND_HZ[1]:.0f}Hz (phase shift was over {DEFAULT_PHASE_THRESHOLD_DEG:.0f}°)")
        true_peak_db = 20.0 * np.log10(np.max(np.abs(corrected)) + 1e-12)

    passed = assess_qc_pass(
        lufs=final_lufs,
        target_lufs=target_lufs,
        true_peak_db=true_peak_db,
        ceiling_db=true_peak_ceiling_db,
        mono_compatibility=mono_compat,
        bass_phase_shift_deg=bass_phase_shift,
        deviations=deviations,
    )

    report = QcReport(
        lufs=final_lufs,
        true_peak_db=true_peak_db,
        mono_compatibility=mono_compat,
        bass_phase_shift_deg=bass_phase_shift,
        band_deviations=deviations,
        corrections_applied=notes,
        passed=passed,
    )
    return corrected, report
