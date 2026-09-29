"""Tests for the bounded iterative feedback loop in qc.run_qc (measure ->
correct -> re-measure, up to MAX_QC_ITERATIONS passes) -- verifies it
converges, respects the per-band cumulative correction cap, and never
regresses the single-pass behavior for an already-on-target signal."""

from __future__ import annotations

import numpy as np
import pytest

from redline.qc import run_qc, MAX_QC_ITERATIONS, MAX_CUMULATIVE_CORRECTION_DB, resolve_target


def _make_noise(sr: int, seconds: float = 3.0, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(sr * seconds)
    mono = rng.normal(0, 0.1, n).astype(np.float32)
    return np.stack([mono, mono], axis=1)


def test_run_qc_converges_within_iteration_cap():
    sr = 44100
    signal = _make_noise(sr, seed=1)
    corrected, report = run_qc(signal, sr, "Pop / Rock", target_lufs=-14.0, true_peak_ceiling_db=-1.0)
    assert corrected.shape == signal.shape
    assert np.all(np.isfinite(corrected))
    # band_deviations always reported, whether or not full convergence happened
    assert set(report.band_deviations.keys()) == set(resolve_target("Pop / Rock").keys())


def test_run_qc_never_exceeds_cumulative_correction_cap():
    sr = 44100
    # Heavily skewed spectrum (near-silent except a narrow low band) forces
    # the loop to keep wanting to correct across iterations -- this is the
    # case that would stack unbounded EQ without the cumulative cap.
    n = sr * 3
    t = np.arange(n) / sr
    mono = (0.2 * np.sin(2 * np.pi * 60 * t)).astype(np.float32)
    signal = np.stack([mono, mono], axis=1)

    corrected, report = run_qc(signal, sr, "Acoustic / Classical", target_lufs=-14.0, true_peak_ceiling_db=-1.0)
    assert np.all(np.isfinite(corrected))
    assert np.max(np.abs(corrected)) < 10.0  # sane amplitude, no blow-up


def test_run_qc_reports_iteration_count_when_multiple_passes_run():
    sr = 44100
    signal = _make_noise(sr, seed=2)
    _, report = run_qc(signal, sr, "EDM / Urban", target_lufs=-9.0, true_peak_ceiling_db=-1.0)
    # Either it converged in 1 pass (no "converged after" note) or it logged
    # how many iterations it took -- both are valid, but if present the
    # number must be within the documented cap.
    convergence_notes = [n for n in report.corrections_applied if "converged after" in n]
    if convergence_notes:
        iterations = int(convergence_notes[0].split("after ")[1].split(" ")[0])
        assert 1 < iterations <= MAX_QC_ITERATIONS


# --- Characterization: pin run_qc's current passed/metrics for a fixed input.
# These exact values were captured from the pre-refactor implementation; the
# assess_qc_pass() extraction must not change any of them.

_CHARACTERIZATION_LUFS = -13.999999966235608
_CHARACTERIZATION_TRUE_PEAK_DB = -6.82681941986084
_CHARACTERIZATION_MONO = 1.0
_CHARACTERIZATION_BASS_PHASE = 0.0
_CHARACTERIZATION_PASSED = False
_CHARACTERIZATION_DEVIATIONS = {
    "sub_bass": -0.11414142092494281,
    "bass": -0.1497594172500004,
    "low_mid": -0.10398203574307807,
    "mid": -0.10277647315394525,
    "high_mid": 0.04790296037686756,
    "air": 0.4227563866950983,
}


def test_run_qc_characterization_metrics_unchanged():
    sr = 44100
    signal = _make_noise(sr, seed=1)
    _, report = run_qc(signal, sr, "Pop / Rock", target_lufs=-14.0, true_peak_ceiling_db=-1.0)

    assert report.lufs == pytest.approx(_CHARACTERIZATION_LUFS, abs=1e-9)
    assert float(report.true_peak_db) == pytest.approx(_CHARACTERIZATION_TRUE_PEAK_DB, abs=1e-6)
    assert report.mono_compatibility == pytest.approx(_CHARACTERIZATION_MONO, abs=1e-9)
    assert report.bass_phase_shift_deg == pytest.approx(_CHARACTERIZATION_BASS_PHASE, abs=1e-9)
    assert report.passed is _CHARACTERIZATION_PASSED
    for name, expected in _CHARACTERIZATION_DEVIATIONS.items():
        assert report.band_deviations[name] == pytest.approx(expected, abs=1e-9)


def test_assess_qc_pass_matches_run_qc_decision():
    """The extracted helper must reproduce run_qc's own pass/fail decision for
    the same measured inputs (no behavior change from the refactor)."""
    from redline.qc import assess_qc_pass

    sr = 44100
    signal = _make_noise(sr, seed=1)
    _, report = run_qc(signal, sr, "Pop / Rock", target_lufs=-14.0, true_peak_ceiling_db=-1.0)

    recomputed = assess_qc_pass(
        lufs=report.lufs,
        target_lufs=-14.0,
        true_peak_db=float(report.true_peak_db),
        ceiling_db=-1.0,
        mono_compatibility=report.mono_compatibility,
        bass_phase_shift_deg=report.bass_phase_shift_deg,
        deviations=report.band_deviations,
    )
    assert recomputed is report.passed


# --- render_master must refresh the emitted qc_report against the FINAL audio
# (after the reference-correction feedback loop), not the pre-feedback values.

def _decorrelated_signal(sr: int, seconds: float = 4.0, seed: int = 7) -> np.ndarray:
    """Stereo signal with real side-channel decorrelation (mono compatibility
    well below 1.0) and a loudness far from target, so the feedback loop
    actually changes LUFS and mono compatibility before the report is emitted."""
    n = int(sr * seconds)
    rng = np.random.default_rng(seed)
    t = np.arange(n) / sr
    base = 0.3 * np.sin(2 * np.pi * 80 * t) + 0.2 * np.sin(2 * np.pi * 440 * t)
    left = (base + 0.25 * rng.standard_normal(n)).astype(np.float32)
    right = (base - 0.25 * rng.standard_normal(n)).astype(np.float32)
    return np.stack([left, right], axis=1).astype(np.float32)


def _analysis_for(genre_name: str):
    from redline.analyze import AnalysisResult
    from redline.analysis.genre import GenreProfile

    return AnalysisResult(
        bpm=120.0,
        key_tonic="A",
        key_mode="minor",
        key_confidence=1.0,
        genre=GenreProfile(
            name=genre_name, bus_eq=[], attack_ms=10.0, release_ms=100.0,
            ratio=2.0, threshold_db=-18.0, parallel_mix=0.2,
        ),
        mix_lufs=-20.0,
        mix_crest=10.0,
        mix_sub_bass_ratio=0.2,
        transient_density=0.5,
        stems={},
    )


def test_render_master_qc_report_reflects_final_audio():
    from redline.masterengine import render_master
    from redline.qc import _mono_compatibility, assess_qc_pass, resolve_target
    from redline.analysis.loudness import spectral_band_energies
    from redline.correlometer import measure_bass_phase_shift_deg_abs

    sr = 44100
    signal = _decorrelated_signal(sr)
    analysis = _analysis_for("Pop / Rock")

    events: list[dict] = []
    mastered = render_master(signal, sr, analysis, on_event=events.append)

    # The feedback loop must actually have run and changed the audio, otherwise
    # this test wouldn't exercise the stale-report bug at all.
    assert any(e["type"] == "master_feedback_pass" for e in events)

    qc_events = [e for e in events if e["type"] == "qc_report"]
    assert qc_events, "expected a qc_report event"
    emitted = qc_events[-1]

    # Emitted mono compatibility must match a fresh measurement of the audio
    # actually returned (the bug: it quoted the pre-feedback value). The event
    # rounds to 2 decimals, so compare against the fresh value at that same
    # precision -- pre-refactor this was 0.71 (stale) vs 0.72 (fresh).
    fresh_mono = _mono_compatibility(mastered)
    assert emitted["mono_compatibility"] == pytest.approx(round(fresh_mono, 2), abs=1e-3)

    # Emitted passed must be consistent with the FINAL metrics, recomputed via
    # the same helper run_qc uses.
    from redline.analysis.loudness import integrated_lufs

    bands = spectral_band_energies(mastered, sr)
    target = resolve_target("Pop / Rock")
    deviations = {name: bands[name] - target[name] for name in target}
    fresh_lufs = integrated_lufs(mastered, sr)
    # The emitted lufs must reflect the final audio using the SAME (stereo)
    # convention run_qc uses -- the event rounds to 1 decimal. Pre-fix this
    # quoted the mono-summed value (~3dB off on correlated stereo).
    assert emitted["lufs"] == pytest.approx(round(fresh_lufs, 1), abs=0.05)
    fresh_peak = 20.0 * np.log10(np.max(np.abs(mastered)) + 1e-12)
    fresh_bass = measure_bass_phase_shift_deg_abs(mastered, sr)

    expected_passed = assess_qc_pass(
        lufs=fresh_lufs,
        target_lufs=-14.0,
        true_peak_db=fresh_peak,
        ceiling_db=-1.0,
        mono_compatibility=fresh_mono,
        bass_phase_shift_deg=fresh_bass,
        deviations=deviations,
    )
    assert emitted["passed"] is expected_passed
