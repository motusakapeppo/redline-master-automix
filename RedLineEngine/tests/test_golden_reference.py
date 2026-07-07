import numpy as np

from redline.input_loader import Stems
from redline.analyze import analyze
from redline.wizard import MixPreferences
from redline.mixengine import render_mix

from tests.golden_reference import generate_golden, assert_golden_match


def _stems_from_golden(name: str) -> Stems:
    audio, sr = generate_golden(name)
    return Stems(sample_rate=sr, tracks={"other": audio})


def test_golden_sine_sweep_produces_output():
    stems = _stems_from_golden("sine_sweep")
    analysis = analyze(stems)
    mixed = render_mix(stems, analysis, MixPreferences())
    assert np.max(np.abs(mixed)) > 0.0


def test_golden_impulse_preserved():
    stems = _stems_from_golden("silence_impulse")
    analysis = analyze(stems)
    mixed = render_mix(stems, analysis, MixPreferences())
    assert np.max(np.abs(mixed)) > 0.01


def test_golden_noise_has_band_energy():
    stems = _stems_from_golden("white_noise")
    analysis = analyze(stems)
    mixed = render_mix(stems, analysis, MixPreferences())

    spectrum = np.abs(np.fft.rfft(mixed[:, 0]))
    freqs = np.fft.rfftfreq(len(mixed), d=1.0 / stems.sample_rate)
    low = np.sum(spectrum[(freqs > 20) & (freqs < 500)])
    mid = np.sum(spectrum[(freqs >= 500) & (freqs < 5000)])
    high = np.sum(spectrum[(freqs >= 5000) & (freqs < 20000)])
    assert low > 0.0 and mid > 0.0 and high > 0.0


def test_golden_identical_runs_match():
    audio, sr = generate_golden("white_noise")
    assert_golden_match("white_noise", audio, sr)
