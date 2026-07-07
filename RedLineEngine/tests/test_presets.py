"""Tests for the PresetManager system — built-in presets, user preset
save/load/delete, and edge cases (collisions, missing files, etc.)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from redline.presets import PresetManager, _BUILTIN_PRESETS, _preset_dir, _preset_path
from redline.wizard import MixPreferences


# ---------------------------------------------------------------------------
# Fixtures: redirect the preset directory to a temp dir so tests never touch
# the real ~/.redline/presets/
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolated_preset_dir(monkeypatch: pytest.MonkeyPatch) -> Path:
    """Replace the user home directory with a temporary one so every test
    writes to a clean, disposable ~/.redline/presets/."""
    tmp = Path(tempfile.mkdtemp(prefix="redline_presets_"))
    monkeypatch.setattr(Path, "home", lambda: tmp)
    # Ensure the preset dir exists (the real _preset_dir() creates it on
    # first call, but we want it ready before any test runs).
    (tmp / ".redline" / "presets").mkdir(parents=True, exist_ok=True)
    return tmp


# ---------------------------------------------------------------------------
# Built-in presets
# ---------------------------------------------------------------------------

class TestBuiltins:
    def test_list_includes_all_builtins(self):
        names = PresetManager.list()
        for builtin in _BUILTIN_PRESETS:
            assert builtin in names

    def test_list_builtins_returns_only_builtins(self):
        assert PresetManager.list_builtins() == list(_BUILTIN_PRESETS.keys())

    def test_load_builtin_returns_valid_mixpreferences(self):
        for name in _BUILTIN_PRESETS:
            prefs = PresetManager.load(name)
            assert isinstance(prefs, MixPreferences)
            assert 1 <= prefs.aggressiveness <= 5
            assert -1.0 <= prefs.warmth <= 1.0
            assert -1.0 <= prefs.vocal_prominence <= 1.0

    def test_builtin_bilanciato_defaults(self):
        prefs = PresetManager.load("Bilanciato")
        assert prefs.aggressiveness == 3
        assert prefs.warmth == 0.0
        assert prefs.vocal_prominence == 0.0
        assert prefs.genre_override is None
        assert prefs.do_mastering is True
        assert prefs.platform == "auto"

    def test_builtin_radio_generico_values(self):
        prefs = PresetManager.load("Radio (generico)")
        assert prefs.aggressiveness == 4
        assert prefs.warmth == 0.3
        assert prefs.vocal_prominence == 0.5
        assert prefs.platform == "spotify"

    def test_builtin_caldo_vintage_values(self):
        prefs = PresetManager.load("Caldo Vintage")
        assert prefs.aggressiveness == 2
        assert prefs.warmth == 0.8
        assert prefs.vocal_prominence == -0.2

    def test_builtin_moderno_brillante_values(self):
        prefs = PresetManager.load("Moderno Brillante")
        assert prefs.aggressiveness == 4
        assert prefs.warmth == -0.5
        assert prefs.vocal_prominence == 0.3

    def test_builtin_morbido_acustico_values(self):
        prefs = PresetManager.load("Morbido Acustico")
        assert prefs.aggressiveness == 1
        assert prefs.warmth == 0.5
        assert prefs.vocal_prominence == 0.2

    def test_builtin_rock_spotify_values(self):
        prefs = PresetManager.load("Rock - Spotify")
        assert prefs.aggressiveness == 4
        assert prefs.genre_override == "Pop / Rock"
        assert prefs.platform == "spotify"
        assert prefs.stereo_width == 0.3

    def test_builtin_edm_club_values(self):
        prefs = PresetManager.load("EDM - Club")
        assert prefs.aggressiveness == 5
        assert prefs.genre_override == "EDM / Urban"
        assert prefs.platform == "club"
        assert prefs.transient_attack == 4.0

    def test_builtin_hiphop_spotify_values(self):
        prefs = PresetManager.load("Hip-Hop - Spotify")
        assert prefs.aggressiveness == 4
        assert prefs.genre_override == "Hip-Hop"
        assert prefs.platform == "spotify"

    def test_builtin_acoustic_apple_values(self):
        prefs = PresetManager.load("Acoustic - Apple Music")
        assert prefs.aggressiveness == 2
        assert prefs.genre_override == "Acoustic / Classical"
        assert prefs.platform == "apple"

    def test_builtin_jazz_apple_values(self):
        prefs = PresetManager.load("Jazz - Apple Music")
        assert prefs.aggressiveness == 2
        assert prefs.genre_override == "Jazz / Vintage"
        assert prefs.platform == "apple"

    def test_builtin_loudness_war_values(self):
        prefs = PresetManager.load("Loudness War")
        assert prefs.aggressiveness == 5
        assert prefs.platform == "club"
        assert prefs.transient_sustain == -3.0


# ---------------------------------------------------------------------------
# User preset save / load / list
# ---------------------------------------------------------------------------

class TestUserPresets:
    def test_save_and_load_roundtrip(self):
        prefs = MixPreferences(aggressiveness=4, warmth=0.5, vocal_prominence=-0.3)
        PresetManager.save(prefs, "My Test")
        loaded = PresetManager.load("My Test")
        assert loaded.aggressiveness == 4
        assert loaded.warmth == 0.5
        assert loaded.vocal_prominence == -0.3
        assert loaded.genre_override is None
        assert loaded.do_mastering is True

    def test_save_persists_json_file(self):
        prefs = MixPreferences(aggressiveness=2, warmth=0.8, vocal_prominence=0.1)
        PresetManager.save(prefs, "Persist Check")
        path = _preset_path("Persist Check")
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["aggressiveness"] == 2
        assert data["warmth"] == 0.8
        assert data["vocal_prominence"] == 0.1

    def test_list_includes_user_presets(self):
        PresetManager.save(MixPreferences(), "User A")
        PresetManager.save(MixPreferences(), "User B")
        names = PresetManager.list()
        assert "User A" in names
        assert "User B" in names

    def test_save_with_builtin_name_raises_valueerror(self):
        with pytest.raises(ValueError, match="predefinito"):
            PresetManager.save(MixPreferences(), "Bilanciato")  # same name as builtin

    def test_load_user_preset_with_genre_override(self):
        prefs = MixPreferences(aggressiveness=3, genre_override="Hip-Hop", do_mastering=False)
        PresetManager.save(prefs, "Hip Hop Special")
        loaded = PresetManager.load("Hip Hop Special")
        assert loaded.genre_override == "Hip-Hop"
        assert loaded.do_mastering is False

    def test_load_nonexistent_raises_keyerror(self):
        with pytest.raises(KeyError, match="non trovato"):
            PresetManager.load("This Preset Does Not Exist")

    def test_save_overwrites_existing_user_preset(self):
        PresetManager.save(MixPreferences(aggressiveness=1), "Overwrite Me")
        PresetManager.save(MixPreferences(aggressiveness=5), "Overwrite Me")
        loaded = PresetManager.load("Overwrite Me")
        assert loaded.aggressiveness == 5


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

class TestDelete:
    def test_delete_user_preset(self):
        PresetManager.save(MixPreferences(), "To Delete")
        assert "To Delete" in PresetManager.list()
        PresetManager.delete("To Delete")
        assert "To Delete" not in PresetManager.list()

    def test_delete_builtin_raises_valueerror(self):
        with pytest.raises(ValueError, match="predefinito"):
            PresetManager.delete("Bilanciato")

    def test_delete_nonexistent_raises_keyerror(self):
        with pytest.raises(KeyError, match="non trovato"):
            PresetManager.delete("Mai Salvato")

    def test_delete_removes_file(self):
        PresetManager.save(MixPreferences(), "File Check")
        path = _preset_path("File Check")
        assert path.exists()
        PresetManager.delete("File Check")
        assert not path.exists()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_save_builtin_name_raises_valueerror(self):
        with pytest.raises(ValueError, match="predefinito"):
            PresetManager.save(MixPreferences(), "Bilanciato")

    def test_load_after_delete_raises_keyerror(self):
        PresetManager.save(MixPreferences(), "Ephemeral")
        PresetManager.delete("Ephemeral")
        with pytest.raises(KeyError):
            PresetManager.load("Ephemeral")

    def test_corrupted_json_raises_keyerror(self):
        path = _preset_path("Corrupted")
        path.write_text("this is not json", encoding="utf-8")
        with pytest.raises(KeyError, match="Impossibile caricare"):
            PresetManager.load("Corrupted")

    def test_empty_preset_dir_returns_only_builtins(self):
        # The fixture gives us an empty preset dir
        names = PresetManager.list()
        assert names == list(_BUILTIN_PRESETS.keys())

    def test_save_with_special_characters_in_name(self):
        prefs = MixPreferences(aggressiveness=3)
        PresetManager.save(prefs, "Test - Special_Chars (1)")
        loaded = PresetManager.load("Test - Special_Chars (1)")
        assert loaded.aggressiveness == 3
        # Clean up
        PresetManager.delete("Test - Special_Chars (1)")

    def test_mixpreferences_clamping_on_load(self):
        """Even if a saved JSON has out-of-range values, MixPreferences
        __post_init__ clamps them."""
        path = _preset_path("Out Of Range")
        path.write_text(
            json.dumps({"aggressiveness": 99, "warmth": 5.0, "vocal_prominence": -5.0}),
            encoding="utf-8",
        )
        prefs = PresetManager.load("Out Of Range")
        assert prefs.aggressiveness == 5
        assert prefs.warmth == 1.0
        assert prefs.vocal_prominence == -1.0
