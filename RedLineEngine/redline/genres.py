"""Canonical genre registry.

The six genre names the engine knows about, in the same order as
redline.analysis.genre._PROFILES (the profile table itself stays where it
is -- this module is the single source of truth for *names*, so callers
that only need to validate or resolve a genre string don't have to import
the analysis package). tests/test_registry.py locks the two together.
"""

from __future__ import annotations

GENRE_NAMES: tuple[str, ...] = (
    "EDM / Urban",
    "Pop / Rock",
    "Acoustic / Classical",
    "Jazz / Vintage",
    "Hip-Hop",
    "Balanced",
)


def resolve_genre_name(name: str) -> str | None:
    """Canonical genre name for `name` (case-insensitive exact match,
    surrounding whitespace ignored), or None if it isn't a known genre.

    Returns None rather than raising: callers use this both for validation
    (is_known_genre) and for normalizing user input, and "unknown genre" is
    an expected case -- qc.resolve_target and
    reference_profiles.resolve_perceptual_target both already fall back to
    'Balanced' for unrecognized names."""
    if not isinstance(name, str):
        return None
    lowered = name.strip().lower()
    for canonical in GENRE_NAMES:
        if canonical.lower() == lowered:
            return canonical
    return None


def is_known_genre(name: str) -> bool:
    """True if `name` resolves to one of GENRE_NAMES (case-insensitive)."""
    return resolve_genre_name(name) is not None
