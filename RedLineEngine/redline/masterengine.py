"""Optional mastering pass: loudness targeting for streaming platforms +
true-peak limiting, or reference-matched mastering via `matchering`."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pyloudnorm as pyln
from pedalboard import Pedalboard, Limiter, Gain

from .analyze import AnalysisResult

StepCallback = Callable[[str], None]


def _noop(_msg: str) -> None:
    pass


# LUFS integrated-loudness targets per platform (streaming normalizes to these)
PLATFORM_TARGETS = {
    "spotify": -14.0,
    "apple": -16.0,
    "youtube": -13.0,
    "club": -9.0,  # louder target for EDM/club-oriented material
}

TRUE_PEAK_CEILING_DB = -1.0


def _target_lufs_for_genre(genre_name: str, platform: str) -> float:
    if platform == "auto":
        return PLATFORM_TARGETS["club"] if "EDM" in genre_name else PLATFORM_TARGETS["spotify"]
    return PLATFORM_TARGETS.get(platform, PLATFORM_TARGETS["spotify"])


def render_master(
    mixed: np.ndarray,
    sr: int,
    analysis: AnalysisResult,
    platform: str = "auto",
    on_step: StepCallback = _noop,
) -> np.ndarray:
    meter = pyln.Meter(sr)
    mono_ref = mixed.mean(axis=1) if mixed.ndim == 2 else mixed
    try:
        current_lufs = meter.integrated_loudness(mono_ref)
    except ValueError:
        current_lufs = -70.0

    target_lufs = _target_lufs_for_genre(analysis.genre.name, platform)
    gain_db = target_lufs - current_lufs
    # Guardrails: never boost more than +12dB (would just raise noise floor) or
    # cut more than -12dB (source was already far louder than any sane target).
    gain_db = float(np.clip(gain_db, -12.0, 12.0))

    on_step(f"Loudness misurata: {current_lufs:.1f} LUFS -> target {target_lufs:.1f} LUFS ({gain_db:+.1f}dB)")

    board = Pedalboard(
        [
            Gain(gain_db=gain_db),
            Limiter(threshold_db=TRUE_PEAK_CEILING_DB, release_ms=100.0),
        ]
    )
    on_step(f"Limiting finale a {TRUE_PEAK_CEILING_DB}dB true-peak ceiling")
    mastered = board(mixed.T, sr).T

    # pedalboard's Limiter can still overshoot on hard transients when the
    # requested makeup gain is large (its envelope needs a moment to react) —
    # this hard clamp is the actual guarantee that the promised ceiling holds,
    # the limiter above just keeps it musical rather than doing all the work.
    ceiling = 10.0 ** (TRUE_PEAK_CEILING_DB / 20.0)
    peak = np.max(np.abs(mastered)) + 1e-9
    if peak > ceiling:
        mastered = mastered * (ceiling / peak)

    on_step("Mastering completato.")
    return mastered


def render_master_reference(mix_path: str, reference_path: str, output_path: str, on_step: StepCallback = _noop) -> None:
    """Alternative mastering strategy: match tonal balance and loudness to a
    user-supplied reference track via matchering, instead of fixed platform
    LUFS targets."""
    import matchering as mg

    on_step(f"Mastering per riferimento: adatto il timbro/loudness a '{reference_path}'")
    mg.process(
        target=mix_path,
        reference=reference_path,
        results=[mg.pcm24(output_path)],
    )
    on_step("Mastering per riferimento completato.")
