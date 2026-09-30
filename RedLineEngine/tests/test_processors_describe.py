"""Additive introspection surface for the built-in character processors.

``describe_processor(name)`` exposes human metadata (label + per-param
default/min/max/step/unit) for the GUI, without changing the existing
``available_processors`` / ``build_processor`` contract. These tests pin the
shape, the unknown-name contract (None, never raise) and the fresh-copy
guarantee (callers must not be able to mutate shared registry state).
"""

from __future__ import annotations

from redline.processors import (
    available_processors,
    build_processor,
    describe_processor,
)

# The 8 processors the registry is expected to expose.
_EXPECTED = {
    "distortion",
    "chorus",
    "phaser",
    "bitcrush",
    "clipping",
    "noise_gate",
    "ladder_filter",
    "pitch_shift",
}

# Real defaults read straight from the factories in redline/processors.py.
_EXPECTED_DEFAULTS = {
    "distortion": {"drive_db": 6.0},
    "chorus": {
        "rate_hz": 1.0,
        "depth": 0.25,
        "centre_delay_ms": 7.0,
        "feedback": 0.0,
        "mix": 0.5,
    },
    "phaser": {
        "rate_hz": 1.0,
        "depth": 0.5,
        "centre_frequency_hz": 1300.0,
        "feedback": 0.0,
        "mix": 0.5,
    },
    "bitcrush": {"bit_depth": 8.0},
    "clipping": {"threshold_db": -6.0},
    "noise_gate": {
        "threshold_db": -100.0,
        "ratio": 10.0,
        "attack_ms": 1.0,
        "release_ms": 100.0,
    },
    "ladder_filter": {
        "cutoff_hz": 200.0,
        "resonance": 0.0,
        "drive": 1.0,
    },
    "pitch_shift": {"semitones": 0.0},
}


def test_describe_covers_every_available_processor():
    names = set(available_processors())
    assert names == _EXPECTED
    for name in names:
        meta = describe_processor(name)
        assert isinstance(meta, dict), name
        assert meta["name"] == name
        assert isinstance(meta["label"], str) and meta["label"]
        assert isinstance(meta["params"], list) and meta["params"]


def test_describe_param_shape_and_defaults_match_factories():
    for name, expected_defaults in _EXPECTED_DEFAULTS.items():
        meta = describe_processor(name)
        params = {p["name"]: p for p in meta["params"]}
        assert set(params) == set(expected_defaults), name
        for pname, default in expected_defaults.items():
            p = params[pname]
            assert set(p) >= {"name", "label", "default", "min", "max", "step", "unit"}, (name, pname)
            assert p["default"] == default, (name, pname)
            assert isinstance(p["label"], str) and p["label"]
            assert isinstance(p["unit"], str)
            assert isinstance(p["min"], (int, float))
            assert isinstance(p["max"], (int, float))
            assert isinstance(p["step"], (int, float))
            assert p["min"] <= p["default"] <= p["max"], (name, pname)
            assert p["step"] > 0, (name, pname)


def test_describe_unknown_returns_none_and_never_raises():
    assert describe_processor("nonexistent") is None
    assert describe_processor("") is None
    # Garbage input must not raise either.
    assert describe_processor(None) is None  # type: ignore[arg-type]
    assert describe_processor(123) is None  # type: ignore[arg-type]


def test_describe_returns_a_fresh_copy():
    """Mutating the returned dict must not corrupt the shared registry."""
    first = describe_processor("distortion")
    first["label"] = "MUTATED"
    first["params"][0]["default"] = 999.0
    first["params"].append({"name": "injected"})

    second = describe_processor("distortion")
    assert second["label"] != "MUTATED"
    assert second["params"][0]["default"] == 6.0
    assert all(p["name"] != "injected" for p in second["params"])


def test_existing_registry_contract_unchanged():
    """The additive change must not alter available_processors/build_processor."""
    names = available_processors()
    assert isinstance(names, tuple)
    assert names == tuple(sorted(names))
    for name in names:
        assert build_processor(name) is not None
    assert build_processor("nonexistent") is None
