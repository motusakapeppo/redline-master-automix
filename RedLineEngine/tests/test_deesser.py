import numpy as np
from scipy.signal import butter, sosfiltfilt

from redline.deesser import deess, SIBILANCE_LOW_HZ, SIBILANCE_HIGH_HZ


def _band_energy(signal: np.ndarray, sr: int) -> float:
    sos = butter(6, [SIBILANCE_LOW_HZ / (sr / 2), SIBILANCE_HIGH_HZ / (sr / 2)], btype="bandpass", output="sos")
    band = sosfiltfilt(sos, signal)
    return float(np.sqrt(np.mean(band**2)))


def test_deesser_reduces_sibilance_but_leaves_low_freq_untouched():
    sr = 44100
    n = sr * 2
    t = np.linspace(0, 2.0, n, endpoint=False)

    low_tone = 0.3 * np.sin(2 * np.pi * 200.0 * t)

    rng = np.random.default_rng(0)
    noise = rng.standard_normal(n).astype(np.float32)
    sos = butter(6, [SIBILANCE_LOW_HZ / (sr / 2), SIBILANCE_HIGH_HZ / (sr / 2)], btype="bandpass", output="sos")
    sibilant_noise = sosfiltfilt(sos, noise)

    burst_mask = np.zeros(n)
    burst_mask[: n // 2] = 1.0  # sibilant burst only in the first half
    sibilant_burst = sibilant_noise * burst_mask * 0.5

    signal = (low_tone + sibilant_burst).astype(np.float32)
    out = deess(signal, sr)

    energy_before = _band_energy(signal[: n // 2], sr)
    energy_after = _band_energy(out[: n // 2], sr)
    assert energy_after < 0.5 * energy_before, "sibilance during the burst should be substantially reduced"

    # second half has no sibilant burst, just the low tone — must survive de-essing intact
    before_low = signal[n // 2 :]
    after_low = out[n // 2 :]
    assert np.corrcoef(before_low, after_low)[0, 1] > 0.99


def test_deesser_handles_stereo():
    sr = 44100
    n = sr
    rng = np.random.default_rng(1)
    mono = rng.standard_normal(n).astype(np.float32) * 0.1
    stereo = np.stack([mono, mono], axis=1)
    out = deess(stereo, sr)
    assert out.shape == stereo.shape
