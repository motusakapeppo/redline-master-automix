"""Genre-set expansion (Wave 1, Track C1).

Locks the expanded genre registry together across every table that has to
agree on the genre set, and characterizes detect_genre() so the 15 new
genres are reachable *without* changing the outcome for any input the old
6-genre tree already classified.

Coupling contract (all four tables must list exactly the same names):
  - redline.analysis.genre._PROFILES
  - redline.genres.GENRE_NAMES
  - redline.reference_profiles.CREST_FACTOR_TARGETS
  - redline.reference_profiles.MONO_COMPATIBILITY_TARGETS
  - redline.qc.TARGET_BAND_RATIOS
"""

from __future__ import annotations

from redline.analysis.genre import _PROFILES, detect_genre, genre_slug
from redline.genres import GENRE_NAMES
from redline.qc import TARGET_BAND_RATIOS
from redline.reference_profiles import (
    CREST_FACTOR_TARGETS,
    MONO_COMPATIBILITY_TARGETS,
)

# The 15 genres added on top of the original 6, in registry order.
NEW_GENRES = (
    "Lo-Fi",
    "Cinematic",
    "Drum & Bass",
    "Reggaeton",
    "Metal",
    "Country",
    "Gospel",
    "Funk",
    "Ambient",
    "Trap",
    "R&B",
    "Blues",
    "Reggae",
    "Afrobeats",
    "K-Pop",
)

ORIGINAL_GENRES = (
    "EDM / Urban",
    "Pop / Rock",
    "Acoustic / Classical",
    "Jazz / Vintage",
    "Hip-Hop",
    "Balanced",
)


def test_all_genres_coupled():
    """Every table that keys on genre name must agree on the exact set."""
    assert set(_PROFILES) == set(GENRE_NAMES)
    # Order too: GENRE_NAMES is documented as the exact _PROFILES order.
    assert tuple(_PROFILES) == GENRE_NAMES

    for name in GENRE_NAMES:
        assert name in CREST_FACTOR_TARGETS, f"{name} missing from CREST_FACTOR_TARGETS"
        assert name in MONO_COMPATIBILITY_TARGETS, f"{name} missing from MONO_COMPATIBILITY_TARGETS"
        assert name in TARGET_BAND_RATIOS, f"{name} missing from TARGET_BAND_RATIOS"


def test_original_six_kept_first_and_unchanged():
    """The original 6 names stay first, in their original order."""
    assert GENRE_NAMES[:6] == ORIGINAL_GENRES
    assert set(NEW_GENRES).issubset(set(GENRE_NAMES))
    assert len(GENRE_NAMES) == 21


def test_target_band_ratios_sum_to_one():
    """Each 6-band fallback curve is a normalized energy distribution."""
    for name, ratios in TARGET_BAND_RATIOS.items():
        assert set(ratios) == {"sub_bass", "bass", "low_mid", "mid", "high_mid", "air"}, name
        assert abs(sum(ratios.values()) - 1.0) < 1e-6, f"{name} sums to {sum(ratios.values())}"


def test_new_genre_boundaries():
    """Concrete (crest, sub_bass_ratio, transient_density) tuples that must
    resolve to each new genre. Every tuple falls in the region the old tree
    mapped to 'Balanced', so these branches are purely additive."""
    cases = {
        "Lo-Fi": (11.0, 0.12, 1.0),
        "R&B": (11.0, 0.12, 5.0),
        "Drum & Bass": (11.0, 0.18, 5.0),
        "Reggae": (11.0, 0.18, 1.0),
        "Afrobeats": (11.0, 0.05, 5.0),
        "Trap": (9.0, 0.15, 5.0),
        "Reggaeton": (9.0, 0.15, 1.0),
        "Metal": (13.0, 0.18, 5.0),
        "Gospel": (13.0, 0.18, 1.0),
        "Funk": (13.0, 0.14, 5.0),
        "Blues": (13.0, 0.14, 1.0),
        "Country": (13.0, 0.05, 1.0),
        "K-Pop": (13.0, 0.05, 5.0),
        "Cinematic": (17.0, 0.19, 1.0),
        "Ambient": (15.0, 0.16, 1.0),
    }
    assert set(cases) == set(NEW_GENRES)
    for expected, (crest, sub, density) in cases.items():
        got = detect_genre(crest, sub, transient_density=density).name
        assert got == expected, f"crest={crest} sub={sub} density={density}: {got} != {expected}"


def test_existing_boundaries_unchanged():
    """Characterization: the original 6-genre decision tree must still map
    these inputs exactly as before the expansion."""
    cases = {
        "EDM / Urban": (8.0, 0.40, 5.0),
        "Hip-Hop": (11.0, 0.40, 5.0),
        "Pop / Rock": (11.0, 0.25, 5.0),
        "Jazz / Vintage": (15.0, 0.10, 5.0),
        "Acoustic / Classical": (15.0, 0.10, 1.0),
        "Jazz / Vintage (2nd path)": (13.0, 0.25, 5.0),
        "Acoustic / Classical (2nd path)": (13.0, 0.25, 1.0),
        # Moderate density (neither dense nor sparse) stays the fallback.
        "Balanced": (12.0, 0.15, 3.0),
    }
    for label, (crest, sub, density) in cases.items():
        expected = label.split(" (")[0]
        got = detect_genre(crest, sub, transient_density=density).name
        assert got == expected, f"{label}: {got} != {expected}"


def test_existing_boundaries_unchanged_without_density():
    """Same characterization with transient_density omitted (None): the
    original 6 outcomes must not shift either. New genres require a density
    signal, so None-density Balanced-region inputs stay 'Balanced'."""
    cases = {
        "EDM / Urban": (8.0, 0.40),
        "Hip-Hop": (11.0, 0.40),
        "Pop / Rock": (11.0, 0.25),
        "Acoustic / Classical": (15.0, 0.10),
        "Jazz / Vintage": (13.0, 0.25),
        "Balanced": (12.0, 0.15),
    }
    for label, (crest, sub) in cases.items():
        got = detect_genre(crest, sub).name
        assert got == label, f"{label}: {got} != {label}"


def test_genre_slugs_unique():
    slugs = {genre_slug(g) for g in GENRE_NAMES}
    assert len(slugs) == len(GENRE_NAMES)


def test_genre_slug_examples():
    assert genre_slug("Drum & Bass") == "drum_bass"
    assert genre_slug("R&B") == "r_b"
    assert genre_slug("Acoustic / Classical") == "acoustic_classical"
    assert genre_slug("K-Pop") == "k_pop"
    assert genre_slug("Lo-Fi") == "lo_fi"
