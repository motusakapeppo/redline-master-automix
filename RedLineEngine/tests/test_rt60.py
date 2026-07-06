import numpy as np

from redline.rt60 import estimate_rt60, room_size_for_rt60, calibrate_room_plate


def test_estimate_rt60_returns_none_on_silence():
    sr = 44100
    silence = np.zeros(sr * 2, dtype=np.float32)
    assert estimate_rt60(silence, sr) is None


def test_estimate_rt60_finds_a_decay_from_a_transient():
    sr = 44100
    n = sr * 2
    t = np.arange(n) / sr
    envelope = np.exp(-t * 3.0)
    rng = np.random.default_rng(0)
    audio = (rng.standard_normal(n) * 0.05 * envelope).astype(np.float32)
    audio[:200] += 0.9

    rt60 = estimate_rt60(audio, sr)
    assert rt60 is not None
    assert 0.15 <= rt60 <= 4.0


def test_room_size_for_rt60_is_monotonic_and_clamped():
    small = room_size_for_rt60(0.3)
    mid = room_size_for_rt60(1.8)
    large = room_size_for_rt60(3.0)
    assert small < mid < large
    assert 0.05 <= room_size_for_rt60(100.0) <= 1.0
    assert 0.05 <= room_size_for_rt60(0.0) <= 1.0


def test_calibrate_room_plate_returns_both_buses():
    result = calibrate_room_plate(0.6)
    assert set(result.keys()) == {"room", "plate"}
    assert result["plate"] >= result["room"]
