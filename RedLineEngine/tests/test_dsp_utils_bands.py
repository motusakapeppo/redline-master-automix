import numpy as np

from redline.dsp_utils import split_band, apply_band_gain_curve, to_mid_side, from_mid_side, loudness_match, stereo_widen, transient_shaper


def test_split_band_recombines_to_original():
    sr = 44100
    n = sr
    rng = np.random.default_rng(7)
    signal = (rng.standard_normal((n, 2)) * 0.1).astype(np.float32)

    band, rest = split_band(signal, sr, 1000.0, 4000.0)
    recombined = band + rest
    assert np.allclose(recombined, signal, atol=1e-4)


def test_apply_band_gain_curve_only_affects_target_band():
    sr = 44100
    n = sr
    t = np.linspace(0, 1.0, n, endpoint=False)
    low_tone = 0.3 * np.sin(2 * np.pi * 200.0 * t)
    mid_tone = 0.3 * np.sin(2 * np.pi * 2000.0 * t)
    signal = np.stack([low_tone + mid_tone, low_tone + mid_tone], axis=1).astype(np.float32)

    gain_curve = np.full(n, 0.1, dtype=np.float32)  # heavy reduction
    out = apply_band_gain_curve(signal, sr, 1000.0, 4000.0, gain_curve)

    # the 200Hz tone (outside the ducked band) should survive close to intact
    from scipy.signal import butter, sosfiltfilt
    sos_low = butter(4, [100 / (sr / 2), 400 / (sr / 2)], btype="bandpass", output="sos")
    low_before = sosfiltfilt(sos_low, signal[:, 0])
    low_after = sosfiltfilt(sos_low, out[:, 0])
    assert np.corrcoef(low_before, low_after)[0, 1] > 0.99
    assert np.sqrt(np.mean(low_after**2)) > 0.5 * np.sqrt(np.mean(low_before**2))

    # the 2kHz tone (inside the ducked band) should be substantially reduced
    sos_mid = butter(4, [1500 / (sr / 2), 2500 / (sr / 2)], btype="bandpass", output="sos")
    mid_before = sosfiltfilt(sos_mid, signal[:, 0])
    mid_after = sosfiltfilt(sos_mid, out[:, 0])
    assert np.sqrt(np.mean(mid_after**2)) < 0.3 * np.sqrt(np.mean(mid_before**2))


def test_mid_side_round_trip():
    rng = np.random.default_rng(8)
    signal = (rng.standard_normal((1000, 2)) * 0.2).astype(np.float32)
    mid, side = to_mid_side(signal)
    recombined = from_mid_side(mid, side)
    assert np.allclose(recombined, signal, atol=1e-5)


# ---------------------------------------------------------------------------
# loudness_match tests
# ---------------------------------------------------------------------------


def test_loudness_match_normalizes_to_target():
    """loudness_match() should bring a signal close to the target LUFS."""
    import sys, unittest.mock as mock

    # Inject fake pyloudnorm module so mock.patch can resolve the path
    fake_pyln = mock.MagicMock()
    fake_meter = mock.MagicMock()
    fake_meter.integrated_loudness.return_value = -20.0
    fake_pyln.Meter.return_value = fake_meter
    sys.modules["pyloudnorm"] = fake_pyln

    try:
        rng = np.random.default_rng(42)
        signal = (rng.standard_normal(48000) * 0.3).astype(np.float32)
        result = loudness_match(signal, target_lufs=-16.0)
    finally:
        sys.modules.pop("pyloudnorm", None)

    assert not np.allclose(result, signal, atol=1e-6)
    assert result.dtype == signal.dtype
    rms_in = np.sqrt(np.mean(signal**2))
    rms_out = np.sqrt(np.mean(result**2))
    gain_db = 20 * np.log10(rms_out / (rms_in + 1e-12))
    assert abs(gain_db - 4.0) < 1.0, f"Expected ~4 dB gain, got {gain_db:.2f} dB"


def test_loudness_match_silent_audio_unchanged():
    """Audio with RMS < 0.001 should be returned unchanged."""
    rng = np.random.default_rng(7)
    signal = (rng.standard_normal(48000) * 1e-6).astype(np.float32)
    result = loudness_match(signal, target_lufs=-16.0)
    assert np.allclose(result, signal, atol=1e-10)


def test_loudness_match_mono_and_stereo():
    """loudness_match() should handle both 1D (mono) and 2D (stereo) arrays."""
    import sys, unittest.mock as mock

    fake_pyln = mock.MagicMock()
    fake_meter = mock.MagicMock()
    fake_meter.integrated_loudness.return_value = -18.0
    fake_pyln.Meter.return_value = fake_meter
    sys.modules["pyloudnorm"] = fake_pyln

    try:
        rng = np.random.default_rng(13)
        mono = (rng.standard_normal(48000) * 0.2).astype(np.float32)
        stereo = np.stack([mono, mono * 0.8], axis=1).astype(np.float32)
        mono_result = loudness_match(mono, target_lufs=-16.0)
        stereo_result = loudness_match(stereo, target_lufs=-16.0)
    finally:
        sys.modules.pop("pyloudnorm", None)

    assert mono_result.ndim == 1
    assert stereo_result.ndim == 2
    assert stereo_result.shape[1] == 2
    assert not np.allclose(mono_result, mono, atol=1e-6)
    assert not np.allclose(stereo_result, stereo, atol=1e-6)


def test_loudness_match_gain_clamped():
    """Gain should be clamped to ±12 dB even for extreme inputs."""
    import sys, unittest.mock as mock

    fake_pyln = mock.MagicMock()
    fake_meter = mock.MagicMock()
    fake_meter.integrated_loudness.return_value = -40.0  # very quiet → would need +24 dB
    fake_pyln.Meter.return_value = fake_meter
    sys.modules["pyloudnorm"] = fake_pyln

    try:
        rng = np.random.default_rng(21)
        quiet = (rng.standard_normal(48000) * 0.01).astype(np.float32)
        result = loudness_match(quiet, target_lufs=-16.0)
    finally:
        sys.modules.pop("pyloudnorm", None)

    rms_result = np.sqrt(np.mean(result**2))
    rms_orig = np.sqrt(np.mean(quiet**2))
    gain_ratio = rms_result / (rms_orig + 1e-12)
    # 12 dB = ~3.98x linear
    assert gain_ratio < 4.5, f"Gain ratio {gain_ratio} exceeds 12 dB clamp"


def test_loudness_match_fallback_without_pyloudnorm(monkeypatch):
    """When pyloudnorm is not available, loudness_match() should return audio unchanged."""
    import builtins
    original_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "pyloudnorm":
            raise ImportError("No module named 'pyloudnorm'")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)

    rng = np.random.default_rng(99)
    signal = (rng.standard_normal(48000) * 0.2).astype(np.float32)
    result = loudness_match(signal, target_lufs=-16.0)
    assert np.allclose(result, signal, atol=1e-10)


# ---------------------------------------------------------------------------
# stereo_widen tests
# ---------------------------------------------------------------------------


def test_stereo_widen_mono_unchanged():
    """Mono input (1D) should be returned unchanged."""
    sr = 44100
    rng = np.random.default_rng(42)
    mono = (rng.standard_normal(sr) * 0.1).astype(np.float32)
    result = stereo_widen(mono, sr, width=0.5)
    assert np.allclose(result, mono, atol=1e-10)
    assert result.ndim == 1


def test_stereo_widen_width_zero_is_mono():
    """width=0 should produce identical left/right channels (mono sum)."""
    sr = 44100
    rng = np.random.default_rng(7)
    stereo = (rng.standard_normal((sr, 2)) * 0.1).astype(np.float32)
    result = stereo_widen(stereo, sr, width=0.0)
    # Both channels should be identical
    assert np.allclose(result[:, 0], result[:, 1], atol=1e-6)
    # Output should still be stereo (2D, 2 channels)
    assert result.ndim == 2
    assert result.shape[1] == 2


def test_stereo_widen_increases_side_energy():
    """width > 1 should increase side channel energy compared to original."""
    sr = 44100
    rng = np.random.default_rng(13)
    # Create a signal with some stereo content
    left = (rng.standard_normal(sr) * 0.1).astype(np.float32)
    right = (rng.standard_normal(sr) * 0.08).astype(np.float32)
    stereo = np.stack([left, right], axis=1)

    # Measure original side energy
    _, side_orig = to_mid_side(stereo)
    orig_side_rms = float(np.sqrt(np.mean(side_orig**2)))

    # Widen
    result = stereo_widen(stereo, sr, width=2.0)
    _, side_result = to_mid_side(result)
    result_side_rms = float(np.sqrt(np.mean(side_result**2)))

    assert result_side_rms > orig_side_rms * 1.5


# ---------------------------------------------------------------------------
# transient_shaper tests
# ---------------------------------------------------------------------------


def test_transient_shaper_boost_attack():
    """Positive attack_gain_db should increase transient energy."""
    sr = 44100
    # Create a signal with a sharp transient followed by sustain
    n = sr // 2  # 0.5s
    t = np.linspace(0, n / sr, n, endpoint=False)
    # Sharp attack: fast rise, then decay to sustain
    attack = np.exp(-t * 50)  # fast decay
    sustain = 0.1 * np.sin(2 * np.pi * 440 * t)  # steady tone
    signal = (attack + sustain).astype(np.float32)

    result = transient_shaper(signal, sr, attack_gain_db=6.0, sustain_gain_db=0.0, attack_time_ms=10.0)

    # The first few samples (attack phase) should be louder
    orig_peak = float(np.max(np.abs(signal[:int(sr * 0.01)])))
    result_peak = float(np.max(np.abs(result[:int(sr * 0.01)])))
    assert result_peak > orig_peak * 1.5


def test_transient_shaper_reduce_sustain():
    """Negative sustain_gain_db should reduce sustain energy."""
    sr = 44100
    n = sr // 2
    t = np.linspace(0, n / sr, n, endpoint=False)
    # Sharp attack + long sustain
    attack = np.exp(-t * 30)
    sustain = 0.2 * np.sin(2 * np.pi * 440 * t)
    signal = (attack + sustain).astype(np.float32)

    result = transient_shaper(signal, sr, attack_gain_db=0.0, sustain_gain_db=-6.0, attack_time_ms=10.0)

    # The tail portion (last 50%) should be quieter
    half = n // 2
    orig_tail_rms = float(np.sqrt(np.mean(signal[half:]**2)))
    result_tail_rms = float(np.sqrt(np.mean(result[half:]**2)))
    assert result_tail_rms < orig_tail_rms * 0.8


def test_transient_shaper_gain_clamped():
    """Gain values should be clamped to ±12 dB."""
    sr = 44100
    rng = np.random.default_rng(42)
    signal = (rng.standard_normal(sr) * 0.1).astype(np.float32)

    # Passing extreme values should not crash and should clamp
    result = transient_shaper(signal, sr, attack_gain_db=30.0, sustain_gain_db=-30.0, attack_time_ms=5.0)
    assert result.shape == signal.shape
    assert result.dtype == signal.dtype
    # Should not be NaN or inf
    assert np.all(np.isfinite(result))
