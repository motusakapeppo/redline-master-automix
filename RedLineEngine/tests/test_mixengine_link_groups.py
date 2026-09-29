"""Regression test for the link-group UnboundLocalError in render_mix().

A session with 2+ stems sharing a naming.py link_id (e.g. Kick_In + Kick_Out)
used to crash with `UnboundLocalError: local variable '_guarded_on_step'
referenced before assignment`, because the two `_guarded_on_*` helpers were
defined *after* the link-group loop that calls them.
"""

import numpy as np

from redline.input_loader import Stems
from redline.analyze import analyze
from redline.wizard import MixPreferences
from redline.mixengine import render_mix
from redline.naming import parse_stem


def _make_link_group_stems(sr: int = 44100, seconds: float = 2.0) -> Stems:
    n = int(sr * seconds)
    t = np.linspace(0, seconds, n, endpoint=False)
    rng = np.random.default_rng(7)

    kick_in = 0.3 * np.sin(2 * np.pi * 60.0 * t)
    kick_out = 0.25 * np.sin(2 * np.pi * 60.0 * t + 0.1)
    bass = 0.3 * np.sin(2 * np.pi * 80.0 * t)
    pad = 0.2 * np.sin(2 * np.pi * 220.0 * t) + 0.05 * rng.standard_normal(n)

    def stereo(mono):
        return np.stack([mono, mono], axis=1).astype(np.float32)

    return Stems(
        sample_rate=sr,
        tracks={
            "Kick_In": stereo(kick_in),
            "Kick_Out": stereo(kick_out),
            "Bass": stereo(bass),
            "Pad": stereo(pad),
        },
    )


def test_kick_in_out_share_link_id():
    assert parse_stem("Kick_In").link_id == parse_stem("Kick_Out").link_id
    assert parse_stem("Kick_In").link_id is not None


def test_render_mix_with_link_group_does_not_raise():
    stems = _make_link_group_stems()
    analysis = analyze(stems)
    prefs = MixPreferences()

    events = []
    mixed = render_mix(stems, analysis, prefs, on_event=events.append)

    assert mixed.shape[0] == stems.num_samples()
    assert mixed.shape[1] == 2
    assert np.max(np.abs(mixed)) > 0.0

    link_events = [e for e in events if e.get("type") == "link_group"]
    assert link_events, "expected at least one link_group event"
    assert link_events[0]["link_id"] == "kick"
    assert set(link_events[0]["members"]) == {"Kick_In", "Kick_Out"}
