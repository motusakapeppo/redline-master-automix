import os

import numpy as np

from redline.input_loader import Stems
from redline.analyze import analyze
from redline.wizard import MixPreferences
from redline.mixengine import render_mix
from redline.bus_exporter import export_buses, BusExports


def _make_synthetic_stems(sr: int = 44100, seconds: float = 2.0) -> Stems:
    n = int(sr * seconds)
    t = np.linspace(0, seconds, n, endpoint=False)
    rng = np.random.default_rng(7)

    vocals = 0.2 * np.sin(2 * np.pi * 440.0 * t)
    bass = 0.3 * np.sin(2 * np.pi * 80.0 * t)
    drums = 0.15 * rng.standard_normal(n)
    other = 0.2 * np.sin(2 * np.pi * 220.0 * t) + 0.05 * rng.standard_normal(n)

    def stereo(mono):
        return np.stack([mono, mono], axis=1).astype(np.float32)

    return Stems(
        sample_rate=sr,
        tracks={
            "vocals": stereo(vocals),
            "bass": stereo(bass),
            "drums": stereo(drums),
            "other": stereo(other),
        },
    )


def test_export_buses_returns_all_buses():
    stems = _make_synthetic_stems()
    analysis = analyze(stems)
    prefs = MixPreferences()

    buses = export_buses(stems, analysis, prefs)
    assert isinstance(buses, BusExports)
    assert buses.full_mix is not None
    # These synthetic stems include vocals, drums and "other" -> vocal_main,
    # parallel and music buses are expected to be populated.
    assert buses.vocal_main is not None
    assert buses.music is not None


def test_vocal_bus_contains_vocals_only():
    stems = _make_synthetic_stems()
    analysis = analyze(stems)
    prefs = MixPreferences()

    buses = export_buses(stems, analysis, prefs)
    assert buses.vocal_main is not None
    assert np.max(np.abs(buses.vocal_main)) > 0.0


def test_music_bus_contains_instruments_only():
    stems = _make_synthetic_stems()
    analysis = analyze(stems)
    prefs = MixPreferences()

    buses = export_buses(stems, analysis, prefs)
    assert buses.music is not None
    assert np.max(np.abs(buses.music)) > 0.0


def test_callback_receives_correct_bus_names():
    stems = _make_synthetic_stems()
    analysis = analyze(stems)
    prefs = MixPreferences()

    received = {}

    def _capture(name, audio):
        received[name] = audio

    render_mix(stems, analysis, prefs, on_bus_ready=_capture)

    assert set(received.keys()) <= {"vocal_main", "vocal_doubles", "music", "parallel", "reverb"}
    for audio in received.values():
        assert audio.ndim == 2
        assert audio.shape[1] == 2


def test_full_mix_unchanged_by_callback():
    stems = _make_synthetic_stems()
    analysis = analyze(stems)
    prefs = MixPreferences()

    mix_without_callback = render_mix(stems, analysis, prefs)
    mix_with_callback = render_mix(stems, analysis, prefs, on_bus_ready=lambda n, a: None)

    assert np.array_equal(mix_without_callback, mix_with_callback)


def test_export_buses_flag_cli(tmp_path):
    import subprocess
    import sys
    import soundfile as sf

    sr = 44100
    seconds = 1.0
    n = int(sr * seconds)
    t = np.linspace(0, seconds, n, endpoint=False)
    vocals = (0.2 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)
    instrumental = (0.2 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)

    def stereo(mono):
        return np.stack([mono, mono], axis=1)

    vocals_path = os.path.join(tmp_path, "vocals.wav")
    instrumental_path = os.path.join(tmp_path, "instrumental.wav")
    sf.write(vocals_path, stereo(vocals), sr)
    sf.write(instrumental_path, stereo(instrumental), sr)

    out_dir = os.path.join(tmp_path, "out")
    result = subprocess.run(
        [
            sys.executable, "-m", "redline.cli",
            "--vocals", vocals_path,
            "--instrumental", instrumental_path,
            "--out", out_dir,
            "--non-interactive",
            "--export-buses",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert os.path.exists(os.path.join(out_dir, "mix.wav"))
    assert os.path.exists(os.path.join(out_dir, "vocal_main.wav"))
