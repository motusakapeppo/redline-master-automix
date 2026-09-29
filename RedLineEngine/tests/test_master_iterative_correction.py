"""Tests for masterengine._apply_reference_correction: the bounded iterative
feedback loop (point 2 of the reference-profile upgrade) that corrects
LUFS/crest-factor/width against reference_profiles.resolve_perceptual_target,
strictly through director_safety.clamp_params()."""

from __future__ import annotations

import numpy as np

from redline.masterengine import (
    _apply_reference_correction,
    _measure_perceptual,
    _perceptual_lufs_target,
    MASTER_CORRECTION_MAX_PASSES,
)
from redline.director_safety import PARAM_RANGES
import pyloudnorm as pyln


def _worst_case_signal(sr: int, seconds: float = 4.0) -> np.ndarray:
    """Very quiet, very peaky (huge crest factor), fully mono-correlated --
    far from every genre's perceptual target at once, engineered to force
    several correction passes rather than converging in one."""
    n = int(sr * seconds)
    rng = np.random.default_rng(3)
    mono = np.zeros(n, dtype=np.float32)
    # Sparse sharp clicks: high peak, very low RMS -> huge crest factor.
    click_positions = rng.integers(0, n, size=20)
    mono[click_positions] = 0.9
    mono += 0.001 * rng.standard_normal(n).astype(np.float32)  # near-silent noise floor
    return np.stack([mono, mono], axis=1).astype(np.float32)  # perfectly correlated (mono-summed) -- max mono compat


def test_iterative_correction_never_exceeds_director_safety_clamps():
    sr = 44100
    signal = _worst_case_signal(sr)
    ceiling = 10.0 ** (-1.0 / 20.0)

    events: list[dict] = []
    corrected, notes = _apply_reference_correction(
        signal, sr, "Acoustic / Classical", ceiling, on_step=lambda _m: None, on_event=events.append
    )

    assert np.all(np.isfinite(corrected))
    assert np.max(np.abs(corrected)) <= ceiling + 1e-6

    gain_lo, gain_hi = PARAM_RANGES["gain_db"]
    eq_lo, eq_hi = PARAM_RANGES["eq_gain_db"]
    ratio_lo, ratio_hi = PARAM_RANGES["compressor_ratio"]

    for note in notes:
        if "makeup loudness" in note:
            db = float(note.split("makeup loudness ")[1].replace("dB", ""))
            assert gain_lo - 1e-6 <= db <= gain_hi + 1e-6
        if "larghezza stereo" in note:
            db = float(note.split("larghezza stereo ")[1].split("dB")[0])
            assert eq_lo - 1e-6 <= db <= eq_hi + 1e-6


def test_iterative_correction_bounded_to_max_passes():
    sr = 44100
    signal = _worst_case_signal(sr)
    ceiling = 10.0 ** (-1.0 / 20.0)

    pass_events: list[dict] = []
    _apply_reference_correction(
        signal, sr, "EDM / Urban", ceiling, on_step=lambda _m: None,
        on_event=lambda evt: pass_events.append(evt) if evt.get("type") == "master_feedback_pass" else None,
    )
    passes = [e["pass"] for e in pass_events]
    assert len(passes) <= MASTER_CORRECTION_MAX_PASSES
    assert passes == sorted(passes)


def test_measure_perceptual_returns_expected_keys():
    sr = 44100
    signal = _worst_case_signal(sr)
    meter = pyln.Meter(sr)
    m = _measure_perceptual(signal, sr, meter)
    assert set(m.keys()) == {"lufs", "crest_factor", "mono_compatibility"}
    assert np.isfinite(m["lufs"])
    assert m["crest_factor"] > 0


def test_correction_improves_or_maintains_distance_to_target_on_average():
    """Not a strict monotonic-convergence guarantee (the loop is allowed to
    stop early on non-improvement), but the final measured LUFS must be
    closer to (or equal to) the genre target than the untouched input was --
    the loop must never make loudness alignment actively worse."""
    sr = 44100
    signal = _worst_case_signal(sr)
    ceiling = 10.0 ** (-1.0 / 20.0)
    meter = pyln.Meter(sr)

    from redline.reference_profiles import resolve_perceptual_target

    target = resolve_perceptual_target("Pop / Rock")
    before = _measure_perceptual(signal, sr, meter)
    corrected, _ = _apply_reference_correction(
        signal, sr, "Pop / Rock", ceiling, on_step=lambda _m: None, on_event=lambda _e: None
    )
    after = _measure_perceptual(corrected, sr, meter)

    assert abs(after["lufs"] - target["target_lufs"]) <= abs(before["lufs"] - target["target_lufs"]) + 0.5


def test_perceptual_lufs_target_platform_overrides_genre_default():
    """An explicit platform must win over the genre default (the bug: the
    feedback loop ignored the user's chosen platform and kept pulling toward
    the genre's club/spotify target)."""
    # apple (-16) beats the EDM genre default (club, -9)
    assert _perceptual_lufs_target("EDM / Urban", "apple", -9.0) == -16.0
    # youtube (-13) beats the Pop/Rock genre default (spotify, -14)
    assert _perceptual_lufs_target("Pop / Rock", "youtube", -14.0) == -13.0
    # club (-9) beats the Pop/Rock genre default (spotify, -14)
    assert _perceptual_lufs_target("Pop / Rock", "club", -14.0) == -9.0


def test_perceptual_lufs_target_auto_preserves_genre_default():
    """platform="auto" must preserve today's behaviour exactly: the genre
    default resolved by resolve_perceptual_target() is returned untouched."""
    assert _perceptual_lufs_target("EDM / Urban", "auto", -9.0) == -9.0
    assert _perceptual_lufs_target("Pop / Rock", "auto", -14.0) == -14.0


def test_apply_reference_correction_uses_platform_lufs_target():
    """Driving the loop with platform="apple" must narrate a -16 LUFS target
    (not the genre's -14/-9 default), proving the override reaches the loop."""
    sr = 44100
    signal = _worst_case_signal(sr)
    ceiling = 10.0 ** (-1.0 / 20.0)

    steps: list[str] = []
    _apply_reference_correction(
        signal, sr, "Pop / Rock", ceiling, on_step=steps.append,
        on_event=lambda _e: None, platform="apple",
    )
    assert any("target -16.0" in s for s in steps), steps


def test_apply_reference_correction_auto_keeps_genre_lufs_target():
    """platform="auto" (the default) must keep the genre-based target."""
    sr = 44100
    signal = _worst_case_signal(sr)
    ceiling = 10.0 ** (-1.0 / 20.0)

    steps: list[str] = []
    _apply_reference_correction(
        signal, sr, "Pop / Rock", ceiling, on_step=steps.append,
        on_event=lambda _e: None,
    )
    assert any("target -14.0" in s for s in steps), steps
