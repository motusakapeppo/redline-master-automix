"""Flag-gated multi-resonance (ENABLE_MULTI_RESONANCE).

OFF => render_mix must be bit-identical to the flag-off baseline.
ON  => find_resonances returns at most 3 ordered nodes, each within the
       existing MAX_CUT_DB clamp; applying them changes the spectrum at
       those frequencies vs OFF. Fail-safe on empty/short input.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.signal import welch

from redline import config
from redline.resonance import (
    find_resonance,
    find_resonances,
    MAX_CUT_DB,
    MUD_LOW_HZ,
    MUD_HIGH_HZ,
)
from redline.input_loader import Stems
from redline.analyze import analyze
from redline.wizard import MixPreferences
from redline.mixengine import render_mix


def _resonant_signal(sr: int = 44100, seconds: float = 3.0) -> np.ndarray:
    """Noise floor + three distinct mud-range bumps at 200/300/420Hz."""
    n = int(sr * seconds)
    t = np.linspace(0, seconds, n, endpoint=False)
    rng = np.random.default_rng(5)
    noise = rng.standard_normal(n) * 0.02
    signal = noise.copy()
    for freq, amp in ((200.0, 0.4), (300.0, 0.3), (420.0, 0.25)):
        signal = signal + amp * np.sin(2 * np.pi * freq * t)
    return signal.astype(np.float32)


def _stems(sr: int = 44100, seconds: float = 3.0) -> Stems:
    n = int(sr * seconds)
    t = np.linspace(0, seconds, n, endpoint=False)
    rng = np.random.default_rng(7)
    vocals = 0.2 * np.sin(2 * np.pi * 440.0 * t) + 0.05 * rng.standard_normal(n)
    bass = 0.3 * np.sin(2 * np.pi * 80.0 * t)
    drums = 0.15 * rng.standard_normal(n)
    other = _resonant_signal(sr, seconds)

    def st(m):
        return np.stack([m, m], axis=1).astype(np.float32)

    return Stems(sample_rate=sr, tracks={
        "vocals": st(vocals), "bass": st(bass), "drums": st(drums), "other": st(other),
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
    with_flags_off = _render({"ENABLE_MULTI_RESONANCE": False})
    assert np.array_equal(baseline, with_flags_off)


def test_find_resonances_returns_up_to_three_ordered_clamped_nodes():
    signal = _resonant_signal()
    nodes = find_resonances(signal, 44100, max_nodes=3)
    assert isinstance(nodes, list)
    assert len(nodes) <= 3
    assert len(nodes) >= 2  # the synthetic bumps are strong enough to count
    # Ordered by descending cut strength (strongest first).
    strengths = [-n.gain_db for n in nodes]
    assert strengths == sorted(strengths, reverse=True)
    for node in nodes:
        assert MUD_LOW_HZ <= node.freq <= MUD_HIGH_HZ
        assert -MAX_CUT_DB <= node.gain_db <= 0.0
    # The single-resonance OFF path is untouched: first node agrees with it.
    single = find_resonance(signal, 44100)
    assert single is not None
    assert nodes[0].freq == pytest.approx(single.freq, abs=1.0)
    assert nodes[0].gain_db == pytest.approx(single.gain_db, abs=0.01)


def test_on_changes_spectrum_at_resonance_freqs():
    off = _render({})
    on = _render({"ENABLE_MULTI_RESONANCE": True})

    def band_db(mix: np.ndarray, freq: float) -> float:
        mono = mix.mean(axis=1).astype(np.float64)
        freqs, psd = welch(mono, fs=44100, nperseg=8192)
        mask = np.abs(freqs - freq) < 15.0
        return float(np.max(10.0 * np.log10(psd[mask] + 1e-15)))

    # The "other" stem carries bumps at 200/300/420Hz; at least one of them
    # must be attenuated in the ON render vs OFF.
    deltas = [band_db(on, f) - band_db(off, f) for f in (200.0, 300.0, 420.0)]
    assert min(deltas) < -0.5, f"expected a cut at a resonance freq, deltas={deltas}"


def test_on_empty_and_short_input_failsafe():
    assert find_resonances(np.zeros((0, 2), dtype=np.float32), 44100) == []
    short = np.zeros((100, 2), dtype=np.float32)  # shorter than 1 second
    assert find_resonances(short, 44100) == []
    flat = np.full(44100 * 2, 0.01, dtype=np.float32)
    assert find_resonances(flat, 44100) == []  # no prominence -> no cuts