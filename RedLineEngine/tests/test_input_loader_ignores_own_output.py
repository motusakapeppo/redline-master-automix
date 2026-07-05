"""Confirmed-in-practice bug: running the pipeline with an output folder
nested inside the input project (a very natural thing to do) meant the next
run picked up the previous mix.wav/master.wav as if they were extra input
stems and summed them into the new render. Must never happen."""

import numpy as np
import soundfile as sf

from redline.input_loader import load_stems_dir, load_auto


def _write_tone(path, sr=44100, seconds=1.0, freq=220.0):
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    tone = (0.2 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    sf.write(path, np.stack([tone, tone], axis=1), sr)


def test_load_stems_dir_ignores_mix_and_master_wav(tmp_path):
    _write_tone(tmp_path / "vocals.wav", freq=440.0)
    _write_tone(tmp_path / "instrumental.wav", freq=110.0)

    output_dir = tmp_path / "previous output"
    output_dir.mkdir()
    _write_tone(output_dir / "mix.wav", freq=990.0)
    _write_tone(output_dir / "master.wav", freq=995.0)

    stems = load_stems_dir(str(tmp_path))

    assert len(stems.names()) == 2
    assert not any("mix" in name.lower() or "master" in name.lower() for name in stems.names())


def test_load_auto_ignores_mix_and_master_wav(tmp_path):
    _write_tone(tmp_path / "vocals.wav", freq=440.0)
    _write_tone(tmp_path / "instrumental.wav", freq=110.0)

    output_dir = tmp_path / "previous output"
    output_dir.mkdir()
    _write_tone(output_dir / "mix.wav", freq=990.0)
    _write_tone(output_dir / "master.wav", freq=995.0)

    stems = load_auto(str(tmp_path))

    assert len(stems.names()) == 2
