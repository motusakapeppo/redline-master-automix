import numpy as np

from redline.analysis.pitch import estimate_fundamental, high_frequency_ratio


def _tone_with_silence(freq, sr, active_seconds=1.5, silence_seconds=8.0, amp=0.3):
    """Simulates the exact problem described: a couple seconds of real
    singing buried in a long mostly-silent take with faint room noise."""
    n_active = int(active_seconds * sr)
    n_silence = int(silence_seconds * sr)
    t = np.linspace(0, active_seconds, n_active, endpoint=False)
    active = amp * np.sin(2 * np.pi * freq * t)

    rng = np.random.default_rng(0)
    noise_floor = rng.standard_normal(n_silence).astype(np.float32) * 0.0005  # near-silent room noise

    mono = np.concatenate([noise_floor[: n_silence // 2], active, noise_floor[n_silence // 2:]]).astype(np.float32)
    return np.stack([mono, mono], axis=1)


def test_pitch_survives_mostly_silent_take():
    sr = 44100
    signal = _tone_with_silence(150.0, sr)
    f0 = estimate_fundamental(signal, sr)
    # without VAD isolation, silence/noise would badly drag this estimate;
    # with it, the estimate should land close to the one real active tone
    assert abs(f0 - 150.0) < 15.0


def test_pitch_ignores_mains_hum_range():
    # A signal with almost no energy above 1kHz and dominated by content
    # near 60Hz (mains hum range) should not be reported at face value if
    # there's a real higher-pitched component too — band-limiting still
    # allows genuine low voices (e.g. ~90Hz) to be found correctly.
    sr = 44100
    n = sr * 3
    t = np.linspace(0, 3.0, n, endpoint=False)
    voice = 0.25 * np.sin(2 * np.pi * 130.0 * t)
    hum = 0.4 * np.sin(2 * np.pi * 60.0 * t)  # stronger than the "voice" on purpose
    mono = (voice + hum).astype(np.float32)
    signal = np.stack([mono, mono], axis=1)

    f0 = estimate_fundamental(signal, sr)
    # band-limit floor is 80Hz, so 60Hz hum cannot dominate the estimate
    assert f0 >= 80.0


def test_high_frequency_ratio_distinguishes_bright_from_dark():
    sr = 44100
    n = sr
    t = np.linspace(0, 1.0, n, endpoint=False)
    bright = (0.3 * np.sin(2 * np.pi * 6000.0 * t)).astype(np.float32)
    dark = (0.3 * np.sin(2 * np.pi * 100.0 * t)).astype(np.float32)

    assert high_frequency_ratio(np.stack([bright, bright], axis=1), sr) > 0.5
    assert high_frequency_ratio(np.stack([dark, dark], axis=1), sr) < 0.05
