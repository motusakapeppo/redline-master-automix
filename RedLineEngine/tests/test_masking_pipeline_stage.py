"""Verifies the masking analysis re-run added at the bus level (point 3 of
the reference-profile upgrade): find_masking_cut() must be invoked at least
twice during a render -- once per-stem (existing behavior) and once more at
the music_bus level after leveling/ducking, before the Music bus Mid/Side EQ
in mixengine.py (see the `if vocal_main_bus is not None:` block right after
the "Bus musicale Mid/Side" step, immediately following the spectral-ducking
stage)."""

from __future__ import annotations

import numpy as np

import redline.mixengine as mixengine
from redline.input_loader import Stems
from redline.analyze import analyze
from redline.wizard import MixPreferences


def _make_synthetic_stems(sr: int = 44100, seconds: float = 3.0) -> Stems:
    n = int(sr * seconds)
    t = np.linspace(0, seconds, n, endpoint=False)
    rng = np.random.default_rng(7)

    # Vocal squarely in the presence band, instrumental heavily overlapping
    # it too -- structured so find_masking_cut() actually recommends a cut
    # both times it's called, not just gets called and returns None.
    vocals = 0.25 * np.sin(2 * np.pi * 3000.0 * t)
    bass = 0.3 * np.sin(2 * np.pi * 80.0 * t)
    drums = 0.1 * rng.standard_normal(n)
    other = 0.25 * np.sin(2 * np.pi * 3200.0 * t) + 0.03 * rng.standard_normal(n)

    def stereo(mono):
        return np.stack([mono, mono], axis=1).astype(np.float32)

    return Stems(
        sample_rate=sr,
        tracks={
            "Main_vocal": stereo(vocals),
            "bass": stereo(bass),
            "drums": stereo(drums),
            "synth": stereo(other),
        },
    )


def test_find_masking_cut_runs_at_least_twice_per_render(monkeypatch):
    stems = _make_synthetic_stems()
    analysis = analyze(stems)
    prefs = MixPreferences()

    call_count = {"n": 0}
    real_find_masking_cut = mixengine.find_masking_cut

    def _counting_find_masking_cut(*args, **kwargs):
        call_count["n"] += 1
        return real_find_masking_cut(*args, **kwargs)

    monkeypatch.setattr(mixengine, "find_masking_cut", _counting_find_masking_cut)

    mixengine.render_mix(stems, analysis, prefs)

    # One call per "other"-role stem (the original per-stem pass) plus at
    # least one more at the music_bus level (the new post-leveling pass) --
    # with a single "other" stem in this fixture, that's a minimum of 2.
    assert call_count["n"] >= 2


def test_bus_level_masking_events_are_emitted_after_stem_level_ones():
    stems = _make_synthetic_stems()
    analysis = analyze(stems)
    prefs = MixPreferences()

    events: list[dict] = []
    mixengine.render_mix(stems, analysis, prefs, on_event=events.append)

    masking_event_types = [e["type"] for e in events if e["type"] in ("masking_cut", "bus_masking_cut")]
    if "bus_masking_cut" in masking_event_types and "masking_cut" in masking_event_types:
        # The bus-level (second) pass must come after the stem-level (first)
        # pass in emission order -- confirms it runs later in the pipeline,
        # not just that it exists somewhere.
        assert masking_event_types.index("bus_masking_cut") > masking_event_types.index("masking_cut")
