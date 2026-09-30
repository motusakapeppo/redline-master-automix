"""Wave 2 / Track E3 tests: preset persistence of the 7 new MixPreferences
parameters + built-in preset coverage of the 15 new genres.

Covers:
- save/load round-trip of the 7 Wave-1 params (mono_compatibility_target,
  bass_mono_below_hz, reference_lufs_target, saturation_amount,
  deess_amount, compression_amount, vocal_reverb_amount).
- every built-in preset's genre_override is None or a canonical GENRE_NAMES
  member.
- at least one built-in preset per new genre (all 15 covered).
- built-in count grew beyond the original 24.
- legacy preset JSON files (original 9 keys only) still load, with the new
  fields defaulting to 0.0.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from redline.genres import GENRE_NAMES
from redline.presets import PresetManager, _BUILTIN_PRESETS, _preset_path
from redline.wizard import MixPreferences

# The 15 genres added in Wave 1 / Track C1 (everything after the original 6).
NEW_GENRES: tuple[str, ...] = GENRE_NAMES[6:]

# The 7 Wave-1 params, with non-neutral values for the round-trip test.
NEW_PARAM_VALUES: dict[str, float] = {
    "mono_compatibility_target": 0.8,
    "bass_mono_below_hz": 140.0,
    "reference_lufs_target": -13.0,
    "saturation_amount": 0.35,
    "deess_amount": -0.25,
    "compression_amount": 0.55,
    "vocal_reverb_amount": -0.45,
}

# The original 9 serialized fields (pre-Wave-2 preset format).
LEGACY_FIELDS: dict = {
    "aggressiveness": 4,
    "warmth": 0.2,
    "vocal_prominence": 0.3,
    "genre_override": "Hip-Hop",
    "do_mastering": True,
    "platform": "spotify",
    "stereo_width": 0.3,
    "transient_attack": 2.0,
    "transient_sustain": -1.0,
}


@pytest.fixture(autouse=True)
def _isolated_preset_dir(monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect ~/.redline/presets/ to a disposable temp dir (same isolation
    strategy as tests/test_presets.py)."""
    tmp = Path(tempfile.mkdtemp(prefix="redline_presets_new_"))
    monkeypatch.setattr(Path, "home", lambda: tmp)
    (tmp / ".redline" / "presets").mkdir(parents=True, exist_ok=True)
    return tmp


# ---------------------------------------------------------------------------
# Persistence of the 7 new params
# ---------------------------------------------------------------------------

def test_save_load_roundtrips_new_params():
    prefs = MixPreferences(**NEW_PARAM_VALUES)
    PresetManager.save(prefs, "New Params Roundtrip")
    loaded = PresetManager.load("New Params Roundtrip")
    for name, expected in NEW_PARAM_VALUES.items():
        assert getattr(loaded, name) == pytest.approx(expected), (
            f"{name} lost in save/load round-trip"
        )


def test_saved_json_contains_new_keys():
    """The serialized JSON must actually carry the 7 new keys (not just
    survive via dataclass defaults)."""
    PresetManager.save(MixPreferences(**NEW_PARAM_VALUES), "New Params Keys")
    data = json.loads(_preset_path("New Params Keys").read_text(encoding="utf-8"))
    for name in NEW_PARAM_VALUES:
        assert name in data, f"{name} missing from saved preset JSON"


def test_old_preset_without_new_keys_loads():
    """A legacy preset file with only the original 9 fields must still load;
    the 7 new fields default to 0.0."""
    path = _preset_path("Legacy Preset")
    path.write_text(json.dumps(LEGACY_FIELDS), encoding="utf-8")

    loaded = PresetManager.load("Legacy Preset")
    assert loaded.aggressiveness == 4
    assert loaded.genre_override == "Hip-Hop"
    for name in NEW_PARAM_VALUES:
        assert getattr(loaded, name) == 0.0, f"{name} should default to 0.0"


# ---------------------------------------------------------------------------
# Built-in presets: genre validity + new-genre coverage
# ---------------------------------------------------------------------------

def test_every_builtin_has_valid_genre_override():
    for name, data in _BUILTIN_PRESETS.items():
        override = data.get("genre_override")
        assert override is None or override in GENRE_NAMES, (
            f"built-in '{name}' has genre_override {override!r} "
            f"which is not in GENRE_NAMES"
        )


def test_new_genre_presets_exist():
    """Every one of the 15 new genres must be reachable via at least one
    built-in preset's genre_override."""
    covered = {
        data.get("genre_override")
        for data in _BUILTIN_PRESETS.values()
    }
    missing = [g for g in NEW_GENRES if g not in covered]
    assert not missing, f"no built-in preset covers new genres: {missing}"


def test_preset_count_grew():
    # Original built-in count was 24 (pre-Wave-2).
    assert len(_BUILTIN_PRESETS) > 24


def test_new_builtins_load_and_are_mastering():
    """Every built-in still loads as a valid MixPreferences with
    do_mastering=True (existing contract)."""
    for name in _BUILTIN_PRESETS:
        prefs = PresetManager.load(name)
        assert isinstance(prefs, MixPreferences)
        assert prefs.do_mastering is True, f"built-in '{name}' has do_mastering=False"
