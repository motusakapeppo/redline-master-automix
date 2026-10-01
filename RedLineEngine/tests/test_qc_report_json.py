"""Flag-gated QC report serialization (ENABLE_QC_REPORT_JSON).

With the flag ON the final QcReport is written to <out_dir>/qc_report.json
with resolved targets, measured values, per-band deviations and the list of
corrections applied. With the flag OFF no file is written and nothing else
changes.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from redline import config
from redline.qc import run_qc


def _make_noise(sr: int, seconds: float = 3.0, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(sr * seconds)
    mono = rng.normal(0, 0.1, n).astype(np.float32)
    return np.stack([mono, mono], axis=1)


def _analysis_for(genre_name: str):
    from redline.analyze import AnalysisResult
    from redline.analysis.genre import GenreProfile

    return AnalysisResult(
        bpm=120.0,
        key_tonic="A",
        key_mode="minor",
        key_confidence=1.0,
        genre=GenreProfile(
            name=genre_name, bus_eq=[], attack_ms=10.0, release_ms=100.0,
            ratio=2.0, threshold_db=-18.0, parallel_mix=0.2,
        ),
        mix_lufs=-20.0,
        mix_crest=10.0,
        mix_sub_bass_ratio=0.2,
        transient_density=0.5,
        stems={},
    )


# --- run_qc optional out_dir --------------------------------------------------

def test_run_qc_writes_json_report(tmp_path):
    config.set_override("ENABLE_QC_REPORT_JSON", True)
    try:
        sr = 44100
        signal = _make_noise(sr, seed=1)
        out_dir = tmp_path / "master"
        out_dir.mkdir()
        _, report = run_qc(
            signal, sr, "Pop / Rock", target_lufs=-14.0, true_peak_ceiling_db=-1.0,
            out_dir=str(out_dir),
        )

        path = out_dir / "qc_report.json"
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))

        assert data["measured"]["lufs"] == pytest.approx(report.lufs, abs=1e-6)
        assert data["measured"]["true_peak_db"] == pytest.approx(float(report.true_peak_db), abs=1e-6)
        assert data["targets"]["target_lufs"] == -14.0
        assert data["targets"]["true_peak_ceiling_db"] == -1.0
        assert set(data["band_deviations"].keys()) == set(report.band_deviations.keys())
        assert isinstance(data["corrections"], list)
        for entry in data["corrections"]:
            assert set(entry.keys()) == {"reason", "measured", "target", "applied"}
    finally:
        config.set_override("ENABLE_QC_REPORT_JSON", False)


def test_run_qc_no_json_without_out_dir(tmp_path):
    """Flag ON but no out_dir passed -> no file written, no crash."""
    config.set_override("ENABLE_QC_REPORT_JSON", True)
    try:
        sr = 44100
        signal = _make_noise(sr, seed=1)
        _, report = run_qc(signal, sr, "Pop / Rock", target_lufs=-14.0, true_peak_ceiling_db=-1.0)

        assert report is not None
        # Nothing was written anywhere unexpected: the tmp_path stays empty.
        assert list(tmp_path.iterdir()) == []
    finally:
        config.set_override("ENABLE_QC_REPORT_JSON", False)


def test_run_qc_flag_off_no_json_file(tmp_path):
    config.set_override("ENABLE_QC_REPORT_JSON", False)
    sr = 44100
    signal = _make_noise(sr, seed=1)
    out_dir = tmp_path / "master"
    out_dir.mkdir()
    _, report = run_qc(
        signal, sr, "Pop / Rock", target_lufs=-14.0, true_peak_ceiling_db=-1.0,
        out_dir=str(out_dir),
    )

    assert report is not None
    assert not (out_dir / "qc_report.json").exists()


# --- render_master optional out_dir -------------------------------------------

def test_render_master_writes_json_report(tmp_path):
    from redline.masterengine import render_master

    config.set_override("ENABLE_QC_REPORT_JSON", True)
    try:
        sr = 44100
        n = int(sr * 2.0)
        t = np.arange(n) / sr
        mono = (0.2 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)
        signal = np.stack([mono, mono], axis=1)
        analysis = _analysis_for("Pop / Rock")

        out_dir = tmp_path / "master"
        out_dir.mkdir()
        render_master(signal, sr, analysis, out_dir=str(out_dir))

        path = out_dir / "qc_report.json"
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "measured" in data and "targets" in data
        assert data["targets"]["target_lufs"] == pytest.approx(-14.0, abs=0.6)
    finally:
        config.set_override("ENABLE_QC_REPORT_JSON", False)


def test_render_master_flag_off_no_json_file(tmp_path):
    from redline.masterengine import render_master

    config.set_override("ENABLE_QC_REPORT_JSON", False)
    sr = 44100
    n = int(sr * 2.0)
    t = np.arange(n) / sr
    mono = (0.2 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)
    signal = np.stack([mono, mono], axis=1)
    analysis = _analysis_for("Pop / Rock")

    out_dir = tmp_path / "master"
    out_dir.mkdir()
    render_master(signal, sr, analysis, out_dir=str(out_dir))

    assert not (out_dir / "qc_report.json").exists()