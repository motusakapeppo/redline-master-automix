"""Tests for batch processing: project discovery, per-project pipeline
execution, error isolation, and report generation."""

from __future__ import annotations

import json
import os
import tempfile

import numpy as np
import soundfile as sf

from redline.batch import BatchProcessor, _find_projects


def _make_synthetic_audio(path: str, sr: int = 44100, seconds: float = 2.0) -> str:
    """Write a short synthetic stereo audio file and return its path."""
    n = int(sr * seconds)
    rng = np.random.default_rng(42)
    data = 0.1 * rng.standard_normal((n, 2)).astype(np.float32)
    sf.write(path, data, sr)
    return path


def _make_project_dir(parent: str, name: str, num_stems: int = 2) -> str:
    """Create a project subdirectory with synthetic stem files."""
    proj_dir = os.path.join(parent, name)
    os.makedirs(proj_dir, exist_ok=True)
    for i in range(num_stems):
        path = os.path.join(proj_dir, f"stem_{i}.wav")
        _make_synthetic_audio(path)
    return proj_dir


def test_find_projects_detects_audio_subdirs():
    """_find_projects should return only subdirectories that contain audio."""
    with tempfile.TemporaryDirectory() as tmp:
        _make_project_dir(tmp, "song_a")
        _make_project_dir(tmp, "song_b")
        empty_dir = os.path.join(tmp, "empty")
        os.makedirs(empty_dir, exist_ok=True)
        # A file (not a dir) should be ignored
        with open(os.path.join(tmp, "notes.txt"), "w") as f:
            f.write("not a project")

        projects = _find_projects(tmp)
        assert "song_a" in projects
        assert "song_b" in projects
        assert "empty" not in projects
        assert "notes.txt" not in projects
        assert len(projects) == 2


def test_find_projects_empty_dir():
    """_find_projects should return empty list for a dir with no audio projects."""
    with tempfile.TemporaryDirectory() as tmp:
        projects = _find_projects(tmp)
        assert projects == []


def test_find_projects_nonexistent_dir():
    """_find_projects should raise on nonexistent directory."""
    import pytest

    with pytest.raises(ValueError, match="not found"):
        _find_projects("/nonexistent/path/xyz")


def test_batch_processor_runs_and_returns_results():
    """BatchProcessor.run() should process all projects and return results."""
    logs: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        batch_dir = os.path.join(tmp, "batch")
        out_dir = os.path.join(tmp, "out")
        os.makedirs(batch_dir)

        _make_project_dir(batch_dir, "proj_a", num_stems=3)
        _make_project_dir(batch_dir, "proj_b", num_stems=2)

        processor = BatchProcessor(on_step=logs.append)
        results = processor.run(batch_dir, out_dir)

        assert len(results) == 2
        for r in results:
            assert r["ok"] is True
            assert r["error"] is None
            assert r["mix_path"] is not None
            assert os.path.exists(r["mix_path"])
            assert r["duration_sec"] > 0

        # Check report file
        report_path = os.path.join(out_dir, "batch_report.json")
        assert os.path.exists(report_path)
        with open(report_path) as f:
            report = json.load(f)
        assert report["total_projects"] == 2
        assert report["successes"] == 2
        assert report["failures"] == 0


def test_batch_report_contains_all_projects():
    """The JSON report should contain all project results."""
    with tempfile.TemporaryDirectory() as tmp:
        batch_dir = os.path.join(tmp, "batch")
        out_dir = os.path.join(tmp, "out")
        os.makedirs(batch_dir)

        _make_project_dir(batch_dir, "alpha")
        _make_project_dir(batch_dir, "beta")
        _make_project_dir(batch_dir, "gamma")

        processor = BatchProcessor()
        processor.run(batch_dir, out_dir)

        report_path = os.path.join(out_dir, "batch_report.json")
        with open(report_path) as f:
            report = json.load(f)

        project_names = {r["project"] for r in report["results"]}
        assert project_names == {"alpha", "beta", "gamma"}


def test_batch_continues_on_project_failure():
    """A failing project should not block subsequent projects."""
    logs: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        batch_dir = os.path.join(tmp, "batch")
        out_dir = os.path.join(tmp, "out")
        os.makedirs(batch_dir)

        # Valid project
        _make_project_dir(batch_dir, "good_project", num_stems=2)

        # Invalid project: corrupt audio file that will fail during processing
        bad_dir = os.path.join(batch_dir, "bad_project")
        os.makedirs(bad_dir, exist_ok=True)
        bad_path = os.path.join(bad_dir, "corrupt.wav")
        with open(bad_path, "wb") as f:
            f.write(b"not a real wav file at all")

        # Another valid project
        _make_project_dir(batch_dir, "another_good", num_stems=2)

        processor = BatchProcessor(on_step=logs.append)
        results = processor.run(batch_dir, out_dir)

        assert len(results) == 3

        good_results = [r for r in results if r["ok"]]
        bad_results = [r for r in results if not r["ok"]]

        assert len(good_results) == 2
        assert len(bad_results) == 1
        assert bad_results[0]["project"] == "bad_project"
        assert bad_results[0]["error"] is not None

        # Check report reflects failures
        report_path = os.path.join(out_dir, "batch_report.json")
        with open(report_path) as f:
            report = json.load(f)
        assert report["successes"] == 2
        assert report["failures"] == 1


def test_batch_processor_empty_batch_dir():
    """BatchProcessor.run() should return empty list for dir with no projects."""
    logs: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        batch_dir = os.path.join(tmp, "batch")
        out_dir = os.path.join(tmp, "out")
        os.makedirs(batch_dir)

        processor = BatchProcessor(on_step=logs.append)
        results = processor.run(batch_dir, out_dir)
        assert results == []
