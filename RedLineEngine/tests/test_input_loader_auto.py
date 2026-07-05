"""load_auto must pick the right mode without the caller having to know the
folder layout in advance — this is what the CLI's --folder option relies on."""

import numpy as np
import soundfile as sf

from redline.input_loader import load_auto


def _write_tone(path, sr=44100, seconds=1.0, freq=220.0):
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    tone = (0.2 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    stereo = np.stack([tone, tone], axis=1)
    sf.write(path, stereo, sr)


def test_folder_with_instrumental_and_vocal_subfolder_uses_stems_mode(tmp_path):
    (tmp_path / "SONG - INSTRUMENTAL.wav")
    _write_tone(tmp_path / "SONG - INSTRUMENTAL.wav", freq=110.0)

    vocals_dir = tmp_path / "vocals stems"
    vocals_dir.mkdir()
    _write_tone(vocals_dir / "Main - Str1.wav", freq=440.0)
    _write_tone(vocals_dir / "Double - Str1 dx.wav", freq=445.0)

    stems = load_auto(str(tmp_path))

    assert len(stems.names()) == 3
    assert any("vocals stems" in name for name in stems.names())
