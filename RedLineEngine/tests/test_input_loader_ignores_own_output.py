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


def test_ignores_prefixed_reference_master_bounce(tmp_path):
    # Confirmed with a real FL Studio project export: a pre-mixed reference
    # bounce named "SONGNAME (Autotune) - _Master.wav" sitting right next to
    # the real stems in the same folder. The old exact-basename check only
    # caught a file literally named "master.wav" -- this one slipped through
    # and got summed into the render as if it were one more instrumental
    # layer, a real and severe cause of an unbalanced/muddy result.
    _write_tone(tmp_path / "BAGDAD (Autotune) - _Main - Ritornello.wav", freq=440.0)
    _write_tone(tmp_path / "BAGDAD (Autotune) - _Double - Rap dx.wav", freq=445.0)
    _write_tone(tmp_path / "BAGDAD (Autotune) - _Beat.wav", freq=110.0)
    _write_tone(tmp_path / "BAGDAD (Autotune) - _Master.wav", freq=990.0)

    stems = load_stems_dir(str(tmp_path))

    assert len(stems.names()) == 3
    assert not any("master" in name.lower() for name in stems.names())
