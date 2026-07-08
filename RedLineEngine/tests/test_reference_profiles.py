"""Tests for redline.reference_profiles: the batch builder that scans
reference_tracks/<genre_slug>/ and writes measured target JSONs."""

from __future__ import annotations

import os

import numpy as np
import soundfile as sf

from redline.reference_profiles import build_all, MIN_TRACKS_FOR_PROFILE
from redline.targets import target_path


def _write_tone(path: str, freq: float, sr: int = 44100, seconds: float = 2.0) -> None:
    t = np.arange(int(sr * seconds)) / sr
    mono = (0.3 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    sf.write(path, np.stack([mono, mono], axis=1), sr)


def test_build_all_skips_folders_below_minimum_track_count(tmp_path):
    folder = tmp_path / "edm_urban"
    folder.mkdir()
    _write_tone(str(folder / "a.wav"), 440.0)  # only 1 file, below MIN_TRACKS_FOR_PROFILE
    built = build_all(str(tmp_path))
    assert built == {}


def test_build_all_profiles_folder_with_enough_tracks(tmp_path, monkeypatch):
    folder = tmp_path / "edm_urban"
    folder.mkdir()
    for i in range(MIN_TRACKS_FOR_PROFILE):
        _write_tone(str(folder / f"track{i}.wav"), 200.0 + i * 50)

    # Redirect where the built JSON gets written so this test doesn't touch
    # the real redline/targets/ directory.
    fake_targets_dir = tmp_path / "targets_out"
    monkeypatch.setattr("redline.reference_profiles.TARGETS_DIR", str(fake_targets_dir))
    monkeypatch.setattr("redline.reference_profiles.target_path", lambda genre: os.path.join(str(fake_targets_dir), "target_edm_urban.json"))

    built = build_all(str(tmp_path))
    assert "EDM / Urban" in built
    assert built["EDM / Urban"]["n_tracks"] == MIN_TRACKS_FOR_PROFILE
    assert os.path.exists(os.path.join(str(fake_targets_dir), "target_edm_urban.json"))


def test_build_all_returns_empty_when_no_reference_tracks_dir(tmp_path):
    missing = tmp_path / "does_not_exist"
    built = build_all(str(missing))
    assert built == {}
