import numpy as np

from redline.audition import _estimate_lag_samples, measure_loopback_latency_ms
from redline import config


def _probe(n=2205, sr=44100, freq=1000.0):
    t = np.linspace(0, n / sr, n, endpoint=False)
    return (0.5 * np.sin(2 * np.pi * freq * t) * np.hanning(n)).astype(np.float32)


def test_estimate_lag_samples_finds_known_delay():
    probe = _probe()
    delay = 137
    recording = np.concatenate([np.zeros(delay, dtype=np.float32), probe])
    lag = _estimate_lag_samples(probe, recording)
    assert lag == delay


def test_estimate_lag_samples_returns_none_on_silence():
    probe = _probe()
    silence = np.zeros(len(probe) + 200, dtype=np.float32)
    assert _estimate_lag_samples(probe, silence) is None


def test_measure_loopback_latency_skipped_when_flag_off():
    # Force the flag off regardless of this machine's local .flags.json
    # (machine-local, gitignored, may legitimately be True for someone
    # doing real Neural Monitor testing) -- restore it afterward.
    original = config.is_enabled("ENABLE_LIVE_AUDITION")
    config.set_override("ENABLE_LIVE_AUDITION", False)
    try:
        # Must return None without ever touching sounddevice when the flag is off.
        assert measure_loopback_latency_ms() is None
    finally:
        config.set_override("ENABLE_LIVE_AUDITION", original)
