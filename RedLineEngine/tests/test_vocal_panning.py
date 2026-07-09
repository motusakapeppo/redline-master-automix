"""Validates two real listening-test-driven panning fixes in mixengine.py:

1. The lead vocal bus is locked to dead-center (mono-folded) regardless of
   any residual L/R imbalance in the source recording -- the one element
   that's supposed to be maximally central shouldn't inherit the source
   file's own stereo image.
2. A lone vocal double with no L/R/dx/sx panning hint at all used to default
   to `d.pan >= 0`, which is True for the unhinted pan==0.0 case too --
   silently hard-panning every unhinted double to the same side instead of
   spreading them. A single unhinted double in its register is now
   auto-split into a genuine hard L+R pair.
"""

from __future__ import annotations

import numpy as np
import pytest

from redline.input_loader import Stems
from redline.analyze import analyze
from redline.wizard import MixPreferences
from redline.bus_exporter import export_buses

SR = 44100


def _stereo(mono: np.ndarray, pan: float = 0.0) -> np.ndarray:
    """Builds a stereo buffer from a mono signal with a constant-power pan,
    so a test can simulate a source file that was exported slightly off
    center (pan != 0) instead of always starting from a perfectly centered
    take."""
    angle = (pan + 1.0) * (np.pi / 4.0)
    left = mono * np.cos(angle)
    right = mono * np.sin(angle)
    return np.stack([left, right], axis=1).astype(np.float32)


def _tone(freq: float, seconds: float = 2.0) -> np.ndarray:
    t = np.linspace(0, seconds, int(SR * seconds), endpoint=False)
    return (0.15 * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _lead_bus_lr_energy(pan: float) -> tuple[float, float]:
    lead = _stereo(_tone(220.0), pan=pan)
    stems = Stems(sample_rate=SR, tracks={"Voce Lead": lead})
    analysis = analyze(stems)
    buses = export_buses(stems, analysis, MixPreferences())
    assert buses.vocal_main is not None
    return (
        float(np.sum(buses.vocal_main[:, 0] ** 2)),
        float(np.sum(buses.vocal_main[:, 1] ** 2)),
    )


def test_lead_vocal_is_locked_dead_center_even_if_source_is_off_center():
    # The captured bus includes the "space" reverb/delay send applied after
    # the centering fix -- that send is deliberately stereo/diffuse (real
    # width is the point of a reverb), so a pan==0 source's L/R energy
    # won't be bit-identical either. The real signature of the centering
    # fix isn't "zero width" but "source pan is discarded before anything
    # stereo happens": a source panned +0.3 and one panned -0.3 must
    # produce statistically the SAME L/R balance, since the dry signal that
    # dominates localization is mono-folded before the reverb/delay send
    # ever sees it. Without the fix, +0.3 vs -0.3 would favor opposite
    # sides.
    right_leaning_l, right_leaning_r = _lead_bus_lr_energy(pan=0.3)
    left_leaning_l, left_leaning_r = _lead_bus_lr_energy(pan=-0.3)

    right_leaning_ratio = right_leaning_r / right_leaning_l
    left_leaning_ratio = left_leaning_r / left_leaning_l
    assert right_leaning_ratio == pytest.approx(left_leaning_ratio, rel=0.02), (
        f"source pan is leaking through the centering fix: "
        f"+0.3 source gave R/L={right_leaning_ratio:.3f}, -0.3 source gave R/L={left_leaning_ratio:.3f}"
    )


def test_lone_unhinted_double_is_auto_split_left_and_right():
    lead = _stereo(_tone(220.0))
    # A single double with NO dx/sx/L/R hint in its name at all.
    double = _stereo(_tone(220.0) * 0.8)

    stems = Stems(sample_rate=SR, tracks={"Voce Lead": lead, "Voce Double": double})
    analysis = analyze(stems)
    buses = export_buses(stems, analysis, MixPreferences())

    assert buses.vocal_doubles is not None
    left_energy = float(np.sum(buses.vocal_doubles[:, 0] ** 2))
    right_energy = float(np.sum(buses.vocal_doubles[:, 1] ** 2))
    # Previously this landed entirely on one side (whichever `d.pan >= 0`
    # picked for pan==0.0) -- both channels must now carry real energy,
    # roughly balanced, instead of one being near-silent.
    assert left_energy > 0.0
    assert right_energy > 0.0
    ratio = max(left_energy, right_energy) / min(left_energy, right_energy)
    assert ratio < 1.5, f"double auto-split isn't balanced L/R (ratio={ratio:.2f})"
