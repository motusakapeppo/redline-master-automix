"""Genuine neutrality regression guard for the universalization pass.

The other "neutral" tests only compare two renders of the SAME input, which
proves determinism, not that the new code left the default output unchanged.
This one pins an actual golden number derived from ALL-ZERO (neutral) render
parameters: if any of the new biases/overrides ever alter the default path, the
measured value changes and this fails. Regenerate the constant only with a
deliberate, reviewed behavior change.
"""

from __future__ import annotations

import numpy as np
import pytest

from redline.input_loader import Stems
from redline.analyze import analyze
from redline.wizard import MixPreferences
from redline.mixengine import render_mix


def _stems(sr: int = 44100, seconds: float = 2.0) -> Stems:
    n = int(sr * seconds)
    t = np.linspace(0, seconds, n, endpoint=False)
    rng = np.random.default_rng(7)
    vocals = 0.2 * np.sin(2 * np.pi * 440.0 * t) + 0.05 * rng.standard_normal(n)
    bass = 0.3 * np.sin(2 * np.pi * 80.0 * t)
    drums = 0.15 * rng.standard_normal(n)
    other = 0.2 * np.sin(2 * np.pi * 220.0 * t)

    def st(m):
        return np.stack([m, m], axis=1).astype(np.float32)

    return Stems(sample_rate=sr, tracks={
        "vocals": st(vocals), "bass": st(bass), "drums": st(drums), "other": st(other),
    })


# Golden checksum of the default (all-zero / neutral) render of the fixed
# stems above. Computed once from the code as merged in the universalization
# wave; any change to the DEFAULT output flips it.
_GOLDEN_MEAN = 0.000067

_MIX_PARAM_FIELDS = (
    "mono_compatibility_target", "bass_mono_below_hz", "reference_lufs_target",
    "saturation_amount", "deess_amount", "compression_amount", "vocal_reverb_amount",
)


def test_default_render_matches_golden_mean():
    stems = _stems()
    analysis = analyze(stems)
    mixed = render_mix(stems, analysis, MixPreferences())
    assert float(np.mean(mixed)) == pytest.approx(_GOLDEN_MEAN, abs=2e-5)


def test_zero_vs_unset_params_render_bit_identical():
    stems = _stems()
    analysis = analyze(stems)
    default = render_mix(stems, analysis, MixPreferences())
    explicit_zero = render_mix(stems, analysis, MixPreferences(**{f: 0.0 for f in _MIX_PARAM_FIELDS}))
    assert np.array_equal(default, explicit_zero)
