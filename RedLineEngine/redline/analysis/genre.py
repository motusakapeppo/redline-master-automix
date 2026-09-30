"""Genre detection and genre-informed mix/master defaults.

This is a rewrite of the old JUCE plugin's RuleEngine profiles (Katz/Owsinski-
informed EQ + dynamics per genre), fixed so the classifier actually uses a
*measured* sub-bass ratio instead of the old hardcoded `subBassRatio = 0.15f`
placeholder. A pretrained audio-tagging model can be swapped in later as a
second signal (see GenreProfile.confidence) without changing callers.
"""

from __future__ import annotations

import re
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
    # --- Expanded set (Wave 1, Track C1). The 6 profiles above are unchanged;
    # the 15 below are additive. Loudness/crest character per genre is taken
    # from the streaming-normalization + loudness-war references below; the
    # EQ/dynamics moves are secondary-source-informed starting points (iZotope
    # genre guides, Sound On Sound mixing articles, MusicProductionWiki) --
    # marked [secondary] where no primary spec exists. All are heuristic
    # defaults, same status as the original 6.
    #
    # Loudness anchors (integrated LUFS / PLR crest, dB):
    #   Spotify normalizes to -14 LUFS; Apple Music to -16; YouTube ~-13/-14
    #   (Spotify/Apple/EBU R128 loudness normalization docs). Club/EDM masters
    #   run hotter (-6..-9). Crest/PLR ranges below are the genre's typical
    #   dynamic character (MusicProductionWiki loudness-war / PLR tables).
    "Lo-Fi": dict(  # LUFS ~ -10..-13, crest 10-14 (warm, rolled-off top)
        bus_eq=[
            EQBand(80, 1.0, 0.7, "low_shelf"),
            EQBand(300, -1.5, 1.2, "peak"),
            EQBand(1000, 0.5, 1.0, "peak"),
            EQBand(4000, -2.0, 1.0, "peak"),   # [secondary] tape/vinyl top roll-off
            EQBand(10000, -3.0, 0.7, "high_shelf"),
        ],
        attack_ms=25.0, release_ms=200.0, ratio=2.5, threshold_db=-18.0, parallel_mix=0.30,
    ),
    "Cinematic": dict(  # LUFS ~ -14..-18, crest 14-20 (wide dynamics, big low, airy)
        bus_eq=[
            EQBand(40, 2.0, 0.7, "low_shelf"),
            EQBand(300, -1.0, 1.2, "peak"),
            EQBand(1000, 0.0, 1.0, "peak"),
            EQBand(3000, 1.0, 1.0, "peak"),
            EQBand(12000, 2.0, 0.7, "high_shelf"),
        ],
        attack_ms=30.0, release_ms=400.0, ratio=1.8, threshold_db=-14.0, parallel_mix=0.15,
    ),
    "Drum & Bass": dict(  # LUFS ~ -6..-9, crest 8-12 (tight sub, punchy, bright)
        bus_eq=[
            EQBand(50, 3.5, 0.7, "low_shelf"),
            EQBand(250, -2.0, 1.2, "peak"),
            EQBand(800, -1.0, 1.0, "peak"),
            EQBand(4000, 2.0, 1.0, "peak"),
            EQBand(10000, 2.0, 0.7, "high_shelf"),
        ],
        attack_ms=8.0, release_ms=70.0, ratio=4.0, threshold_db=-16.0, parallel_mix=0.20,
    ),
    "Reggaeton": dict(  # LUFS ~ -8..-10, crest 9-13 (dembow, sub-heavy, mid scoop)
        bus_eq=[
            EQBand(55, 3.5, 0.7, "low_shelf"),
            EQBand(300, -2.0, 1.2, "peak"),
            EQBand(900, -1.0, 1.0, "peak"),
            EQBand(3500, 2.0, 1.0, "peak"),
            EQBand(10000, 1.5, 0.7, "high_shelf"),
        ],
        attack_ms=12.0, release_ms=90.0, ratio=3.5, threshold_db=-17.0, parallel_mix=0.20,
    ),
    "Metal": dict(  # LUFS ~ -8..-11, crest 10-14 (scooped mids, tight low, aggressive top)
        bus_eq=[
            EQBand(80, 2.0, 0.7, "low_shelf"),
            EQBand(400, -3.0, 1.2, "peak"),   # [secondary] classic mid scoop
            EQBand(1000, -1.0, 1.0, "peak"),
            EQBand(3000, 2.5, 1.0, "peak"),
            EQBand(8000, 2.0, 0.7, "high_shelf"),
        ],
        attack_ms=5.0, release_ms=60.0, ratio=4.5, threshold_db=-16.0, parallel_mix=0.15,
    ),
    "Country": dict(  # LUFS ~ -12..-16, crest 12-16 (natural, mid-forward, gentle)
        bus_eq=[
            EQBand(80, 1.0, 0.7, "low_shelf"),
            EQBand(300, -1.0, 1.2, "peak"),
            EQBand(1500, 1.0, 1.0, "peak"),
            EQBand(3500, 1.5, 1.0, "peak"),
            EQBand(12000, 1.5, 0.7, "high_shelf"),
        ],
        attack_ms=20.0, release_ms=180.0, ratio=2.5, threshold_db=-18.0, parallel_mix=0.25,
    ),
    "Gospel": dict(  # LUFS ~ -12..-16, crest 12-16 (big vocals, warm, dynamic)
        bus_eq=[
            EQBand(70, 1.5, 0.7, "low_shelf"),
            EQBand(300, -1.5, 1.2, "peak"),
            EQBand(1200, 0.5, 1.0, "peak"),
            EQBand(3000, 1.5, 1.0, "peak"),
            EQBand(11000, 2.0, 0.7, "high_shelf"),
        ],
        attack_ms=22.0, release_ms=220.0, ratio=2.5, threshold_db=-17.0, parallel_mix=0.25,
    ),
    "Funk": dict(  # LUFS ~ -10..-14, crest 11-15 (punchy, tight, bright)
        bus_eq=[
            EQBand(70, 1.5, 0.7, "low_shelf"),
            EQBand(350, -1.5, 1.2, "peak"),
            EQBand(1000, 0.0, 1.0, "peak"),
            EQBand(4000, 2.0, 1.0, "peak"),
            EQBand(10000, 2.0, 0.7, "high_shelf"),
        ],
        attack_ms=10.0, release_ms=90.0, ratio=3.0, threshold_db=-17.0, parallel_mix=0.20,
    ),
    "Ambient": dict(  # LUFS ~ -14..-18, crest 15-22 (very dynamic, airy, soft)
        bus_eq=[
            EQBand(50, 1.0, 0.7, "low_shelf"),
            EQBand(300, -0.5, 1.2, "peak"),
            EQBand(1000, 0.0, 1.0, "peak"),
            EQBand(3000, 0.5, 1.0, "peak"),
            EQBand(12000, 2.5, 0.7, "high_shelf"),
        ],
        attack_ms=40.0, release_ms=600.0, ratio=1.5, threshold_db=-12.0, parallel_mix=0.10,
    ),
    "Trap": dict(  # LUFS ~ -8..-11, crest 8-12 (808 sub, sparse, crisp hats)
        bus_eq=[
            EQBand(45, 4.0, 0.7, "low_shelf"),
            EQBand(250, -2.5, 1.2, "peak"),
            EQBand(800, -1.5, 1.0, "peak"),
            EQBand(5000, 2.5, 1.0, "peak"),
            EQBand(12000, 2.0, 0.7, "high_shelf"),
        ],
        attack_ms=8.0, release_ms=80.0, ratio=4.0, threshold_db=-16.0, parallel_mix=0.20,
    ),
    "R&B": dict(  # LUFS ~ -12..-16, crest 11-15 (smooth, warm, sub present)
        bus_eq=[
            EQBand(60, 2.5, 0.7, "low_shelf"),
            EQBand(300, -2.0, 1.2, "peak"),
            EQBand(1000, -0.5, 1.0, "peak"),
            EQBand(3500, 1.5, 1.0, "peak"),
            EQBand(10000, 1.5, 0.7, "high_shelf"),
        ],
        attack_ms=15.0, release_ms=130.0, ratio=3.0, threshold_db=-17.0, parallel_mix=0.25,
    ),
    "Blues": dict(  # LUFS ~ -12..-16, crest 12-16 (warm mids, natural dynamics)
        bus_eq=[
            EQBand(70, 1.0, 0.7, "low_shelf"),
            EQBand(300, -1.0, 1.2, "peak"),
            EQBand(1000, 0.5, 1.0, "peak"),
            EQBand(3000, 1.5, 1.0, "peak"),
            EQBand(10000, 1.0, 0.7, "high_shelf"),
        ],
        attack_ms=20.0, release_ms=200.0, ratio=2.5, threshold_db=-18.0, parallel_mix=0.25,
    ),
    "Reggae": dict(  # LUFS ~ -10..-14, crest 11-15 (deep bass, laid-back, warm)
        bus_eq=[
            EQBand(50, 3.0, 0.7, "low_shelf"),
            EQBand(300, -2.0, 1.2, "peak"),
            EQBand(900, -0.5, 1.0, "peak"),
            EQBand(3500, 1.5, 1.0, "peak"),
            EQBand(10000, 1.0, 0.7, "high_shelf"),
        ],
        attack_ms=18.0, release_ms=160.0, ratio=3.0, threshold_db=-17.0, parallel_mix=0.25,
    ),
    "Afrobeats": dict(  # LUFS ~ -9..-12, crest 9-13 (bouncy, sub, bright percussion)
        bus_eq=[
            EQBand(55, 3.0, 0.7, "low_shelf"),
            EQBand(300, -2.0, 1.2, "peak"),
            EQBand(1000, -0.5, 1.0, "peak"),
            EQBand(4000, 2.0, 1.0, "peak"),
            EQBand(11000, 2.0, 0.7, "high_shelf"),
        ],
        attack_ms=12.0, release_ms=100.0, ratio=3.5, threshold_db=-17.0, parallel_mix=0.20,
    ),
    "K-Pop": dict(  # LUFS ~ -7..-10, crest 9-13 (loud, bright, polished)
        bus_eq=[
            EQBand(60, 3.0, 0.7, "low_shelf"),
            EQBand(300, -2.0, 1.2, "peak"),
            EQBand(1000, 0.0, 1.0, "peak"),
            EQBand(3500, 2.5, 1.0, "peak"),
            EQBand(12000, 2.5, 0.7, "high_shelf"),
        ],
        attack_ms=10.0, release_ms=90.0, ratio=3.5, threshold_db=-17.0, parallel_mix=0.20,
    ),
}


def genre_slug(name: str) -> str:
    """"Drum & Bass" -> "drum_bass", "R&B" -> "r_b" — a filesystem-safe,
    stable key. Same normalization as redline.targets.genre_slug (kept local
    so the analysis package doesn't import the top-level targets module)."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return slug.strip("_")


def _detect_new_genre(crest: float, sub_bass_ratio: float, dense: bool, sparse: bool) -> str:
    """Additive classifier for the 15 genres added in Wave 1 / Track C1.

    Only ever called from detect_genre()'s final `else` -- i.e. for inputs the
    original 6-genre tree already mapped to 'Balanced'. It therefore cannot
    change any of the original 6 outcomes. Requires an explicit rhythmic
    signal (dense or sparse); with no transient_density it returns 'Balanced'
    so None-density callers keep the exact pre-expansion behaviour."""
    if not dense and not sparse:
        return "Balanced"

    # crest < 10: sub-heavy but below EDM's >0.30 (already caught upstream).
    if crest < 10.0 and sub_bass_ratio > 0.10:
        return "Trap" if dense else "Reggaeton"

    # 10 <= crest < 12.
    if crest < 12.0:
        if sub_bass_ratio > 0.15:
            return "Drum & Bass" if dense else "Reggae"
        if sub_bass_ratio > 0.08:
            return "R&B" if dense else "Lo-Fi"
        return "Afrobeats" if dense else "Balanced"

    # 12 <= crest <= 14.
    if crest <= 14.0:
        if sub_bass_ratio > 0.15:
            return "Metal" if dense else "Gospel"
        if sub_bass_ratio > 0.08:
            return "Funk" if dense else "Blues"
        return "K-Pop" if dense else "Country"

    # crest > 14 (the old tree already took sub_bass_ratio < 0.15).
    if sub_bass_ratio > 0.18:
        return "Cinematic"
    if sub_bass_ratio > 0.12:
        return "Ambient"
    return "Balanced"


def detect_genre(crest: float, sub_bass_ratio: float, transient_density: float | None = None) -> GenreProfile:
    """Heuristic classifier: crest factor (dynamics) + measured sub-bass energy
    ratio, same decision boundaries as the original RuleEngine but now fed a
    real sub_bass_ratio instead of a constant. `transient_density` (onsets/sec,
    optional) breaks ties between genres that share similar crest/sub-bass but
    differ in rhythmic density — e.g. dense trap hi-hats vs sustained pads.

    The original 6-genre if/elif tree is preserved verbatim; the 15 genres
    added in Wave 1 / Track C1 are resolved by _detect_new_genre() only in the
    final `else` (the region the old tree called 'Balanced'), so no existing
    input's outcome changes."""
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
        name = _detect_new_genre(crest, sub_bass_ratio, dense, sparse)

    p = _PROFILES[name]
    return GenreProfile(name=name, **p)
