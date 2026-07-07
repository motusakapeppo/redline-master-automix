"""Genre spectral targets: real measured reference curves when available,
approximate built-in heuristics otherwise.

The built-in TARGET_BAND_RATIOS in qc.py are theoretical approximations. To
match the actual record market, run `profile_targets.py` over a folder of
commercial reference tracks per genre — it writes a JSON here (one per
genre) holding the measured Long-Term Average Spectrum as band-energy
ratios. This loader prefers that measured file if it exists, so the QC pass
compares against the real industry average rather than a guessed curve, with
zero code change needed once the JSON appears.
"""

from __future__ import annotations

import json
import os
import re

from redline.logging_setup import get_logger

logger = get_logger(__name__)

TARGETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "targets")


def genre_slug(genre_name: str) -> str:
    """"EDM / Urban" -> "edm_urban" — a filesystem-safe stable key."""
    slug = genre_name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return slug.strip("_")


def target_path(genre_name: str) -> str:
    return os.path.join(TARGETS_DIR, f"target_{genre_slug(genre_name)}.json")


def load_measured_target(genre_name: str) -> dict[str, float] | None:
    """Returns the measured band-ratio target for a genre if a profiled JSON
    exists and is valid, else None (caller falls back to the built-in curve)."""
    path = target_path(genre_name)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        ratios = data.get("band_ratios", data)  # accept either wrapped or bare
        if not isinstance(ratios, dict):
            return None
        return {k: float(v) for k, v in ratios.items()}
    except Exception:
        logger.warning("Failed to load measured target for '%s'", genre_name, exc_info=True)
        return None
