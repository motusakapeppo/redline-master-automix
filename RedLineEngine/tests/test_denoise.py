import numpy as np

from redline.denoise import denoise


def test_denoise_reduces_broadband_noise_floor():
    # Room-tone/hiss throughout, with a clear tone only in the second half —
    # mirrors a real vocal take: constant mic noise, signal only some of the
    # time. Isolating a noise-only stretch (first half) avoids conflating
    # "did the noise floor drop" with "did the tone get distorted".
    sr = 22050
    n = sr * 4
    half = n // 2
    t_full = np.linspace(0, 4.0, n, endpoint=False)
    rng = np.random.default_rng(0)

    noise = rng.standard_normal(n).astype(np.float32) * 0.03
    tone = np.zeros(n, dtype=np.float32)
    tone[half:] = 0.25 * np.sin(2 * np.pi * 220.0 * t_full[half:])

    signal = (tone + noise).astype(np.float32)
    stereo = np.stack([signal, signal], axis=1)

    out = denoise(stereo, sr)
    assert out.shape == stereo.shape

    noise_only_before = signal[: half - sr]  # comfortably clear of the tone onset
    noise_only_after = out[: half - sr, 0]
    assert np.std(noise_only_after) < np.std(noise_only_before)


def test_denoise_zero_reduction_is_noop():
    sr = 22050
    signal = np.random.default_rng(1).standard_normal((1000, 2)).astype(np.float32) * 0.1
    out = denoise(signal, sr, reduction_db=0.0)
    assert np.array_equal(out, signal)
