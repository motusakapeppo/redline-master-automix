import numpy as np

from redline.correlometer import measure_bass_phase_shift_deg_abs


def _bass_tone(n=8820, sr=44100, freq=40.0):
    t = np.linspace(0, n / sr, n, endpoint=False)
    return np.sin(2 * np.pi * freq * t).astype(np.float64), sr


def test_identical_channels_no_phase_shift():
    mono, sr = _bass_tone()
    stereo = np.stack([mono, mono], axis=1)
    shift = measure_bass_phase_shift_deg_abs(stereo, sr)
    assert shift < 1.0


def test_delayed_channel_shows_phase_shift():
    mono, sr = _bass_tone(freq=40.0)
    delay_samples = 20
    right = np.roll(mono, delay_samples)
    right[:delay_samples] = 0.0
    stereo = np.stack([mono, right], axis=1)
    shift = measure_bass_phase_shift_deg_abs(stereo, sr)
    assert shift > 5.0


def test_mono_input_returns_zero():
    mono, sr = _bass_tone()
    shift = measure_bass_phase_shift_deg_abs(mono, sr)
    assert shift == 0.0


def test_silent_input_returns_zero():
    sr = 44100
    silence = np.zeros((4410, 2))
    shift = measure_bass_phase_shift_deg_abs(silence, sr)
    assert shift == 0.0
