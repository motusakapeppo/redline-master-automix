"""Canonical platform registry.

Single source of truth for the streaming/club loudness targets and the
platform choices the wizard/CLI/schema accept. Values are the exact ones
masterengine.py has always used (masterengine now re-exports this dict, so
`from redline.masterengine import PLATFORM_TARGETS` keeps working and
returns the same object).
"""

from __future__ import annotations

# LUFS integrated-loudness targets per platform (streaming normalizes to
# these). "club" is a louder target for EDM/club-oriented material.
PLATFORM_TARGETS: dict[str, float] = {
    "spotify": -14.0,
    "apple": -16.0,
    "youtube": -13.0,
    "club": -9.0,
}

# "auto" = let the engine pick from the detected genre (see
# masterengine._target_lufs_for_genre); the rest are explicit overrides.
PLATFORM_CHOICES: tuple[str, ...] = ("auto",) + tuple(PLATFORM_TARGETS)
