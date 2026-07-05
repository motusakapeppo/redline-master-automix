"""Concurrent vocal-take level compensation. True phase-cancellation
detection is fragile and often a non-issue for separately recorded takes —
what actually matters and *is* reliably measurable is buildup: when several
"primary" lead takes are energetically active at the same moment (alternate
lines, ad-libs, a rap/autotune split across sections), summing them raises
the level unpredictably. This computes, per time-block, how many primary
vocal takes are simultaneously active and applies power-preserving gain
compensation so overlapping takes don't silently stack level."""

from __future__ import annotations

import numpy as np

from .dsp_utils import envelope_follower


def compute_activity_mask(signal: np.ndarray, sr: int, threshold_ratio: float = 0.15) -> np.ndarray:
    """1.0 where the stem is meaningfully active, 0.0 where it's silent/near-
    silent — a coarse voice-activity proxy from the envelope alone."""
    mono = signal.mean(axis=1) if signal.ndim == 2 else signal
    env = envelope_follower(np.abs(mono), sr, attack_ms=10.0, release_ms=200.0)
    reference = np.percentile(env, 90) + 1e-9
    return (env > reference * threshold_ratio).astype(np.float32)


def concurrent_take_gain_curves(tracks: dict[str, np.ndarray], sr: int) -> dict[str, np.ndarray]:
    """For a set of same-role tracks (e.g. multiple lead vocal takes), returns
    a per-track linear gain curve that divides level by sqrt(active_count) at
    each moment — power-preserving, so N simultaneously active takes don't
    just stack to N times the level."""
    if len(tracks) <= 1:
        return {name: np.ones(next(iter(tracks.values())).shape[0], dtype=np.float32) for name in tracks}

    masks = {name: compute_activity_mask(audio, sr) for name, audio in tracks.items()}
    active_count = np.sum(np.stack(list(masks.values()), axis=0), axis=0)
    active_count = np.maximum(active_count, 1.0)  # avoid dividing by zero when all are silent
    shared_gain = (1.0 / np.sqrt(active_count)).astype(np.float32)

    # Only compensate when more than one take is actually active at once —
    # a lone active take should play at full level, not be quietly attenuated.
    only_one_active = active_count <= 1.0
    curves = {}
    for name in tracks:
        curve = np.where(only_one_active, 1.0, shared_gain).astype(np.float32)
        curves[name] = curve
    return curves
