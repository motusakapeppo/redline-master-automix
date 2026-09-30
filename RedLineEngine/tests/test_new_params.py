"""Tests for the Wave-1 (Track E1) user-exposed mix parameters.

Covers:
- schema/clamp desalignment fix: every numeric PRESET_SCHEMA range must equal
  the MixPreferences.__post_init__ clamp (drift guard).
- the 7 new optional MixPreferences fields: neutral defaults, clamping,
  dataclass round-trip, and matching schema entries.

NOTE: preset serialization wiring (PresetManager.save/load) is Wave 2 (E3);
presets.py is intentionally NOT touched here. The round-trip test below
simulates the JSON round-trip via dataclasses.asdict instead.
"""

from __future__ import annotations

from dataclasses import asdict

import pytest

from redline.schema_validator import PRESET_SCHEMA
from redline.wizard import MixPreferences

# ---------------------------------------------------------------------------
# New fields: documented bounds (must match __post_init__ clamps AND schema)
# ---------------------------------------------------------------------------

NEW_FIELD_BOUNDS: dict[str, tuple[float, float]] = {
    "mono_compatibility_target": (0.0, 1.0),
    "bass_mono_below_hz": (0.0, 300.0),
    "reference_lufs_target": (-30.0, 0.0),
    "saturation_amount": (-1.0, 1.0),
    "deess_amount": (-1.0, 1.0),
    "compression_amount": (-1.0, 1.0),
    "vocal_reverb_amount": (-1.0, 1.0),
}


# ---------------------------------------------------------------------------
# Schema <-> clamp alignment (drift guard)
# ---------------------------------------------------------------------------

def test_schema_ranges_match_clamps():
    """For every numeric schema entry, an out-of-range MixPreferences value
    must clamp exactly to the schema bound. Fails today for stereo_width
    (schema -1..1 vs clamp 0..1) and transient_attack/sustain (schema
    -10..10 vs clamp -6..6)."""
    numeric_specs = {
        name: spec
        for name, spec in PRESET_SCHEMA.items()
        if spec["type"] in ("int", "float") and "min" in spec and "max" in spec
    }
    assert numeric_specs, "PRESET_SCHEMA has no numeric entries to check"

    for name, spec in numeric_specs.items():
        lo, hi = spec["min"], spec["max"]

        below = MixPreferences(**{name: lo - 1})
        assert getattr(below, name) == lo, (
            f"{name}: value {lo - 1} clamped to {getattr(below, name)}, "
            f"expected schema min {lo}"
        )

        above = MixPreferences(**{name: hi + 1})
        assert getattr(above, name) == hi, (
            f"{name}: value {hi + 1} clamped to {getattr(above, name)}, "
            f"expected schema max {hi}"
        )


def test_new_fields_in_schema():
    """Each new field must have a matching schema entry with the documented
    bounds and a neutral default."""
    for name, (lo, hi) in NEW_FIELD_BOUNDS.items():
        assert name in PRESET_SCHEMA, f"{name} missing from PRESET_SCHEMA"
        spec = PRESET_SCHEMA[name]
        assert spec["type"] == "float", f"{name}: expected float schema type"
        assert spec["min"] == lo, f"{name}: schema min {spec['min']} != {lo}"
        assert spec["max"] == hi, f"{name}: schema max {spec['max']} != {hi}"
        assert spec["default"] == 0.0, f"{name}: schema default must be neutral 0.0"


# ---------------------------------------------------------------------------
# New fields: neutral defaults
# ---------------------------------------------------------------------------

def test_new_fields_default_neutral():
    """All new fields default to 0.0 = engine default, no change."""
    prefs = MixPreferences()
    for name in NEW_FIELD_BOUNDS:
        assert getattr(prefs, name) == 0.0, f"{name} default is not neutral 0.0"


# ---------------------------------------------------------------------------
# New fields: clamping
# ---------------------------------------------------------------------------

def test_new_fields_clamp():
    """Out-of-range values clamp to the documented bounds; in-range values
    are preserved."""
    for name, (lo, hi) in NEW_FIELD_BOUNDS.items():
        below = MixPreferences(**{name: lo - 1.0})
        assert getattr(below, name) == lo, f"{name}: below-range not clamped to {lo}"

        above = MixPreferences(**{name: hi + 1.0})
        assert getattr(above, name) == hi, f"{name}: above-range not clamped to {hi}"

        mid = (lo + hi) / 2.0
        if mid != 0.0:  # 0.0 is the neutral default; still assert it survives
            inside = MixPreferences(**{name: mid})
            assert getattr(inside, name) == pytest.approx(mid), (
                f"{name}: in-range value {mid} was altered"
            )


# ---------------------------------------------------------------------------
# New fields: dataclass round-trip (preset persistence is Wave 2 / E3)
# ---------------------------------------------------------------------------

def test_new_fields_roundtrip():
    """Construct with non-neutral values, assert stored; then simulate the
    preset JSON round-trip via dataclasses.asdict -> MixPreferences(**data)."""
    values = {
        "mono_compatibility_target": 0.75,
        "bass_mono_below_hz": 150.0,
        "reference_lufs_target": -14.0,
        "saturation_amount": 0.4,
        "deess_amount": -0.3,
        "compression_amount": 0.6,
        "vocal_reverb_amount": -0.5,
    }
    prefs = MixPreferences(**values)
    for name, expected in values.items():
        assert getattr(prefs, name) == expected, f"{name} not stored as constructed"

    # Simulated serialization round-trip (what PresetManager will do in Wave 2)
    restored = MixPreferences(**asdict(prefs))
    for name, expected in values.items():
        assert getattr(restored, name) == expected, f"{name} lost in round-trip"
