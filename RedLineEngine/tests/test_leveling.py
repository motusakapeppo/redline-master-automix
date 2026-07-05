import numpy as np

from redline.leveling import concurrent_take_gain_curves


def _make_track(sr, seconds, active_from, active_to, freq=220.0, amp=0.3):
    n = int(sr * seconds)
    t = np.linspace(0, seconds, n, endpoint=False)
    tone = amp * np.sin(2 * np.pi * freq * t)
    mask = np.zeros(n)
    mask[int(active_from * sr): int(active_to * sr)] = 1.0
    mono = (tone * mask).astype(np.float32)
    return np.stack([mono, mono], axis=1)


def test_no_compensation_when_only_one_track_active_at_a_time():
    sr = 44100
    seconds = 4.0
    track_a = _make_track(sr, seconds, 0.0, 2.0)
    track_b = _make_track(sr, seconds, 2.0, 4.0)

    curves = concurrent_take_gain_curves({"a": track_a, "b": track_b}, sr)

    # while only "a" is active (first second, well away from the boundary),
    # its gain should be ~1.0 (no reduction needed)
    idx = int(0.5 * sr)
    assert curves["a"][idx] > 0.95


def test_compensates_when_both_active_simultaneously():
    sr = 44100
    seconds = 2.0
    track_a = _make_track(sr, seconds, 0.0, 2.0)
    track_b = _make_track(sr, seconds, 0.0, 2.0)  # fully overlapping

    curves = concurrent_take_gain_curves({"a": track_a, "b": track_b}, sr)

    idx = int(1.0 * sr)
    # two simultaneous active takes -> ~1/sqrt(2) power-preserving reduction
    assert curves["a"][idx] < 0.85
    assert curves["b"][idx] < 0.85


def test_single_track_is_unaffected():
    sr = 44100
    track = _make_track(sr, 1.0, 0.0, 1.0)
    curves = concurrent_take_gain_curves({"only": track}, sr)
    assert np.allclose(curves["only"], 1.0)
