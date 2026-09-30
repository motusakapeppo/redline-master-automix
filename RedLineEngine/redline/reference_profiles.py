"""Batch driver for profile_targets.py: scans `reference_tracks/<genre_slug>/`
for user-supplied audio and (re)builds every genre's measured target JSON in
one call, instead of running `python -m redline.profile_targets` by hand per
genre.

Usage:
    python -m redline.reference_profiles

Drop legally-obtained, professionally-produced reference tracks (Creative
Commons, purchased lossless, or your own masters) into
`reference_tracks/<genre_slug>/` -- see reference_tracks/README.md. Folders
with too few files are skipped (a couple of tracks isn't a meaningful average
industry curve). Genres with no folder, or an empty one, keep using the
built-in heuristic curve in qc.TARGET_BAND_RATIOS -- this is additive, never a
requirement.
"""

from __future__ import annotations

import os

from redline.logging_setup import get_logger
from .profile_targets import AUDIO_EXTENSIONS, profile_folder
from .qc import TARGET_BAND_RATIOS
from .targets import TARGETS_DIR, genre_slug, target_path

logger = get_logger(__name__)

REFERENCE_TRACKS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reference_tracks")

MIN_TRACKS_FOR_PROFILE = 3  # fewer than this isn't a meaningful LTAS average


def _slug_to_genre() -> dict[str, str]:
    # "Balanced" is included: even though it's genre.py's fallback profile
    # (used when detect_genre() can't confidently pick one of the other 5),
    # it's still a real target curve tracks get measured against, so it gets
    # its own drop folder like every other genre.
    return {genre_slug(name): name for name in TARGET_BAND_RATIOS}


# --- Perceptual targets beyond LTAS band ratios: crest factor and mono/
# stereo-width compatibility, used by masterengine.py's iterative correction
# loop (point 2 of the reference-profile upgrade). No measured-file blending
# for these two yet (would need a folder of real masters to average, same as
# the LTAS bands) -- built-in numeric defaults only, derived below from
# values already resolved elsewhere in the engine, not invented.

# Crest factor: midpoint of the crest-factor range redline.analysis.genre's
# detect_genre() already uses to *recognize* each genre (its own decision
# boundaries), since no single resolved "target crest" value exists
# elsewhere in DSP_ENGINE_SPECS.md.
#   EDM / Urban:          crest < 10                              -> midpoint [6, 10]   = 8.0
#   Hip-Hop:               crest < 13, denser sub-bass              -> midpoint [8, 13]   = 10.5
#   Pop / Rock:             crest < 12                               -> midpoint [9, 12]   = 10.5
#   Jazz / Vintage:         crest > 12, moderate sub-bass, or dense   -> midpoint [12, 16]  = 14.0
#   Acoustic / Classical:   crest > 14, sparse                        -> midpoint [14, 20]  = 17.0
#   Balanced:               falls between all the above               -> 12.0 (dead center)
CREST_FACTOR_TARGETS: dict[str, float] = {
    "EDM / Urban": 8.0,
    "Hip-Hop": 10.5,
    "Pop / Rock": 10.5,
    "Jazz / Vintage": 14.0,
    "Acoustic / Classical": 17.0,
    "Balanced": 12.0,
    # --- Wave 1 / Track C1 expansion: midpoint of each genre's researched
    # crest/PLR range (see genre.py's per-genre loudness anchors; ranges from
    # MusicProductionWiki PLR tables + Spotify/Apple normalization docs).
    "Lo-Fi": 12.0,        # 10-14
    "Cinematic": 17.0,    # 14-20
    "Drum & Bass": 10.0,  # 8-12
    "Reggaeton": 11.0,    # 9-13
    "Metal": 12.0,        # 10-14
    "Country": 14.0,      # 12-16
    "Gospel": 14.0,       # 12-16
    "Funk": 13.0,         # 11-15
    "Ambient": 18.5,      # 15-22
    "Trap": 10.0,         # 8-12
    "R&B": 13.0,          # 11-15
    "Blues": 14.0,        # 12-16
    "Reggae": 13.0,       # 11-15
    "Afrobeats": 11.0,    # 9-13
    "K-Pop": 11.0,        # 9-13
}

# Mono/stereo-width compatibility target: qc.py's own QC pass floor is
# "> 0.6" (run_qc's `passed` check) -- that's the minimum acceptable, not a
# target. Bass-heavy, mono-critical genres (club PA systems, phone speakers)
# are targeted tighter/more mono-safe; genres with more natural room/stage
# stereo (acoustic/orchestral recordings, wide-panned jazz kits) are targeted
# looser, interpolating between qc.py's 0.6 floor and a perfectly-correlated
# 1.0.
MONO_COMPATIBILITY_TARGETS: dict[str, float] = {
    "EDM / Urban": 0.90,           # club/PA systems -- sub must fold to mono cleanly
    "Hip-Hop": 0.88,                # 808-driven, same mono-bass requirement
    "Pop / Rock": 0.80,
    "Jazz / Vintage": 0.72,         # wider live-kit/room stereo image is expected
    "Acoustic / Classical": 0.68,   # natural hall/room stereo decorrelation
    "Balanced": 0.78,
    # --- Wave 1 / Track C1 expansion: same interpolation between qc.py's 0.6
    # floor and 1.0 -- bass-heavy club genres tighter, wide/room genres looser.
    "Lo-Fi": 0.80,
    "Cinematic": 0.70,              # wide orchestral/hybrid stereo field
    "Drum & Bass": 0.90,            # club sub, mono-critical
    "Reggaeton": 0.88,              # dembow sub, club/PA
    "Metal": 0.82,                  # tight but double-tracked guitars widen
    "Country": 0.78,
    "Gospel": 0.74,                 # big room/choir decorrelation
    "Funk": 0.80,
    "Ambient": 0.66,                # deliberately wide, decorrelated pads
    "Trap": 0.90,                   # 808 sub, mono-critical
    "R&B": 0.84,
    "Blues": 0.76,
    "Reggae": 0.86,                 # deep bass, mono-safe low end
    "Afrobeats": 0.88,              # club sub
    "K-Pop": 0.82,                  # polished, wide but controlled
}


def resolve_perceptual_target(genre_name: str) -> dict[str, float]:
    """Non-spectral reference targets for `genre_name`: target LUFS (reused
    exactly from masterengine.PLATFORM_TARGETS' own "auto" resolution logic),
    target crest factor, and target mono/stereo-width compatibility. Falls
    back to 'Balanced' for an unrecognized genre name, same convention as
    qc.resolve_target()."""
    from .masterengine import PLATFORM_TARGETS  # local import: avoids a cycle if masterengine imports us at module load

    lufs = PLATFORM_TARGETS["club"] if "EDM" in genre_name else PLATFORM_TARGETS["spotify"]
    return {
        "target_lufs": lufs,
        "crest_factor": CREST_FACTOR_TARGETS.get(genre_name, CREST_FACTOR_TARGETS["Balanced"]),
        "mono_compatibility": MONO_COMPATIBILITY_TARGETS.get(genre_name, MONO_COMPATIBILITY_TARGETS["Balanced"]),
    }


def build_all(reference_tracks_dir: str = REFERENCE_TRACKS_DIR) -> dict[str, dict]:
    """Profiles every populated genre folder under reference_tracks_dir and
    writes redline/targets/target_<slug>.json for each. Returns
    {genre_name: profile_dict} for whatever was actually (re)built."""
    slug_to_genre = _slug_to_genre()
    built: dict[str, dict] = {}

    if not os.path.isdir(reference_tracks_dir):
        logger.info("No reference_tracks/ directory found at %s -- nothing to profile.", reference_tracks_dir)
        return built

    for slug, genre_name in slug_to_genre.items():
        folder = os.path.join(reference_tracks_dir, slug)
        if not os.path.isdir(folder):
            continue
        audio_files = [f for f in os.listdir(folder) if os.path.splitext(f)[1].lower() in AUDIO_EXTENSIONS]
        if len(audio_files) < MIN_TRACKS_FOR_PROFILE:
            logger.info(
                "Skipping '%s': %d reference track(s) found, need >= %d for a meaningful profile.",
                genre_name, len(audio_files), MIN_TRACKS_FOR_PROFILE,
            )
            continue
        result = profile_folder(genre_name, folder)
        os.makedirs(TARGETS_DIR, exist_ok=True)
        with open(target_path(genre_name), "w", encoding="utf-8") as f:
            import json

            json.dump(result, f, indent=2)
        built[genre_name] = result
        logger.info("Profiled '%s' from %d track(s) -> %s", genre_name, result["n_tracks"], target_path(genre_name))

    return built


def main() -> int:
    built = build_all()
    if not built:
        print("No genre folders in reference_tracks/ had enough audio files to profile.")
        print(f"Drop tracks into reference_tracks/<genre_slug>/ -- see {REFERENCE_TRACKS_DIR}\\README.md")
        return 0
    for genre_name, result in built.items():
        print(f"{genre_name}: {result['n_tracks']} tracks -> {target_path(genre_name)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
