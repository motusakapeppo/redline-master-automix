"""Flag-gated QC v2 measurements (ENABLE_QC_V2).

With the flag OFF the QcReport must be exactly what it was before: the new
fields stay None and the existing sample-peak true_peak_db is used unchanged.
With the flag ON the report gains additive measurements (4x-oversampled true
peak, LRA, DC offset, stereo correlation) without touching any existing one.
"""

from __future__ import annotations

import numpy as np
import pytest

from redline import config
from redline.qc import run_qc


def _make_noise(sr: int, seconds: float = 3.0, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(sr * seconds)
    mono = rng.normal(0, 0.1, n).astype(np.float32)
    return np.stack([mono, mono], axis=1)


# --- OFF path: report identical to before -----------------------------------

def test_qc_v2_off_new_fields_are_none():
    config.set_override("ENABLE_QC_V2", False)
    sr = 44100
    signal = _make_noise(sr, seed=1)
    _, report = run_qc(signal, sr, "Pop / Rock", target_lufs=-14.0, true_peak_ceiling_db=-1.0)

    assert report.true_peak_isp_db is None
    assert report.lra is None
    assert report.dc_offset is None
    assert report.stereo_correlation is None


def test_qc_v2_off_true_peak_is_sample_peak():
    config.set_override("ENABLE_QC_V2", False)
    sr = 44100
    signal = _make_noise(sr, seed=1)
    _, report = run_qc(signal, sr, "Pop / Rock", target_lufs=-14.0, true_peak_ceiling_db=-1.0)

    # The QC loop may correct/trim the signal, so the reported peak is the
    # sample peak of the FINAL (returned) audio, not of the input.
    corrected, _ = run_qc(signal, sr, "Pop / Rock", target_lufs=-14.0, true_peak_ceiling_db=-1.0)
    expected = 20.0 * np.log10(np.max(np.abs(corrected)) + 1e-12)
    assert float(report.true_peak_db) == pytest.approx(expected, abs=1e-9)


# --- ON path: additive measurements ------------------------------------------

def test_qc_v2_on_true_peak_isp_at_least_sample_peak():
    config.set_override("ENABLE_QC_V2", True)
    try:
        sr = 44100
        signal = _make_noise(sr, seed=1)
        _, report = run_qc(signal, sr, "Pop / Rock", target_lufs=-14.0, true_peak_ceiling_db=-1.0)

        assert report.true_peak_isp_db is not None
        assert report.true_peak_isp_db >= float(report.true_peak_db) - 1e-6
    finally:
        config.set_override("ENABLE_QC_V2", False)


def test_qc_v2_on_lra_non_negative():
    config.set_override("ENABLE_QC_V2", True)
    try:
        sr = 44100
        signal = _make_noise(sr, seed=1)
        _, report = run_qc(signal, sr, "Pop / Rock", target_lufs=-14.0, true_peak_ceiling_db=-1.0)

        assert report.lra is not None
        assert report.lra >= 0.0
    finally:
        config.set_override("ENABLE_QC_V2", False)


def test_qc_v2_on_dc_offset_and_stereo_correlation_present():
    config.set_override("ENABLE_QC_V2", True)
    try:
        sr = 44100
        signal = _make_noise(sr, seed=1)
        _, report = run_qc(signal, sr, "Pop / Rock", target_lufs=-14.0, true_peak_ceiling_db=-1.0)

        assert report.dc_offset is not None
        assert report.stereo_correlation is not None
        assert -1.0 <= report.stereo_correlation <= 1.0
    finally:
        config.set_override("ENABLE_QC_V2", False)


def test_qc_v2_on_report_json_serializable():
    """All QcReport fields (old + new) must survive _sanitize_for_json and
    json.dumps — the report feeds the webview bridge and the JSON file."""
    import json

    from app.api import _sanitize_for_json

    config.set_override("ENABLE_QC_V2", True)
    try:
        sr = 44100
        signal = _make_noise(sr, seed=1)
        _, report = run_qc(signal, sr, "Pop / Rock", target_lufs=-14.0, true_peak_ceiling_db=-1.0)

        payload = _sanitize_for_json(vars(report))
        json.dumps(payload)  # must not raise
    finally:
        config.set_override("ENABLE_QC_V2", False)


def test_qc_v2_on_existing_metrics_unchanged():
    """The v2 measurements are additive: existing fields keep their values."""
    config.set_override("ENABLE_QC_V2", True)
    try:
        sr = 44100
        signal = _make_noise(sr, seed=1)
        _, report_on = run_qc(signal, sr, "Pop / Rock", target_lufs=-14.0, true_peak_ceiling_db=-1.0)
    finally:
        config.set_override("ENABLE_QC_V2", False)

    config.set_override("ENABLE_QC_V2", False)
    _, report_off = run_qc(signal, sr, "Pop / Rock", target_lufs=-14.0, true_peak_ceiling_db=-1.0)

    assert report_on.lufs == report_off.lufs
    assert float(report_on.true_peak_db) == float(report_off.true_peak_db)
    assert report_on.mono_compatibility == report_off.mono_compatibility
    assert report_on.bass_phase_shift_deg == report_off.bass_phase_shift_deg
    assert report_on.band_deviations == report_off.band_deviations
    assert report_on.passed is report_off.passed