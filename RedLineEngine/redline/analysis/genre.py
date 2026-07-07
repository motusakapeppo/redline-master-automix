"""Genre detection and genre-informed mix/master defaults.

This is a rewrite of the old JUCE plugin's RuleEngine profiles (Katz/Owsinski-
informed EQ + dynamics per genre), fixed so the classifier actually uses a
*measured* sub-bass ratio instead of the old hardcoded `subBassRatio = 0.15f`
placeholder. A pretrained audio-tagging model can be swapped in later as a
second signal (see GenreProfile.confidence) without changing callers.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EQBand:
    freq: float
    gain_db: float
    q: float
    kind: str  # "peak" | "low_shelf" | "high_shelf"


@dataclass
class GenreProfile:
    name: str
    bus_eq: list[EQBand]
    attack_ms: float
    release_ms: float
    ratio: float
    threshold_db: float
    parallel_mix: float
    confidence: float = 1.0


_PROFILES: dict[str, dict] = {
    "EDM / Urban": dict(
        bus_eq=[
            EQBand(60, 4.0, 0.7, "low_shelf"),
            EQBand(250, -2.5, 1.2, "peak"),
            EQBand(800, -1.0, 1.0, "peak"),
            EQBand(3000, 2.0, 1.0, "peak"),
            EQBand(10000, 2.5, 0.7, "high_shelf"),
        ],
        attack_ms=12.0, release_ms=80.0, ratio=3.5, threshold_db=-18.0, parallel_mix=0.20,
    ),
    "Pop / Rock": dict(
        bus_eq=[
            EQBand(80, 1.0, 0.7, "low_shelf"),
            EQBand(250, -0.5, 1.2, "peak"),
            EQBand(1000, 0.0, 1.0, "peak"),
            EQBand(3000, 3.0, 1.0, "peak"),
            EQBand(12000, 2.5, 0.7, "high_shelf"),
        ],
        attack_ms=18.0, release_ms=120.0, ratio=3.5, threshold_db=-18.0, parallel_mix=0.30,
    ),
    "Acoustic / Classical": dict(
        bus_eq=[
            EQBand(60, 0.0, 0.7, "low_shelf"),
            EQBand(250, -0.5, 1.2, "peak"),
            EQBand(1000, 0.0, 1.0, "peak"),
            EQBand(3000, 1.0, 0.8, "peak"),
            EQBand(10000, 1.5, 0.7, "high_shelf"),
        ],
        attack_ms=20.0, release_ms=300.0, ratio=2.0, threshold_db=-16.0, parallel_mix=0.15,
    ),
    "Jazz / Vintage": dict(
        bus_eq=[
            EQBand(40, 0.5, 0.7, "low_shelf"),
            EQBand(250, -0.5, 1.0, "peak"),
            EQBand(800, -0.5, 1.0, "peak"),
            EQBand(3000, 1.5, 0.8, "peak"),
            EQBand(10000, 0.5, 0.7, "high_shelf"),
        ],
        attack_ms=18.0, release_ms=200.0, ratio=2.5, threshold_db=-18.0, parallel_mix=0.25,
    ),
    "Hip-Hop": dict(
        bus_eq=[
            EQBand(50, 4.0, 0.7, "low_shelf"),
            EQBand(250, -2.5, 1.2, "peak"),
            EQBand(800, -1.5, 1.0, "peak"),
            EQBand(3500, 2.5, 0.8, "peak"),
            EQBand(10000, 2.0, 0.7, "high_shelf"),
        ],
        attack_ms=10.0, release_ms=100.0, ratio=4.0, threshold_db=-17.0, parallel_mix=0.20,
    ),
    "Balanced": dict(
        bus_eq=[
            EQBand(80, 0.5, 0.7, "low_shelf"),
            EQBand(250, -1.0, 1.0, "peak"),
            EQBand(1000, 0.0, 1.0, "peak"),
            EQBand(3000, 1.5, 1.0, "peak"),
            EQBand(10000, 1.0, 0.7, "high_shelf"),
        ],
        attack_ms=10.0, release_ms=150.0, ratio=3.0, threshold_db=-18.0, parallel_mix=0.25,
    ),
}


def detect_genre(crest: float, sub_bass_ratio: float, transient_density: float | None = None) -> GenreProfile:
    """Heuristic classifier: crest factor (dynamics) + measured sub-bass energy
    ratio, same decision boundaries as the original RuleEngine but now fed a
    real sub_bass_ratio instead of a constant. `transient_density` (onsets/sec,
    optional) breaks ties between genres that share similar crest/sub-bass but
    differ in rhythmic density — e.g. dense trap hi-hats vs sustained pads."""
    dense = transient_density is not None and transient_density > 4.0
    sparse = transient_density is not None and transient_density < 1.5

    if crest < 10.0 and sub_bass_ratio > 0.30:
        name = "EDM / Urban"
    elif crest < 13.0 and sub_bass_ratio > 0.35:
        name = "Hip-Hop"
    elif crest < 12.0 and sub_bass_ratio > 0.20:
        name = "Pop / Rock"
    elif crest > 14.0 and sub_bass_ratio < 0.15:
        name = "Jazz / Vintage" if dense else "Acoustic / Classical"
    elif crest > 12.0 and sub_bass_ratio > 0.20:
        name = "Acoustic / Classical" if sparse else "Jazz / Vintage"
    else:
        name = "Balanced"

    p = _PROFILES[name]
    return GenreProfile(name=name, **p)
