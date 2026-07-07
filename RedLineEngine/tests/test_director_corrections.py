"""Integration test for the Director Mode stem-classification correction
flow: a GUI-supplied correction must actually change how render_mix treats
the stem (not just its label), verified end-to-end through a real
DirectorGate on a background thread -- same pattern as test_director.py,
but exercising render_mix's consumption of the answer instead of just the
gate primitive."""

import threading

import numpy as np

from redline.director import DirectorGate
from redline.input_loader import Stems
from redline.analyze import analyze
from redline.wizard import MixPreferences
from redline.mixengine import render_mix


def _make_stems(sr=44100, seconds=2.0):
    n = int(sr * seconds)
    t = np.linspace(0, seconds, n, endpoint=False)
    rng = np.random.default_rng(3)

    def stereo(mono):
        return np.stack([mono, mono], axis=1).astype(np.float32)

    # "mystery" has no naming hint at all -- defaults to role="other".
    mystery = 0.2 * np.sin(2 * np.pi * 440.0 * t)
    bass = 0.3 * np.sin(2 * np.pi * 80.0 * t)
    drums = 0.15 * rng.standard_normal(n)

    return Stems(
        sample_rate=sr,
        tracks={"mystery": stereo(mystery), "bass": stereo(bass), "drums": stereo(drums)},
    )


def test_role_correction_reroutes_stem_into_vocal_bus():
    stems = _make_stems()
    analysis = analyze(stems)
    prefs = MixPreferences()
    gate = DirectorGate()
    events = []
    bus_names_seen = []

    def on_event(evt):
        events.append(evt)

    def on_bus_ready(name, audio):
        bus_names_seen.append(name)

    def worker():
        render_mix(
            stems, analysis, prefs,
            on_event=on_event, director_gate=gate, on_bus_ready=on_bus_ready,
        )

    t = threading.Thread(target=worker)
    t.start()

    # Wait for the stem_classification checkpoint, then answer with a
    # correction promoting "mystery" from "other" to a primary lead vocal.
    for _ in range(200):
        if any(e.get("type") == "director_checkpoint" and e.get("checkpoint") == "stem_classification" for e in events):
            break
        threading.Event().wait(0.05)
    gate.answer({"mystery": {"role": "vocal", "layer": "primary"}})
    t.join(timeout=30)

    assert any(e.get("type") == "director_corrections" and "mystery" in e.get("stems", []) for e in events)
    assert "vocal_main" in bus_names_seen


def test_no_corrections_leaves_classification_unchanged():
    stems = _make_stems()
    analysis = analyze(stems)
    prefs = MixPreferences()
    gate = DirectorGate()
    events = []

    def worker():
        render_mix(stems, analysis, prefs, on_event=events.append, director_gate=gate)

    t = threading.Thread(target=worker)
    t.start()
    for _ in range(200):
        if any(e.get("type") == "director_checkpoint" and e.get("checkpoint") == "stem_classification" for e in events):
            break
        threading.Event().wait(0.05)
    gate.answer({})
    t.join(timeout=30)

    assert not any(e.get("type") == "director_corrections" for e in events)
