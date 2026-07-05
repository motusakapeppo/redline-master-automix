import numpy as np

from redline.resonance import find_resonance, MUD_LOW_HZ, MUD_HIGH_HZ


def test_detects_a_real_resonance_bump():
    sr = 44100
    n = sr * 3
    t = np.linspace(0, 3.0, n, endpoint=False)
    rng = np.random.default_rng(5)
    noise = rng.standard_normal(n) * 0.02
    bump = 0.5 * np.sin(2 * np.pi * 300.0 * t)  # strong resonance at 300Hz
    signal = (noise + bump).astype(np.float32)

    cut = find_resonance(signal, sr)
    assert cut is not None
    assert MUD_LOW_HZ <= cut.freq <= MUD_HIGH_HZ
    assert abs(cut.freq - 300.0) < 40.0
    assert cut.gain_db < 0


def test_flat_spectrum_has_no_resonance():
    sr = 44100
    n = sr * 3
    rng = np.random.default_rng(6)
    signal = (rng.standard_normal(n) * 0.05).astype(np.float32)

    cut = find_resonance(signal, sr)
    assert cut is None
