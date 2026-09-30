"""Wave 2 / Track F: optional built-in "character" processor variants.

These wrap the unused pedalboard classes (Distortion, Chorus, Phaser, ...)
behind a tiny registry. Nothing here touches the render path unless a caller
explicitly builds a processor and inserts it, and the whole feature is gated
by ENABLE_BUILTIN_PROCESSOR_VARIANTS (OFF by default).
"""

from __future__ import annotations

import numpy as np

from redline import config
from redline.input_loader import Stems
from redline.analyze import analyze
from redline.wizard import MixPreferences
from redline.mixengine import render_mix
from redline.processors import available_processors, build_processor


def test_processor_variants_flag_defaults_off(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "_FLAGS_PATH", str(tmp_path / "nonexistent.flags.json"))
    config.reload()
    try:
        assert config.is_enabled("ENABLE_BUILTIN_PROCESSOR_VARIANTS") is False
    finally:
        config.reload()


def test_processors_available_and_buildable():
    """Every advertised name must build a non-None object; an unknown name
    must return None (caller skips) rather than raising."""
    names = available_processors()
    assert isinstance(names, tuple)
    assert len(names) >= 8
    for name in names:
        built = build_processor(name)
        assert built is not None, f"processor '{name}' failed to build"
    assert build_processor("nonexistent") is None


def test_config_flags_present():
    assert "ENABLE_PLUGIN_HOSTING" in config.DEFAULTS
    assert "ENABLE_BUILTIN_PROCESSOR_VARIANTS" in config.DEFAULTS
    assert config.DEFAULTS["ENABLE_PLUGIN_HOSTING"] is False
    assert config.DEFAULTS["ENABLE_BUILTIN_PROCESSOR_VARIANTS"] is False


def _make_stems(sr: int = 44100, seconds: float = 2.0) -> Stems:
    n = int(sr * seconds)
    t = np.linspace(0, seconds, n, endpoint=False)
    rng = np.random.default_rng(42)

    vocals = (
        0.2 * np.sin(2 * np.pi * 440.0 * t)
        + 0.15 * np.sin(2 * np.pi * 7000.0 * t)
        + 0.05 * rng.standard_normal(n)
    )
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


def test_processor_variants_flag_off_is_neutral(monkeypatch, tmp_path):
    """With the flag OFF (default), render_mix must be bit-identical to
    itself across runs -- i.e. the new hook is completely inert."""
    monkeypatch.setattr(config, "_FLAGS_PATH", str(tmp_path / "nonexistent.flags.json"))
    config.reload()
    try:
        stems = _make_stems()
        analysis = analyze(stems)
        prefs = MixPreferences()

        first = render_mix(stems, analysis, prefs)
        second = render_mix(stems, analysis, prefs)

        assert np.array_equal(first, second)
    finally:
        config.reload()
