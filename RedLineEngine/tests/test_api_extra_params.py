"""Regression test for a real GUI completeness gap found in review: the 7
neutral-by-default mix parameters added in the universalization pass were
persisted by `presets.py`, but the app bridge (`app/api.py`) dropped them in
`load_preset` / `save_preset` / `_build_mix_prefs` -- so a built-in preset that
sets one (e.g. Lo-Fi's saturation_amount) silently lost it the moment it passed
through the GUI. This pins the bridge round-trip."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

pytest.importorskip("webview")  # app/api.py imports pywebview at module scope

import api as api_module  # noqa: E402
from redline.wizard import MixPreferences  # noqa: E402


EXTRA_FIELDS = api_module._EXTRA_MIX_FIELDS
VALUES = {
    "mono_compatibility_target": 0.75,
    "bass_mono_below_hz": 150.0,
    "reference_lufs_target": -20.0,
    "saturation_amount": 0.5,
    "deess_amount": -0.4,
    "compression_amount": 0.3,
    "vocal_reverb_amount": -0.6,
}


def test_extra_mix_fields_cover_all_extra_mixpreferences_fields():
    # Guards against a future MixPreferences field being added and forgotten
    # by the bridge again.
    import dataclasses

    known = {
        "aggressiveness", "warmth", "vocal_prominence", "genre_override",
        "do_mastering", "platform", "stereo_width", "transient_attack",
        "transient_sustain",
    }
    all_fields = {f.name for f in dataclasses.fields(MixPreferences)}
    assert set(EXTRA_FIELDS) == all_fields - known


def test_extra_mix_kwargs_extracts_values_and_defaults_to_zero():
    assert api_module._extra_mix_kwargs(VALUES) == VALUES
    assert api_module._extra_mix_kwargs({}) == {name: 0.0 for name in EXTRA_FIELDS}


def test_build_mix_prefs_forwards_extra_fields():
    # `_build_mix_prefs` is a method; call it unbound with a dummy self so we
    # do not need a real pywebview window.
    class _Dummy:
        def _narrate(self, _msg):  # pragma: no cover - no brief in this test
            pass

    prefs = api_module.Api._build_mix_prefs(_Dummy(), dict(VALUES, aggressiveness=3))
    for name, expected in VALUES.items():
        assert getattr(prefs, name) == expected, name


def test_build_mix_prefs_missing_extra_fields_default_neutral():
    class _Dummy:
        def _narrate(self, _msg):  # pragma: no cover
            pass

    prefs = api_module.Api._build_mix_prefs(_Dummy(), {"aggressiveness": 3})
    for name in EXTRA_FIELDS:
        assert getattr(prefs, name) == 0.0, name


def test_save_then_load_preset_round_trips_extra_fields(monkeypatch, tmp_path):
    # Redirect the user-preset dir so we do not touch ~/.redline.
    from redline import presets as presets_module

    monkeypatch.setattr(presets_module, "_preset_dir", lambda: tmp_path)
    monkeypatch.setattr(presets_module, "_preset_path", lambda name: tmp_path / f"{name}.json")

    mp = MixPreferences(aggressiveness=3, **VALUES)
    presets_module.PresetManager.save(mp, "roundtrip-test")

    class _Dummy:
        pass

    loaded = api_module.Api.load_preset(_Dummy(), "roundtrip-test")
    assert loaded["ok"] is True
    for name, expected in VALUES.items():
        assert loaded[name] == expected, name
