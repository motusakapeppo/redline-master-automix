"""Regression test for a real crash: every on_event dict emitted by the
engine must survive json.dumps once run through _sanitize_for_json — numpy
scalar types (float32/float64/int64/bool_) aren't JSON-serializable on their
own, and this crashed every render right after the QC step tried to report
its (numpy-typed) measurements."""

import json
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

from api import _sanitize_for_json  # noqa: E402

from redline.input_loader import Stems
from redline.analyze import analyze
from redline.wizard import MixPreferences
from redline.mixengine import render_mix
from redline.masterengine import render_master


def test_sanitize_handles_numpy_scalars_and_nesting():
    evt = {
        "a": np.float32(1.5),
        "b": np.float64(-9.0),
        "c": np.int64(3),
        "d": np.bool_(True),
        "e": [np.float32(1.0), "text", {"nested": np.float32(2.0)}],
        "f": np.array([1.0, 2.0], dtype=np.float32),
    }
    cleaned = _sanitize_for_json(evt)
    json.dumps(cleaned)  # must not raise


def _make_synthetic_stems(sr: int = 44100, seconds: float = 2.0) -> Stems:
    n = int(sr * seconds)
    t = np.linspace(0, seconds, n, endpoint=False)
    rng = np.random.default_rng(1)
    vocals = 0.2 * np.sin(2 * np.pi * 440.0 * t)
    bass = 0.3 * np.sin(2 * np.pi * 80.0 * t)
    drums = 0.15 * rng.standard_normal(n)
    other = 0.2 * np.sin(2 * np.pi * 220.0 * t)

    def stereo(mono):
        return np.stack([mono, mono], axis=1).astype(np.float32)

    return Stems(sample_rate=sr, tracks={"vocals": stereo(vocals), "bass": stereo(bass), "drums": stereo(drums), "other": stereo(other)})


def test_every_real_event_from_the_pipeline_survives_json_dumps():
    """Runs the actual mix+master pipeline and JSON-encodes every single
    event it emits, exactly like the app does — this is the real crash
    reproduced and pinned down as a regression test."""
    stems = _make_synthetic_stems()
    analysis = analyze(stems)
    prefs = MixPreferences()

    events = []
    mixed = render_mix(stems, analysis, prefs, on_event=events.append)
    render_master(mixed, stems.sample_rate, analysis, on_event=events.append)

    assert events, "expected at least one event"
    for evt in events:
        json.dumps(_sanitize_for_json(evt))
