import numpy as np

from redline.depth import classify_depth, classify_stem_depth, spectral_flux, FOREGROUND, BACKGROUND


def test_classify_depth_thresholds():
    assert classify_depth(crest=8.0, flux=0.3) == FOREGROUND
    assert classify_depth(crest=3.0, flux=0.05) == BACKGROUND
    assert classify_depth(crest=8.0, flux=0.05) == BACKGROUND  # peaky but tonally static


def test_sustained_pad_classifies_as_background():
    sr = 22050
    n = sr * 3
    t = np.linspace(0, 3.0, n, endpoint=False)
    pad = 0.2 * (np.sin(2 * np.pi * 220.0 * t) + 0.5 * np.sin(2 * np.pi * 330.0 * t))
    stereo = np.stack([pad, pad], axis=1).astype(np.float32)

    assert classify_stem_depth(stereo, sr) == BACKGROUND


def test_percussive_clicks_classify_as_foreground():
    sr = 22050
    n = sr * 3
    signal = np.zeros(n, dtype=np.float32)
    rng = np.random.default_rng(0)
    for onset in range(0, n, sr // 4):  # a click every 250ms
        dur = int(0.01 * sr)
        end = min(onset + dur, n)
        signal[onset:end] += rng.standard_normal(end - onset).astype(np.float32) * 0.8
    stereo = np.stack([signal, signal], axis=1)

    assert classify_stem_depth(stereo, sr) == FOREGROUND


def test_spectral_flux_higher_for_changing_signal():
    sr = 22050
    n = sr * 2
    rng = np.random.default_rng(1)
    steady = (0.2 * np.sin(2 * np.pi * 220.0 * np.linspace(0, 2, n, endpoint=False))).astype(np.float32)
    changing = rng.standard_normal(n).astype(np.float32) * 0.2

    flux_steady = spectral_flux(np.stack([steady, steady], axis=1), sr)
    flux_changing = spectral_flux(np.stack([changing, changing], axis=1), sr)
    assert flux_changing > flux_steady
