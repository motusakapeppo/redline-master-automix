import numpy as np

from redline.ltas import compute_ltas, compute_delta_curve, design_fir, match_ltas


def _tone(freq_hz, sr, seconds=2.0, amp=0.3):
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    return (amp * np.sin(2 * np.pi * freq_hz * t)).astype(np.float32)


def test_match_ltas_clamps_delta_and_preserves_shape():
    sr = 44100
    mix = np.stack([_tone(200, sr) + 0.05 * _tone(6000, sr)] * 2, axis=1)
    ref = np.stack([_tone(200, sr) + 0.3 * _tone(6000, sr)] * 2, axis=1)

    out, report = match_ltas(mix, sr, ref, sr, max_delta_db=2.5)

    assert out.shape == mix.shape
    assert out.dtype == np.float32
    assert not np.isnan(out).any()
    lo, hi = report["applied_delta_db_range"]
    assert lo >= -2.5 - 1e-6
    assert hi <= 2.5 + 1e-6


def test_compute_delta_curve_clamps_to_max_db():
    freqs = np.array([0.0, 100.0, 1000.0])
    mix_db = np.array([-40.0, -40.0, -40.0])
    ref_db = np.array([0.0, 0.0, 0.0])  # wildly louder reference at every bin
    delta = compute_delta_curve(freqs, mix_db, freqs, ref_db, max_delta_db=2.5)
    assert np.all(delta <= 2.5)
    assert np.all(delta >= -2.5)


def test_design_fir_returns_odd_length_filter():
    freqs = np.linspace(0, 22050, 50)
    delta = np.zeros_like(freqs)
    fir = design_fir(delta, freqs, sr=44100, numtaps=256)
    assert len(fir) % 2 == 1
