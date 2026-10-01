"""Automatic per-stem character-processor assignment (ENABLE_AUTO_PROCESSORS).

The old UX applied ONE processor to every stem, which is musically wrong.
With ``ENABLE_AUTO_PROCESSORS`` (AND ``ENABLE_BUILTIN_PROCESSOR_VARIANTS``)
ON, render_mix assigns a curated preset per stem based on its role /
instrument / register, and emits the existing ``character_processor`` event
(now carrying ``auto`` + ``reason``) so the GUI can show what was applied and
why. An explicit caller-supplied ``character_spec`` always wins.

With the flag OFF (the default) the render is byte-identical to before this
feature existed -- the golden neutrality guard must stay green.
"""

from __future__ import annotations

import numpy as np

from redline import config
from redline.analyze import analyze
from redline.wizard import MixPreferences
from redline.mixengine import render_mix
from tests.test_neutral_golden import _stems


def _render(stems, analysis, prefs, **kwargs):
    events: list[dict] = []
    mixed = render_mix(stems, analysis, prefs, on_event=events.append, **kwargs)
    return mixed, events


def _character_events(events: list[dict]) -> list[dict]:
    return [e for e in events if e.get("type") == "character_processor"]


def test_auto_off_is_bit_identical(monkeypatch, tmp_path):
    """Default (ENABLE_AUTO_PROCESSORS OFF) -> no processor, byte-identical."""
    monkeypatch.setattr(config, "_FLAGS_PATH", str(tmp_path / "nonexistent.flags.json"))
    config.reload()
    try:
        stems = _stems()
        analysis = analyze(stems)
        prefs = MixPreferences()

        baseline = render_mix(stems, analysis, prefs)
        mixed, events = _render(stems, analysis, prefs)

        assert _character_events(events) == []
        assert np.array_equal(baseline, mixed)
    finally:
        config.reload()


def test_auto_on_but_variants_off_is_inert(monkeypatch, tmp_path):
    """Both flags are required: auto ON alone must not insert anything."""
    monkeypatch.setattr(config, "_FLAGS_PATH", str(tmp_path / "nonexistent.flags.json"))
    config.reload()
    try:
        stems = _stems()
        analysis = analyze(stems)
        prefs = MixPreferences()

        baseline = render_mix(stems, analysis, prefs)

        config.set_override("ENABLE_AUTO_PROCESSORS", True)
        mixed, events = _render(stems, analysis, prefs)

        assert _character_events(events) == []
        assert np.array_equal(baseline, mixed)
    finally:
        config.reload()


def test_auto_on_produces_per_stem_plan(monkeypatch, tmp_path):
    """Both flags ON -> per-stem auto events with a reason, and audio changes."""
    monkeypatch.setattr(config, "_FLAGS_PATH", str(tmp_path / "nonexistent.flags.json"))
    config.reload()
    try:
        stems = _stems()
        analysis = analyze(stems)
        prefs = MixPreferences()

        baseline = render_mix(stems, analysis, prefs)

        config.set_override("ENABLE_BUILTIN_PROCESSOR_VARIANTS", True)
        config.set_override("ENABLE_AUTO_PROCESSORS", True)
        mixed, events = _render(stems, analysis, prefs)

        char_events = _character_events(events)
        assert char_events, "expected auto character_processor events"
        for evt in char_events:
            assert evt.get("auto") is True
            assert isinstance(evt.get("reason"), str) and evt["reason"]
            assert isinstance(evt.get("stem"), str) and evt["stem"]
            assert isinstance(evt.get("processor"), str) and evt["processor"]

        # The lead vocal must NOT get a processor by default.
        assert all(e["stem"] != "vocals" for e in char_events)

        assert not np.array_equal(baseline, mixed), "auto processors must change the audio"
    finally:
        config.reload()


def test_explicit_spec_overrides_auto(monkeypatch, tmp_path):
    """An explicit character_spec always wins over auto-assignment."""
    monkeypatch.setattr(config, "_FLAGS_PATH", str(tmp_path / "nonexistent.flags.json"))
    config.reload()
    try:
        stems = _stems()
        analysis = analyze(stems)
        prefs = MixPreferences()

        config.set_override("ENABLE_BUILTIN_PROCESSOR_VARIANTS", True)
        config.set_override("ENABLE_AUTO_PROCESSORS", True)

        spec = {"bass": {"processor": "distortion", "params": {"drive_db": 3.0}}}
        mixed, events = _render(stems, analysis, prefs, character_spec=spec)

        char_events = _character_events(events)
        assert char_events, "explicit spec must still apply"
        # The explicitly-specified stem must use the user's processor, not the
        # auto preset, and must not be flagged as auto.
        bass_events = [e for e in char_events if e["stem"] == "bass"]
        assert bass_events, "explicit bass spec must apply"
        for evt in bass_events:
            assert evt["processor"] == "distortion"
            assert evt["params"] == {"drive_db": 3.0}
            assert evt.get("auto") is not True
        # Other stems may still be auto-assigned (that is the point of auto).
        for evt in char_events:
            if evt["stem"] != "bass":
                assert evt.get("auto") is True
    finally:
        config.reload()
