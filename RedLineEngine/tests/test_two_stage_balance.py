"""Flag-gated two-stage balance (ENABLE_TWO_STAGE_BALANCE).

OFF => render_mix must be bit-identical to the flag-off baseline.
ON  => a synthetic mix with one very loud "other" stem is rebalanced
       (loud-vs-quiet ratio shrinks) and total energy stays sane
       (no clipping after the final safety ceiling). Fail-safe on
       silent input (render still completes).
"""

from __future__ import annotations

import numpy as np
import pytest

from redline import config
from redline.input_loader import Stems
from redline.analyze import analyze
from redline.wizard import MixPreferences
from redline.mixengine import render_mix


def _stems(sr: int = 44100, seconds: float = 2.0) -> Stems:
    """Four "other"-role stems with wildly different levels: one very loud,
    one very quiet, two middling. Names carry no role hints, so naming.py
    classifies them all as role="other" (folded into the music bus)."""
    n = int(sr * seconds)
    t = np.linspace(0, seconds, n, endpoint=False)
    rng = np.random.default_rng(11)
    loud = 0.9 * np.sin(2 * np.pi * 220.0 * t)
    quiet = 0.02 * np.sin(2 * np.pi * 330.0 * t) + 0.002 * rng.standard_normal(n)
    mid1 = 0.15 * np.sin(2 * np.pi * 440.0 * t)
    mid2 = 0.12 * np.sin(2 * np.pi * 550.0 * t)

    def st(m):
        return np.stack([m, m], axis=1).astype(np.float32)

    return Stems(sample_rate=sr, tracks={
        "Pad_A": st(loud), "Pad_B": st(quiet), "Pad_C": st(mid1), "Pad_D": st(mid2),
    })


def _render(flags: dict) -> np.ndarray:
    for key, value in flags.items():
        config.set_override(key, value)
    try:
        stems = _stems()
        analysis = analyze(stems)
        return render_mix(stems, analysis, MixPreferences())
    finally:
        for key in flags:
            config.set_override(key, False)


def test_off_matches_baseline_bit_identical():
    baseline = _render({})
    with_flags_off = _render({"ENABLE_TWO_STAGE_BALANCE": False})
    assert np.array_equal(baseline, with_flags_off)


def test_on_rebalances_loud_vs_quiet_and_stays_sane():
    off = _render({})
    on = _render({"ENABLE_TWO_STAGE_BALANCE": True})

    # The loud-vs-quiet imbalance must shrink: measure the ratio between the
    # RMS of the loudest and quietest 1-second block of each render.
    def block_rms_ratio(mix: np.ndarray) -> float:
        mono = mix.mean(axis=1)
        blocks = np.array_split(mono, max(1, mono.size // 44100))
        rmss = np.array([float(np.sqrt(np.mean(b.astype(np.float64) ** 2))) for b in blocks if b.size])
        loud_rms = float(np.max(rmss))
        quiet_rms = max(float(np.min(rmss)), 1e-9)
        return loud_rms / quiet_rms

    ratio_off = block_rms_ratio(off)
    ratio_on = block_rms_ratio(on)
    assert ratio_on < ratio_off, f"expected rebalance, ratio {ratio_on:.2f} >= {ratio_off:.2f}"

    # Total energy sane: no clipping after the final safety ceiling.
    assert float(np.max(np.abs(on))) <= 1.0
    # And the render is not empty/silenced by the balance stage.
    assert float(np.sqrt(np.mean(on.astype(np.float64) ** 2))) > 1e-4


def test_on_silent_input_failsafe():
    n = 44100
    silence = np.zeros((n, 2), dtype=np.float32)
    config.set_override("ENABLE_TWO_STAGE_BALANCE", True)
    try:
        stems = Stems(sample_rate=44100, tracks={"Pad_A": silence, "Pad_B": silence.copy()})
        analysis = analyze(stems)
        mixed = render_mix(stems, analysis, MixPreferences())
        assert mixed is not None
        assert mixed.shape[0] == n
        assert float(np.max(np.abs(mixed))) == 0.0
    finally:
        config.set_override("ENABLE_TWO_STAGE_BALANCE", False)