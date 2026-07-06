"""Applies a validated DSP automation suggestion (Module 2: NLP-to-DSP) to
a rendered mix. Deliberately post-mix and EQ-only for this first pass --
time-ranged compression/reverb automation would need hooks inside
mixengine.py's per-stem chain that don't exist yet; scoped down rather
than half-built. Every adjustment is applied only within its time range,
crossfaded at both edges via dsp_utils.timed_gain_curve so there's no
audible click at the chorus/verse boundary."""

from __future__ import annotations

from typing import Callable

import numpy as np

from .dsp_utils import apply_band_gain_curve, timed_gain_curve

StepCallback = Callable[[str], None]


def _noop(_msg: str) -> None:
    pass


def apply_dsp_automation(mixed: np.ndarray, sr: int, automation: dict, on_step: StepCallback = _noop) -> np.ndarray:
    """`automation` must already be the *validated* dict from
    director_safety.validate_dsp_automation -- this function trusts its
    input completely and does not re-check ranges. Returns a new array;
    never mutates `mixed` in place."""
    out = mixed.copy()
    n = out.shape[0]
    start_sec, end_sec = automation["time_range"]

    for adj in automation.get("eq_adjustments", []):
        freq = adj["freq"]
        gain_db = adj["gain_db"]
        curve = timed_gain_curve(n, sr, start_sec, end_sec, gain_db)

        if adj["type"] == "high_shelf":
            # Approximated as a wide bandpass from freq_hz up to just under
            # Nyquist -- a true shelf filter would need its own IIR design;
            # this reuses the bandpass primitive already used elsewhere in
            # the engine (spectral ducking) and is close enough for a
            # broad "add air above Xkhz" style request.
            low_hz, high_hz = freq, sr / 2.0 * 0.98
        else:  # "bell"
            low_hz, high_hz = freq / 1.5, freq * 1.5

        out = apply_band_gain_curve(out, sr, low_hz, high_hz, curve)
        on_step(
            f"Automazione DSP: {adj['type']} a {freq:.0f}Hz {gain_db:+.1f}dB "
            f"tra {start_sec:.1f}s e {end_sec:.1f}s"
        )

    return out
