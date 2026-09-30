"""Registry consistency tests: the canonical genre/platform registries must
stay in lockstep with the tables they were extracted from (genre profiles,
masterengine's re-export, wizard validation, schema choices)."""

from redline import masterengine, platforms
from redline.analysis.genre import _PROFILES
from redline.genres import GENRE_NAMES, is_known_genre, resolve_genre_name
from redline.platforms import PLATFORM_CHOICES, PLATFORM_TARGETS
from redline.schema_validator import PRESET_SCHEMA
from redline.wizard import MixPreferences


def test_genre_profiles_match_registry():
    assert set(_PROFILES) == set(GENRE_NAMES)
    # Same order too -- GENRE_NAMES is documented as the exact current order.
    assert tuple(_PROFILES) == GENRE_NAMES


def test_genre_resolution_is_case_insensitive():
    assert resolve_genre_name("edm / urban") == "EDM / Urban"
    assert resolve_genre_name("  HIP-HOP ") == "Hip-Hop"
    assert resolve_genre_name("balanced") == "Balanced"
    assert resolve_genre_name("Some Made Up Genre") is None
    assert resolve_genre_name(None) is None


def test_is_known_genre():
    for name in GENRE_NAMES:
        assert is_known_genre(name)
    assert not is_known_genre("Some Made Up Genre")


def test_platform_targets_match_choices():
    assert set(PLATFORM_TARGETS) == set(PLATFORM_CHOICES) - {"auto"}
    assert PLATFORM_CHOICES == ("auto", "spotify", "apple", "youtube", "tidal", "amazon", "deezer", "club")


def test_platform_target_values_unchanged():
    # Behavior preservation: the exact values masterengine has always used,
    # plus the 2026 correction (youtube -13 -> -14, since YouTube has
    # normalized to -14 LUFS since 2019) and the added -14 platforms.
    assert PLATFORM_TARGETS == {
        "spotify": -14.0,
        "apple": -16.0,
        "youtube": -14.0,
        "tidal": -14.0,
        "amazon": -14.0,
        "deezer": -14.0,
        "club": -9.0,
    }


def test_masterengine_reexports_platform_targets():
    assert masterengine.PLATFORM_TARGETS is platforms.PLATFORM_TARGETS


def test_wizard_platform_validation_uses_registry():
    for platform in PLATFORM_CHOICES:
        assert MixPreferences(platform=platform).platform == platform
    assert MixPreferences(platform="myspace").platform == "auto"


def test_schema_validator_platform_choices_use_registry():
    assert PRESET_SCHEMA["platform"]["choices"] == list(PLATFORM_CHOICES)
