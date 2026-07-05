import numpy as np

from redline.dsp_utils import split_band, apply_band_gain_curve, to_mid_side, from_mid_side


def test_split_band_recombines_to_original():
    sr = 44100
    n = sr
    rng = np.random.default_rng(7)
    signal = (rng.standard_normal((n, 2)) * 0.1).astype(np.float32)

    band, rest = split_band(signal, sr, 1000.0, 4000.0)
    recombined = band + rest
    assert np.allclose(recombined, signal, atol=1e-4)


def test_apply_band_gain_curve_only_affects_target_band():
    sr = 44100
    n = sr
    t = np.linspace(0, 1.0, n, endpoint=False)
    low_tone = 0.3 * np.sin(2 * np.pi * 200.0 * t)
    mid_tone = 0.3 * np.sin(2 * np.pi * 2000.0 * t)
    signal = np.stack([low_tone + mid_tone, low_tone + mid_tone], axis=1).astype(np.float32)

    gain_curve = np.full(n, 0.1, dtype=np.float32)  # heavy reduction
    out = apply_band_gain_curve(signal, sr, 1000.0, 4000.0, gain_curve)

    # the 200Hz tone (outside the ducked band) should survive close to intact
    from scipy.signal import butter, sosfiltfilt
    sos_low = butter(4, [100 / (sr / 2), 400 / (sr / 2)], btype="bandpass", output="sos")
    low_before = sosfiltfilt(sos_low, signal[:, 0])
    low_after = sosfiltfilt(sos_low, out[:, 0])
    assert np.corrcoef(low_before, low_after)[0, 1] > 0.99
    assert np.sqrt(np.mean(low_after**2)) > 0.5 * np.sqrt(np.mean(low_before**2))

    # the 2kHz tone (inside the ducked band) should be substantially reduced
    sos_mid = butter(4, [1500 / (sr / 2), 2500 / (sr / 2)], btype="bandpass", output="sos")
    mid_before = sosfiltfilt(sos_mid, signal[:, 0])
    mid_after = sosfiltfilt(sos_mid, out[:, 0])
    assert np.sqrt(np.mean(mid_after**2)) < 0.3 * np.sqrt(np.mean(mid_before**2))


def test_mid_side_round_trip():
    rng = np.random.default_rng(8)
    signal = (rng.standard_normal((1000, 2)) * 0.2).astype(np.float32)
    mid, side = to_mid_side(signal)
    recombined = from_mid_side(mid, side)
    assert np.allclose(recombined, signal, atol=1e-5)
