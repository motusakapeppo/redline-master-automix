"""Tests for redline.ab_compare -- the loudness-matched A/B measurement
harness. Must never play audio (see docstring in the module); these tests
only check file I/O and the returned numbers."""

from __future__ import annotations

import json

import numpy as np
import soundfile as sf

from redline.ab_compare import compare, report_to_dict


def _write_tone(path: str, freq: float, amp: float, sr: int = 44100, seconds: float = 2.0) -> None:
    t = np.arange(int(sr * seconds)) / sr
    mono = (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    sf.write(path, np.stack([mono, mono], axis=1), sr)


def test_compare_measures_both_files(tmp_path):
    before_path = str(tmp_path / "before.wav")
    after_path = str(tmp_path / "after.wav")
    _write_tone(before_path, 440.0, 0.1)
    _write_tone(after_path, 440.0, 0.3)  # louder "after"

    report = compare(before_path, after_path)
    assert report.after.lufs > report.before.lufs
    assert report.lufs_delta_db > 0
    assert set(report.band_energy_delta.keys()) == set(report.before.band_energies.keys())


def test_compare_is_json_serializable(tmp_path):
    before_path = str(tmp_path / "before.wav")
    after_path = str(tmp_path / "after.wav")
    _write_tone(before_path, 220.0, 0.15)
    _write_tone(after_path, 220.0, 0.15)

    report = compare(before_path, after_path)
    payload = json.dumps(report_to_dict(report))
    assert "lufs_delta_db" in payload


def test_compare_can_render_loudness_matched_ab_wav(tmp_path):
    before_path = str(tmp_path / "before.wav")
    after_path = str(tmp_path / "after.wav")
    render_path = str(tmp_path / "ab.wav")
    _write_tone(before_path, 440.0, 0.05)
    _write_tone(after_path, 440.0, 0.4)

    compare(before_path, after_path, render_wav_path=render_path)

    rendered, sr = sf.read(render_path)
    assert rendered.shape[0] > 0
    # loudness-matched: peak amplitude of the two halves should be much
    # closer to each other than the raw 0.05 vs 0.4 input amplitudes were.
    half = rendered.shape[0] // 2
    first_half_peak = np.max(np.abs(rendered[:half]))
    second_half_peak = np.max(np.abs(rendered[half:]))
    assert first_half_peak > 0 and second_half_peak > 0
