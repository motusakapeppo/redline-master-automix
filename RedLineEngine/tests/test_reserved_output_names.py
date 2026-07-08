"""Tests for input_loader._is_reserved_output: files that are a bounce of
the whole finished track (not an individual stem) must be excluded from
loading, so they never get summed in as if they were one more instrumental
layer. Covers the original "mix"/"master" convention plus common DAW export
names like "STEREO OUT", "mixdown", "premaster", and multi-word phrases."""

from __future__ import annotations

import numpy as np
import soundfile as sf

from redline.input_loader import _is_reserved_output, load_stems_dir


def test_recognizes_common_full_mix_bounce_names():
    reserved = [
        "STEREO OUT",
        "Stereo_Out (2)",
        "Stereo-Out",
        "SONGNAME - _Master",
        "Full Mix Reference",
        "Mixdown v2",
        "Premaster",
        "Rough Mix",
        "Bounce final",
        "mix",
        "master",
    ]
    for name in reserved:
        assert _is_reserved_output(name), f"expected '{name}' to be recognized as a full-mix bounce"


def test_does_not_reject_real_instrument_names():
    real_instruments = [
        "Mixolydian Pad",
        "Outro FX",
        "Callout Vox",
        "Kick 01",
        "Strings",
    ]
    for name in real_instruments:
        assert not _is_reserved_output(name), f"'{name}' should not be treated as a reserved output name"


def test_stereo_out_bounce_is_excluded_from_loaded_stems(tmp_path):
    sr = 44100
    n = sr * 2
    real = (0.2 * np.sin(2 * np.pi * 220.0 * np.arange(n) / sr)).astype(np.float32)
    real_stereo = np.stack([real, real], axis=1)

    sf.write(str(tmp_path / "Lead Vocal.wav"), real_stereo, sr)
    sf.write(str(tmp_path / "STEREO OUT.wav"), real_stereo, sr)

    stems = load_stems_dir(str(tmp_path))

    assert "Lead Vocal" in stems.tracks
    assert "STEREO OUT" not in stems.tracks
