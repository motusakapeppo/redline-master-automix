"""Wave 2 / Track F: live telemetry for the character-processor + plugin seams.

These tests pin the *render-path* wiring of the two already-stored Api
attributes (``self._character_spec`` / ``self._plugin_path``):

  1. With the feature flags OFF (the defaults) the render is BYTE-IDENTICAL
     to before the wiring existed -- the whole point of the flag gate.
  2. With ``ENABLE_BUILTIN_PROCESSOR_VARIANTS`` ON and a spec supplied, a
     ``character_processor`` event is emitted and the audio actually changes.
  3. With the flag OFF a supplied spec is ignored entirely (no event, no
     change) -- the flag, not the spec, is the gate.
  4. A bad/unreadable plugin path degrades to ``None``: no ``plugin_hosted``
     event, no crash, byte-identical output.

The event shapes are frozen (the GUI already consumes them):
  {"type": "character_processor", "stem": str, "processor": str, "params": {...}}
  {"type": "plugin_hosted", "name": str, "parameters": [{"name","label","raw_value"}]}
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


def _plugin_events(events: list[dict]) -> list[dict]:
    return [e for e in events if e.get("type") == "plugin_hosted"]


def test_defaults_bit_identical_to_explicit_none(monkeypatch, tmp_path):
    """(1) Defaults (flag OFF) must equal an explicit character_spec=None /
    plugin_path=None render byte-for-byte."""
    monkeypatch.setattr(config, "_FLAGS_PATH", str(tmp_path / "nonexistent.flags.json"))
    config.reload()
    try:
        stems = _stems()
        analysis = analyze(stems)
        prefs = MixPreferences()

        default = render_mix(stems, analysis, prefs)
        explicit = render_mix(stems, analysis, prefs, character_spec=None, plugin_path=None)

        assert np.array_equal(default, explicit)
    finally:
        config.reload()


def test_flag_on_no_spec_is_inert(monkeypatch, tmp_path):
    """(2) Flag ON but no spec -> hook is a strict no-op, byte-identical."""
    monkeypatch.setattr(config, "_FLAGS_PATH", str(tmp_path / "nonexistent.flags.json"))
    config.reload()
    try:
        stems = _stems()
        analysis = analyze(stems)
        prefs = MixPreferences()

        off = render_mix(stems, analysis, prefs)

        config.set_override("ENABLE_BUILTIN_PROCESSOR_VARIANTS", True)
        on, events = _render(stems, analysis, prefs, character_spec=None)

        assert np.array_equal(off, on)
        assert _character_events(events) == []
    finally:
        config.reload()


def test_flag_on_with_spec_emits_event_and_changes_audio(monkeypatch, tmp_path):
    """(3) Flag ON + wildcard spec -> a character_processor event with the
    right processor/stem, and the audio actually changes."""
    monkeypatch.setattr(config, "_FLAGS_PATH", str(tmp_path / "nonexistent.flags.json"))
    config.reload()
    try:
        stems = _stems()
        analysis = analyze(stems)
        prefs = MixPreferences()

        baseline = render_mix(stems, analysis, prefs)

        config.set_override("ENABLE_BUILTIN_PROCESSOR_VARIANTS", True)
        spec = {"*": {"processor": "distortion", "params": {"drive_db": 6.0}}}
        mixed, events = _render(stems, analysis, prefs, character_spec=spec)

        char_events = _character_events(events)
        assert char_events, "expected at least one character_processor event"
        for evt in char_events:
            assert evt["processor"] == "distortion"
            assert isinstance(evt["stem"], str) and evt["stem"]
            assert evt["params"] == {"drive_db": 6.0}

        assert not np.array_equal(baseline, mixed), "distortion must change the audio"
    finally:
        config.reload()


def test_flag_off_with_spec_is_gated(monkeypatch, tmp_path):
    """(4) Flag OFF + a spec present -> no event and byte-identical output."""
    monkeypatch.setattr(config, "_FLAGS_PATH", str(tmp_path / "nonexistent.flags.json"))
    config.reload()
    try:
        stems = _stems()
        analysis = analyze(stems)
        prefs = MixPreferences()

        baseline = render_mix(stems, analysis, prefs)

        spec = {"*": {"processor": "distortion", "params": {"drive_db": 6.0}}}
        mixed, events = _render(stems, analysis, prefs, character_spec=spec)

        assert _character_events(events) == []
        assert np.array_equal(baseline, mixed)
    finally:
        config.reload()


def test_bad_plugin_path_is_failsafe(monkeypatch, tmp_path):
    """(5) Unreadable/nonexistent plugin path -> no plugin_hosted event, no
    crash, byte-identical output (even with the hosting flag ON)."""
    monkeypatch.setattr(config, "_FLAGS_PATH", str(tmp_path / "nonexistent.flags.json"))
    config.reload()
    try:
        stems = _stems()
        analysis = analyze(stems)
        prefs = MixPreferences()

        baseline = render_mix(stems, analysis, prefs)

        config.set_override("ENABLE_PLUGIN_HOSTING", True)
        mixed, events = _render(
            stems, analysis, prefs, plugin_path=str(tmp_path / "does_not_exist.vst3")
        )

        assert _plugin_events(events) == []
        assert np.array_equal(baseline, mixed)
    finally:
        config.reload()
