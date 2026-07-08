"""Tests for input_loader._drop_fully_silent: stems that are exact digital
silence (every sample 0.0 -- a broken/empty bounce, confirmed on real
material: 6 exported stems that were 100% zero across the whole file) are
dropped at load time instead of being carried through the full pipeline."""

from __future__ import annotations

import os

import numpy as np
import soundfile as sf

from redline.input_loader import load_stems_dir


def _write_wav(path: str, data: np.ndarray, sr: int = 44100) -> None:
    sf.write(path, data, sr)


def test_fully_silent_stem_is_dropped(tmp_path):
    sr = 44100
    n = sr * 2
    real = 0.2 * np.sin(2 * np.pi * 220.0 * np.arange(n) / sr)
    real_stereo = np.stack([real, real], axis=1).astype(np.float32)
    silent_stereo = np.zeros((n, 2), dtype=np.float32)

    _write_wav(str(tmp_path / "real_instrument.wav"), real_stereo, sr)
    _write_wav(str(tmp_path / "broken_bounce.wav"), silent_stereo, sr)

    stems = load_stems_dir(str(tmp_path))

    assert "real_instrument" in stems.tracks
    assert "broken_bounce" not in stems.tracks


def test_near_silent_but_nonzero_stem_is_kept(tmp_path):
    sr = 44100
    n = sr * 2
    quiet = (1e-6 * np.sin(2 * np.pi * 220.0 * np.arange(n) / sr)).astype(np.float32)
    quiet_stereo = np.stack([quiet, quiet], axis=1)

    _write_wav(str(tmp_path / "very_quiet_but_real.wav"), quiet_stereo, sr)

    stems = load_stems_dir(str(tmp_path))

    assert "very_quiet_but_real" in stems.tracks


def test_all_stems_silent_raises_clear_error(tmp_path):
    sr = 44100
    n = sr * 2
    silent_stereo = np.zeros((n, 2), dtype=np.float32)
    _write_wav(str(tmp_path / "a.wav"), silent_stereo, sr)
    _write_wav(str(tmp_path / "b.wav"), silent_stereo, sr)

    try:
        load_stems_dir(str(tmp_path))
        assert False, "expected ValueError for an all-silent stem folder"
    except ValueError as e:
        assert "silenzio" in str(e).lower()
