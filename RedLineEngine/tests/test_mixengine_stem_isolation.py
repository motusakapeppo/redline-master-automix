"""Per-stem failure isolation in render_mix().

A single stem whose per-stem DSP chain raises must not abort the whole
render: the failure is logged, a `stem_failed` event is emitted, and the
stem falls back to its dry signal so downstream bus math (which indexes
`processed[name]` unconditionally for every solo stem) still finds it.
"""

import numpy as np

from redline.input_loader import Stems
from redline.analyze import analyze
from redline.wizard import MixPreferences
import redline.mixengine as mixengine
from redline.mixengine import render_mix


def _make_stems(sr: int = 44100, seconds: float = 2.0) -> Stems:
    n = int(sr * seconds)
    t = np.linspace(0, seconds, n, endpoint=False)
    rng = np.random.default_rng(11)

    kick = 0.3 * np.sin(2 * np.pi * 60.0 * t)
    bass = 0.3 * np.sin(2 * np.pi * 80.0 * t)
    pad = 0.2 * np.sin(2 * np.pi * 220.0 * t) + 0.05 * rng.standard_normal(n)

    def stereo(mono):
        return np.stack([mono, mono], axis=1).astype(np.float32)

    return Stems(
        sample_rate=sr,
        tracks={
            "Kick": stereo(kick),
            "Bass": stereo(bass),
            "Pad": stereo(pad),
        },
    )


def test_one_failing_stem_does_not_abort_render(monkeypatch):
    stems = _make_stems()
    analysis = analyze(stems)
    prefs = MixPreferences()

    original = mixengine._process_stem
    failing = "Bass"

    def flaky_process_stem(name, *args, **kwargs):
        if name == failing:
            raise RuntimeError("boom in per-stem DSP")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(mixengine, "_process_stem", flaky_process_stem)

    events = []
    mixed = render_mix(stems, analysis, prefs, on_event=events.append)

    # (a) no exception propagated -- reaching here is the assertion.
    # (b) output shape is correct and finite.
    assert mixed.shape[0] == stems.num_samples()
    assert mixed.shape[1] == 2
    assert np.all(np.isfinite(mixed))
    assert np.max(np.abs(mixed)) > 0.0

    # (c) a stem_failed event was emitted for the failing stem.
    failed_events = [e for e in events if e.get("type") == "stem_failed"]
    assert failed_events, "expected a stem_failed event"
    assert failed_events[0]["stem"] == failing
    assert "boom in per-stem DSP" in failed_events[0]["error"]
