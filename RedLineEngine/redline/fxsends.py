"""Parallel (send/return) space: reverb + BPM-synced delay. Kept separate
from insert processing so the dry signal is preserved — this is what makes
it "space" rather than "smearing the source"."""

from __future__ import annotations

import numpy as np
from pedalboard import Pedalboard, Reverb, Delay

# Genre convention: EDM/Hip-Hop stay drier/tighter, Pop/Acoustic/Jazz get more space.
# Wave 1 / Track C1: expanded to the club/rhythmic genres that want a tight,
# dry lead (substring match, so "Drum & Bass"/"Reggaeton"/"Afrobeats" all hit).
DRY_GENRES = ("EDM", "Hip-Hop", "Trap", "Drum & Bass", "Reggaeton", "Afrobeats")
# Genres that deliberately want more space than the default wet amount.
WET_GENRES = ("Ambient", "Cinematic", "Gospel")


def genre_space_amount(genre_name: str, aggressiveness: int) -> float:
    """0..1 send amount for the lead vocal, informed by genre convention and
    the wizard's aggressiveness answer (more aggressive -> drier/tighter)."""
    if any(g in genre_name for g in DRY_GENRES):
        base = 0.10
    elif any(g in genre_name for g in WET_GENRES):
        base = 0.30
    else:
        base = 0.22
    aggressiveness_pull = (aggressiveness - 3) * 0.02  # +/-0.04 across the 1..5 range
    return float(np.clip(base - aggressiveness_pull, 0.04, 0.35))


def vocal_send(signal: np.ndarray, sr: int, bpm: float, mix: float) -> np.ndarray:
    """Short plate-style reverb + a tempo-synced (dotted-eighth) slap delay,
    blended in at `mix` — preserves the dry lead underneath."""
    if mix <= 0.0:
        return signal

    beat_seconds = 60.0 / max(bpm, 40.0)
    dotted_eighth_s = beat_seconds * 0.75
    delay_seconds = float(np.clip(dotted_eighth_s, 0.08, 0.6))

    board = Pedalboard(
        [
            Reverb(room_size=0.35, damping=0.5, wet_level=1.0, dry_level=0.0, width=0.9),
            Delay(delay_seconds=delay_seconds, feedback=0.15, mix=0.5),
        ]
    )
    wet = board(signal.T, sr).T
    return signal * (1.0 - mix) + wet * mix


def drum_room_send(signal: np.ndarray, sr: int, mix: float = 0.10) -> np.ndarray:
    """A short, subtle room reverb for drums — cohesion, not obvious space."""
    if mix <= 0.0:
        return signal
    board = Pedalboard([Reverb(room_size=0.2, damping=0.6, wet_level=1.0, dry_level=0.0, width=0.6)])
    wet = board(signal.T, sr).T
    return signal * (1.0 - mix) + wet * mix
