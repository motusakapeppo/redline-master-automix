"""Tests for the canonical platform registry (redline/platforms.py) and its
consumers: masterengine's re-export + _target_lufs_for_genre, wizard's
MixPreferences validation, and schema_validator's PRESET_SCHEMA choices.

YouTube has normalized to -14 LUFS since 2019 (the registry originally pinned
-13); Tidal, Amazon Music and Deezer all normalize to -14 as well.
"""

from __future__ import annotations

from redline import masterengine, platforms
from redline.masterengine import _target_lufs_for_genre
from redline.platforms import PLATFORM_CHOICES, PLATFORM_TARGETS
from redline.schema_validator import PRESET_SCHEMA
from redline.wizard import MixPreferences

NEW_PLATFORMS = ("tidal", "amazon", "deezer")


def test_youtube_is_minus_14():
    assert PLATFORM_TARGETS["youtube"] == -14.0


def test_new_platforms_present():
    for name in NEW_PLATFORMS:
        assert name in PLATFORM_TARGETS, f"{name} missing from PLATFORM_TARGETS"
        assert PLATFORM_TARGETS[name] == -14.0


def test_platform_choices_include_new():
    for name in NEW_PLATFORMS:
        assert name in PLATFORM_CHOICES, f"{name} missing from PLATFORM_CHOICES"
    assert PLATFORM_CHOICES[0] == "auto"
    # PLATFORM_CHOICES stays derived: "auto" + every registry key, in order.
    assert set(PLATFORM_TARGETS) == set(PLATFORM_CHOICES) - {"auto"}


def test_wizard_accepts_new_platforms():
    for name in NEW_PLATFORMS:
        assert MixPreferences(platform=name).platform == name
    # Unknown platforms still fall back to "auto".
    assert MixPreferences(platform="myspace").platform == "auto"


def test_schema_choices_match_registry():
    assert PRESET_SCHEMA["platform"]["choices"] == list(PLATFORM_CHOICES)
    for name in NEW_PLATFORMS:
        assert name in PRESET_SCHEMA["platform"]["choices"]


def test_target_lufs_for_new_platforms():
    assert _target_lufs_for_genre("Pop / Rock", "tidal") == -14.0
    assert _target_lufs_for_genre("Pop / Rock", "amazon") == -14.0
    assert _target_lufs_for_genre("Pop / Rock", "deezer") == -14.0
    assert _target_lufs_for_genre("Pop / Rock", "youtube") == -14.0


def test_target_lufs_for_auto_and_existing_platforms_unchanged():
    # "auto" keeps the genre-based resolution (club for EDM, spotify otherwise).
    assert _target_lufs_for_genre("Pop / Rock", "auto") == -14.0
    assert _target_lufs_for_genre("EDM / Urban", "auto") == -9.0
    # Existing explicit platforms keep their values.
    assert _target_lufs_for_genre("Pop / Rock", "spotify") == -14.0
    assert _target_lufs_for_genre("Pop / Rock", "apple") == -16.0
    assert _target_lufs_for_genre("Pop / Rock", "club") == -9.0


def test_masterengine_reexport_is_same_object():
    assert masterengine.PLATFORM_TARGETS is platforms.PLATFORM_TARGETS
