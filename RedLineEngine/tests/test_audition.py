import numpy as np

from redline.audition import extract_smart_chunk
from redline import config


def test_extract_smart_chunk_finds_loudest_window():
    sr = 1000
    quiet = np.zeros(sr)
    loud = np.ones(sr) * 0.8
    audio = np.concatenate([quiet, loud, quiet])

    chunk = extract_smart_chunk(audio, sr, duration_sec=1.0)

    assert chunk.shape[0] == sr
    assert np.mean(np.abs(chunk)) > 0.5


def test_extract_smart_chunk_returns_whole_array_if_shorter_than_duration():
    sr = 1000
    audio = np.ones(500)
    chunk = extract_smart_chunk(audio, sr, duration_sec=1.0)
    assert chunk.shape[0] == 500


def test_live_audition_flag_defaults_off():
    config.reload()
    assert config.is_enabled("ENABLE_LIVE_AUDITION") is False


def test_set_override_toggles_flag_at_runtime():
    config.reload()
    assert config.is_enabled("ENABLE_LIVE_AUDITION") is False
    config.set_override("ENABLE_LIVE_AUDITION", True)
    assert config.is_enabled("ENABLE_LIVE_AUDITION") is True
    config.set_override("ENABLE_LIVE_AUDITION", False)
    assert config.is_enabled("ENABLE_LIVE_AUDITION") is False
