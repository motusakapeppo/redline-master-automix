"""Tests for the Matchering-style LTAS matcher (ENABLE_LTAS_V2).

OFF => match_ltas must behave exactly like the legacy implementation
(byte-identical output, same report keys). ON => the improved pipeline runs:
loudest-pieces spectrum, separate mid/side FIRs, LOWESS-style log-frequency
smoothing, iterative RMS re-correction.
"""

from __future__ import annotations

import numpy as np
import pytest

from redline import config
from redline.ltas import match_ltas


@pytest.fixture(autouse=True)
def _restore_flags():
    yield
    config.reload()


def _tone(freq_hz, sr, seconds=2.0, amp=0.3):
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    return (amp * np.sin(2 * np.pi * freq_hz * t)).astype(np.float32)


def _stereo(mono):
    return np.stack([mono, mono], axis=1)


def _signal_with_quiet_edges(sr, seconds=30.0):
    """Loud body with quiet intro/outro: the loudest-pieces selection must
    ignore the edges when measuring the target spectrum."""
    n = int(sr * seconds)
    t = np.linspace(0, seconds, n, endpoint=False)
    body = 0.3 * np.sin(2 * np.pi * 220.0 * t)
    quiet = 0.01 * np.sin(2 * np.pi * 220.0 * t)
    mono = np.concatenate([quiet[: n // 6], body, quiet[: n // 6]])
    return _stereo(mono[:n].astype(np.float32))


# ---------------------------------------------------------------------------
# OFF path: byte-identical to the legacy implementation
# ---------------------------------------------------------------------------

def test_off_path_byte_identical_to_legacy():
    sr = 44100
    mix = _stereo(_tone(200, sr) + 0.05 * _tone(6000, sr))
    ref = _stereo(_tone(200, sr) + 0.3 * _tone(6000, sr))

    config.set_override("ENABLE_LTAS_V2", False)
    out, report = match_ltas(mix, sr, ref, sr)

    # Legacy reference: the exact same call sequence the old body performed.
    from redline.ltas import compute_ltas, compute_delta_curve, design_fir, apply_fir
    mix_freqs, mix_db = compute_ltas(mix, sr)
    ref_freqs, ref_db = compute_ltas(ref, sr)
    delta_db = compute_delta_curve(mix_freqs, mix_db, ref_freqs, ref_db, 2.5)
    fir = design_fir(delta_db, mix_freqs, sr, 256)
    legacy = apply_fir(mix, fir)

    assert np.array_equal(out, legacy)
    assert report["max_delta_db"] == 2.5
    assert report["fir_taps"] == 256
    assert "pieces_used" not in report


# ---------------------------------------------------------------------------
# ON path: new pipeline
# ---------------------------------------------------------------------------

def test_on_path_shape_dtype_and_report_keys():
    sr = 44100
    mix = _stereo(_tone(200, sr) + 0.05 * _tone(6000, sr))
    ref = _stereo(_tone(200, sr) + 0.3 * _tone(6000, sr))

    config.set_override("ENABLE_LTAS_V2", True)
    out, report = match_ltas(mix, sr, ref, sr)

    assert out.shape == mix.shape
    assert out.dtype == np.float32
    assert not np.isnan(out).any()
    # legacy keys preserved
    assert report["max_delta_db"] == 2.5
    assert report["fir_taps"] == 256
    assert "applied_delta_db_range" in report
    # new keys
    assert "pieces_used" in report
    assert "mid_side" in report
    assert "lowess_frac" in report


def test_on_path_tonal_delta_no_worse_than_legacy():
    """Mean |dB| distance between matched and reference LTAS must not be
    worse than what the legacy path achieves on the same material."""
    sr = 44100
    mix = _stereo(_tone(200, sr) + 0.05 * _tone(6000, sr))
    ref = _stereo(_tone(200, sr) + 0.3 * _tone(6000, sr))

    from redline.ltas import compute_ltas

    def tonal_distance(out):
        f1, db1 = compute_ltas(out, sr)
        f2, db2 = compute_ltas(ref, sr)
        return float(np.mean(np.abs(np.interp(f1, f2, db2) - db1)))

    config.set_override("ENABLE_LTAS_V2", False)
    legacy_out, _ = match_ltas(mix, sr, ref, sr)
    config.set_override("ENABLE_LTAS_V2", True)
    v2_out, _ = match_ltas(mix, sr, ref, sr)

    d_legacy = tonal_distance(legacy_out)
    d_v2 = tonal_distance(v2_out)
    assert d_v2 <= d_legacy + 0.5, f"v2 {d_v2:.3f} dB vs legacy {d_legacy:.3f} dB"


def test_on_path_preserves_loudness_within_half_db():
    sr = 44100
    mix = _stereo(_tone(200, sr) + 0.05 * _tone(6000, sr))
    ref = _stereo(_tone(200, sr) + 0.3 * _tone(6000, sr))

    config.set_override("ENABLE_LTAS_V2", True)
    out, _ = match_ltas(mix, sr, ref, sr)

    rms_in = float(np.sqrt(np.mean(mix.astype(np.float64) ** 2)))
    rms_out = float(np.sqrt(np.mean(out.astype(np.float64) ** 2)))
    assert abs(20 * np.log10(rms_out / rms_in)) < 0.5


def test_on_path_loudest_pieces_ignore_quiet_edges():
    """With quiet intro/outro, the v2 spectrum must be measured on the loud
    body: pieces_used must be reported and the applied delta must stay
    clamped (guard active)."""
    sr = 44100
    mix = _signal_with_quiet_edges(sr)
    ref = _stereo(_tone(200, sr) + 0.3 * _tone(6000, sr))

    config.set_override("ENABLE_LTAS_V2", True)
    out, report = match_ltas(mix, sr, ref, sr)

    assert out.shape == mix.shape
    assert report["pieces_used"] >= 1
    lo, hi = report["applied_delta_db_range"]
    assert lo >= -2.5 - 1e-6
    assert hi <= 2.5 + 1e-6


# ---------------------------------------------------------------------------
# Fail-safe: broken reference never raises
# ---------------------------------------------------------------------------

def test_failsafe_empty_reference_returns_input_unchanged():
    sr = 44100
    mix = _stereo(_tone(200, sr))
    ref = np.zeros((0, 2), dtype=np.float32)

    config.set_override("ENABLE_LTAS_V2", True)
    out, report = match_ltas(mix, sr, ref, sr)
    assert np.array_equal(out, mix)
    assert report == {}


def test_failsafe_nan_reference_returns_input_unchanged():
    sr = 44100
    mix = _stereo(_tone(200, sr))
    ref = _stereo(_tone(200, sr))
    ref[0, 0] = np.nan

    config.set_override("ENABLE_LTAS_V2", True)
    out, report = match_ltas(mix, sr, ref, sr)
    assert np.array_equal(out, mix)
    assert report == {}