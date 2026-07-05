import numpy as np
from scipy.signal import butter, sosfiltfilt

from redline.deesser import deess, detect_sibilance_band, SibilanceBand

TEST_BAND = SibilanceBand(5000.0, 9000.0)


def _band_energy(signal: np.ndarray, sr: int, band: SibilanceBand = TEST_BAND) -> float:
    sos = butter(6, [band.low_hz / (sr / 2), band.high_hz / (sr / 2)], btype="bandpass", output="sos")
    filtered = sosfiltfilt(sos, signal)
    return float(np.sqrt(np.mean(filtered**2)))


def test_deesser_reduces_sibilance_but_leaves_low_freq_untouched():
    sr = 44100
    n = sr * 2
    t = np.linspace(0, 2.0, n, endpoint=False)

    low_tone = 0.3 * np.sin(2 * np.pi * 200.0 * t)

    rng = np.random.default_rng(0)
    noise = rng.standard_normal(n).astype(np.float32)
    sos = butter(6, [TEST_BAND.low_hz / (sr / 2), TEST_BAND.high_hz / (sr / 2)], btype="bandpass", output="sos")
    sibilant_noise = sosfiltfilt(sos, noise)

    burst_mask = np.zeros(n)
    burst_mask[: n // 2] = 1.0  # sibilant burst only in the first half
    sibilant_burst = sibilant_noise * burst_mask * 0.5

    signal = (low_tone + sibilant_burst).astype(np.float32)
    # Fixed band here so the test isolates the reduction behavior from the
    # adaptive detection behavior (covered separately below).
    out = deess(signal, sr, band=TEST_BAND)

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


def test_adaptive_band_detection_finds_the_actual_sibilance_frequency():
    sr = 44100
    n = sr * 2
    rng = np.random.default_rng(2)

    # A voice with sibilance concentrated much higher than the "classic"
    # 5-9kHz assumption (e.g. a bright mic/voice) should still be found.
    high_band = SibilanceBand(8500.0, 10200.0)
    sos = butter(6, [high_band.low_hz / (sr / 2), high_band.high_hz / (sr / 2)], btype="bandpass", output="sos")
    noise = rng.standard_normal(n).astype(np.float64)
    sibilant = sosfiltfilt(sos, noise)

    burst_mask = np.zeros(n)
    burst_mask[::5] = 1.0  # scattered short consonant-like bursts
    signal = (sibilant * burst_mask * 0.6).astype(np.float32)

    detected = detect_sibilance_band(signal, sr)
    center = (detected.low_hz + detected.high_hz) / 2.0
    assert 7500.0 < center < 10500.0
