"""Wave 2 / Track E2: the 7 Wave-1 MixPreferences parameters must actually
reach the DSP. Each test proves a NON-neutral value changes the rendered
output, and the key regression guard proves 0.0 is bit-identical to today.

Design notes:
- The synthetic stems deliberately carry broadband (noise) content in the
  vocal so the de-esser has real sibilance to act on -- a pure sine has no
  energy in the 3-11kHz sibilance band and would make the de-ess test pass
  vacuously.
- `render_master` is expensive, so the two mastering-only fields
  (bass_mono_below_hz, mono_compatibility_target) are proven at the unit
  level (the exact DSP helper / decision function) plus a cheap integration
  assertion on the emitted event, instead of a second full mastering render.
"""

from __future__ import annotations

import numpy as np
import pytest

from redline.input_loader import Stems
from redline.analyze import analyze
from redline.wizard import MixPreferences
from redline.mixengine import render_mix
from redline.masterengine import (
    render_master,
    _mid_side_polish,
    _target_lufs_for_genre,
)
from redline.analysis.loudness import integrated_lufs
from redline.qc import assess_qc_pass


def _make_stems(sr: int = 44100, seconds: float = 2.0) -> Stems:
    n = int(sr * seconds)
    t = np.linspace(0, seconds, n, endpoint=False)
    rng = np.random.default_rng(42)

    # Vocal carries a strong sibilance-band component (7kHz) plus broadband
    # HF noise so the de-esser has real work to do -- a pure sine has no
    # energy in the 3-11kHz sibilance band and would make the de-ess test
    # pass vacuously (max_reduction would never be reached).
    vocals = (
        0.2 * np.sin(2 * np.pi * 440.0 * t)
        + 0.15 * np.sin(2 * np.pi * 7000.0 * t)
        + 0.05 * rng.standard_normal(n)
    )
    bass = 0.3 * np.sin(2 * np.pi * 80.0 * t)
    drums = 0.15 * rng.standard_normal(n)
    other = 0.2 * np.sin(2 * np.pi * 220.0 * t) + 0.05 * rng.standard_normal(n)

    def stereo(mono):
        return np.stack([mono, mono], axis=1).astype(np.float32)

    return Stems(
        sample_rate=sr,
        tracks={
            "vocals": stereo(vocals),
            "bass": stereo(bass),
            "drums": stereo(drums),
            "other": stereo(other),
        },
    )


# ---------------------------------------------------------------------------
# Mix-stage biases: a non-neutral value must change the rendered mix
# ---------------------------------------------------------------------------

def test_compression_amount_changes_output():
    stems = _make_stems()
    analysis = analyze(stems)

    neutral = render_mix(stems, analysis, MixPreferences(compression_amount=0.0))
    pushed = render_mix(stems, analysis, MixPreferences(compression_amount=1.0))

    assert not np.array_equal(neutral, pushed)


def test_saturation_amount_changes_output():
    stems = _make_stems()
    analysis = analyze(stems)

    neutral = render_mix(stems, analysis, MixPreferences(saturation_amount=0.0))
    pushed = render_mix(stems, analysis, MixPreferences(saturation_amount=1.0))

    assert not np.array_equal(neutral, pushed)


def test_deess_amount_changes_output():
    stems = _make_stems()
    analysis = analyze(stems)

    neutral = render_mix(stems, analysis, MixPreferences(deess_amount=0.0))
    pushed = render_mix(stems, analysis, MixPreferences(deess_amount=1.0))

    assert not np.array_equal(neutral, pushed)


def test_vocal_reverb_amount_changes_output():
    stems = _make_stems()
    analysis = analyze(stems)

    neutral = render_mix(stems, analysis, MixPreferences(vocal_reverb_amount=0.0))
    pushed = render_mix(stems, analysis, MixPreferences(vocal_reverb_amount=1.0))

    assert not np.array_equal(neutral, pushed)


# ---------------------------------------------------------------------------
# KEY REGRESSION GUARD: 0.0 must be truly neutral (bit-identical)
# ---------------------------------------------------------------------------

def test_neutral_params_are_bit_identical():
    """All 7 new params explicitly set to 0.0 must produce output bit-identical
    to the default MixPreferences -- guaranteeing 0.0 is a true no-op."""
    stems = _make_stems()
    analysis = analyze(stems)

    default = render_mix(stems, analysis, MixPreferences())
    explicit_zero = render_mix(
        stems,
        analysis,
        MixPreferences(
            mono_compatibility_target=0.0,
            bass_mono_below_hz=0.0,
            reference_lufs_target=0.0,
            saturation_amount=0.0,
            deess_amount=0.0,
            compression_amount=0.0,
            vocal_reverb_amount=0.0,
        ),
    )

    assert np.array_equal(default, explicit_zero)


# ---------------------------------------------------------------------------
# Mastering: reference_lufs_target overrides the platform/genre target
# ---------------------------------------------------------------------------

def test_reference_lufs_target_override():
    stems = _make_stems()
    analysis = analyze(stems)
    mixed = render_mix(stems, analysis, MixPreferences())

    platform_target = _target_lufs_for_genre(analysis.genre.name, "auto")

    mastered = render_master(
        mixed, stems.sample_rate, analysis,
        prefs=MixPreferences(reference_lufs_target=-20.0),
    )
    measured = integrated_lufs(mastered, stems.sample_rate)

    assert abs(measured - (-20.0)) < abs(measured - platform_target), (
        f"measured {measured:.2f} LUFS not closer to -20 than to platform "
        f"target {platform_target:.2f}"
    )


# ---------------------------------------------------------------------------
# Mastering: bass_mono_below_hz overrides the M/S mono crossover
# ---------------------------------------------------------------------------

def test_bass_mono_below_hz_changes_mid_side_output():
    """The M/S polish helper must honour an explicit mono crossover."""
    sr = 44100
    n = sr  # 1s
    t = np.linspace(0, 1.0, n, endpoint=False)
    # Low-frequency side content (L/R differ below 120Hz) so the crossover
    # choice actually changes what survives in the side channel.
    left = 0.3 * np.sin(2 * np.pi * 60.0 * t)
    right = 0.3 * np.sin(2 * np.pi * 60.0 * t + 0.9)
    signal = np.stack([left, right], axis=1).astype(np.float32)

    default = _mid_side_polish(signal, sr, lambda _m: None, lambda _e: None)
    overridden = _mid_side_polish(
        signal, sr, lambda _m: None, lambda _e: None, mono_below_hz=250.0
    )

    assert not np.array_equal(default, overridden)


def test_bass_mono_below_hz_reaches_render_master():
    """render_master must thread prefs.bass_mono_below_hz into the M/S step."""
    stems = _make_stems()
    analysis = analyze(stems)
    mixed = render_mix(stems, analysis, MixPreferences())

    events: list[dict] = []
    render_master(
        mixed, stems.sample_rate, analysis,
        prefs=MixPreferences(bass_mono_below_hz=250.0),
        on_event=events.append,
    )
    ms_events = [e for e in events if e.get("type") == "mid_side"]
    assert ms_events, "expected a mid_side event"
    assert ms_events[-1]["mono_below_hz"] == 250.0


# ---------------------------------------------------------------------------
# Mastering: mono_compatibility_target overrides the QC mono floor
# ---------------------------------------------------------------------------

def test_mono_compatibility_target_raises_qc_floor():
    """A raised mono floor must be able to flip a QC pass to a fail."""
    kwargs = dict(
        lufs=-14.0,
        target_lufs=-14.0,
        true_peak_db=-1.0,
        ceiling_db=-1.0,
        mono_compatibility=0.7,  # passes the default 0.6 floor
        bass_phase_shift_deg=0.0,
        deviations={},
    )
    assert assess_qc_pass(**kwargs) is True
    assert assess_qc_pass(**kwargs, mono_compat_floor=0.95) is False


def test_mono_compatibility_target_reaches_render_master():
    """render_master must thread prefs.mono_compatibility_target into the QC
    decision and report the effective floor."""
    stems = _make_stems()
    analysis = analyze(stems)
    mixed = render_mix(stems, analysis, MixPreferences())

    events: list[dict] = []
    render_master(
        mixed, stems.sample_rate, analysis,
        prefs=MixPreferences(mono_compatibility_target=0.99),
        on_event=events.append,
    )
    qc_events = [e for e in events if e.get("type") == "qc_report"]
    assert qc_events, "expected a qc_report event"
    assert qc_events[-1]["mono_compat_floor"] == pytest.approx(0.99)
