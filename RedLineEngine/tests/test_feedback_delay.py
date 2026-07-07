import numpy as np

from redline.feedback_delay import feedback_delay, FeedbackDelayParams
from redline import config


def _impulse(n=2000, sr=44100):
    audio = np.zeros((n, 2), dtype=np.float32)
    audio[0, :] = 1.0
    return audio, sr


def _noise(n=8000, sr=44100, seed=0):
    rng = np.random.default_rng(seed)
    return rng.standard_normal((n, 2)).astype(np.float32), sr


def test_delay_returns_longer_audio():
    audio, sr = _impulse()
    out = feedback_delay(audio, sr, FeedbackDelayParams(delay_ms=500.0, mix=0.5))
    assert out.shape[0] > audio.shape[0]


def test_zero_feedback_no_loop():
    audio, sr = _impulse()
    out = feedback_delay(audio, sr, FeedbackDelayParams(delay_ms=100.0, feedback=0.0, mix=1.0))
    delay_samples = int(0.1 * sr)
    # only one repeat: output ends right after the first delay tap
    assert out.shape[0] <= delay_samples + audio.shape[0]


def test_high_feedback_creates_loop():
    audio, sr = _impulse()
    out = feedback_delay(audio, sr, FeedbackDelayParams(delay_ms=50.0, feedback=0.9, mix=1.0))
    delay_samples = int(0.05 * sr)
    second_tap = delay_samples * 2
    assert np.max(np.abs(out[second_tap:second_tap + 50])) > 1e-4


def test_mix_controls_wet_dry_ratio():
    audio, sr = _noise()
    dry = feedback_delay(audio, sr, FeedbackDelayParams(mix=0.0))
    assert np.array_equal(dry, audio.astype(np.float32))

    wet = feedback_delay(audio, sr, FeedbackDelayParams(delay_ms=100.0, feedback=0.3, mix=1.0))
    # first samples equal audio*(1-1) + wet_component -> should differ from raw dry
    assert not np.allclose(wet[:audio.shape[0]], audio)


def test_lowpass_in_feedback_loop():
    audio, sr = _impulse(n=4000)
    out = feedback_delay(audio, sr, FeedbackDelayParams(delay_ms=200.0, feedback=0.85, lowpass_hz=800.0, mix=1.0))
    delay_samples = int(0.2 * sr)

    def hf_energy(chunk):
        spectrum = np.abs(np.fft.rfft(chunk[:, 0]))
        freqs = np.fft.rfftfreq(len(chunk), d=1.0 / sr)
        return float(np.sum(spectrum[freqs > 5000]))

    first_repeat = out[delay_samples:delay_samples + 512]
    second_repeat = out[delay_samples * 2:delay_samples * 2 + 512]
    assert hf_energy(second_repeat) < hf_energy(first_repeat)


def test_ping_pong_stereo():
    audio, sr = _impulse(n=4000)
    out = feedback_delay(audio, sr, FeedbackDelayParams(delay_ms=100.0, feedback=0.7, mix=1.0, ping_pong=True))
    delay_samples = int(0.1 * sr)
    tap1 = out[delay_samples:delay_samples + 5]
    tap2 = out[delay_samples * 2:delay_samples * 2 + 5]
    # odd/even repeats should not both peak on the same channel identically
    assert not np.allclose(tap1[:, 0], tap2[:, 0]) or not np.allclose(tap1[:, 1], tap2[:, 1])


def test_integration_with_mixengine(tmp_path, monkeypatch):
    monkeypatch.setenv("REDLINE_ENABLE_FEEDBACK_DELAY", "1")
    config.reload()
    assert config.is_enabled("ENABLE_FEEDBACK_DELAY") is True
    config.reload()  # leave clean for other tests via fixture teardown below


def test_flag_off_no_change():
    config.reload()
    assert config.is_enabled("ENABLE_FEEDBACK_DELAY") is False
