"""Curated per-stem character-processor presets (data-only table).

The engine used to offer only "apply one processor to every stem", which is
musically wrong: a kick, a bass, a pad and a lead vocal each need different
treatment. This module pins the curated ``PROCESSOR_PRESETS`` table and its
resolver ``preset_for(role, instrument_kind, register)``:

  - a bass gets a bass-appropriate processor (warmth), never chorus/phaser;
  - a lead vocal gets None (or only a genuinely gentle choice), never chorus;
  - an unknown context resolves to None (no processor);
  - every preset names a real processor and only valid params for it.

The table is pure data with no side effects -- importing it must never touch
audio or the render path.
"""

from __future__ import annotations

from redline.processors import (
    PROCESSOR_PRESETS,
    available_presets,
    available_processors,
    build_processor,
    describe_processor,
    preset_for,
)


def _valid_param_names(processor: str) -> set[str]:
    meta = describe_processor(processor) or {}
    return {p["name"] for p in meta.get("params", [])}


def test_bass_preset_is_bass_appropriate_not_chorus():
    preset = preset_for("bass")
    assert preset is not None
    assert preset["processor"] in ("distortion", "ladder_filter")
    assert preset["processor"] not in ("chorus", "phaser")


def test_lead_vocal_is_none_or_gentle_only():
    # A lead vocal (no register context) must never get a chorus/phaser by
    # default -- that is the whole point of per-stem intelligence.
    preset = preset_for("vocal")
    if preset is not None:
        assert preset["processor"] not in ("chorus", "phaser", "bitcrush")
        assert preset["processor"] in ("clipping", "noise_gate", "ladder_filter", "distortion")


def test_unknown_context_returns_none():
    assert preset_for("nonsense") is None
    assert preset_for("") is None
    assert preset_for(None) is None  # type: ignore[arg-type]


def test_available_presets_stable_and_sorted():
    first = available_presets()
    second = available_presets()
    assert first == second
    assert isinstance(first, tuple)
    assert first == tuple(sorted(first))
    assert len(first) >= 1


def test_every_preset_processor_and_params_are_valid():
    for key, preset in PROCESSOR_PRESETS.items():
        assert isinstance(preset, dict), key
        proc = preset.get("processor")
        assert proc in available_processors(), (key, proc)
        assert build_processor(proc, preset.get("params")) is not None, key
        valid = _valid_param_names(proc)
        for pname in (preset.get("params") or {}):
            assert pname in valid, (key, proc, pname)


def test_preset_for_returns_fresh_copy():
    a = preset_for("bass")
    assert a is not None
    a["processor"] = "MUTATED"
    a["params"]["drive_db"] = 999.0
    b = preset_for("bass")
    assert b is not None
    assert b["processor"] != "MUTATED"
    assert b["params"].get("drive_db") != 999.0


def test_instrument_and_register_contexts_resolve():
    # synth pad / keys / strings -> width (chorus/phaser)
    pad = preset_for("other", instrument_kind="synth_pad")
    assert pad is not None and pad["processor"] in ("chorus", "phaser")
    # electric guitar -> chorus/phaser
    gtr = preset_for("other", instrument_kind="guitar_electric")
    assert gtr is not None and gtr["processor"] in ("chorus", "phaser")
    # drums -> transient glue / bleed control
    drums = preset_for("drums")
    assert drums is not None and drums["processor"] in ("clipping", "noise_gate")
    # fx/riser -> bitcrush/phaser
    fx = preset_for("other", instrument_kind="fx")
    assert fx is not None and fx["processor"] in ("bitcrush", "phaser")
    # a vocal double (register context) may get subtle width, but never a
    # lead vocal (no register) -- already covered above.
    double = preset_for("vocal", register="high")
    if double is not None:
        assert double["processor"] in ("chorus", "phaser")
