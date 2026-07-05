"""The actual mixing logic. Takes the Stems + AnalysisResult + MixPreferences
and renders a stereo mixdown via pedalboard (JUCE-based DSP).

Design rules encoded here (from DSP_Rules_Summary.md / Stavrou / Eargle /
Katz-Owsinski, and this time actually applied to the audio, unlike the old
plugin):
  - Only one element should "own" the low end: bass/kick keep full range,
    everything else gets high-passed to reduce mud and masking.
  - Avoid solo-EQing every stem with the same favorite frequency (Stavrou's
    warning) — the bus EQ, not per-stem EQ, carries the genre-specific tonal
    shape; per-stem EQ only does corrective HPF + mud carve.
  - Vocal is the lead: the instrumental bed is sidechain-ducked under it
    instead of just turning the vocal up, which preserves headroom.
  - Compression ratios are multiplicative across stages (Stavrou's warning),
    so per-stem compression stays gentle and glue/limiting happens once, on
    the bus.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from pedalboard import (
    Pedalboard,
    HighpassFilter,
    LowShelfFilter,
    HighShelfFilter,
    PeakFilter,
    Compressor,
    Gain,
)

from .input_loader import Stems
from .analyze import AnalysisResult
from .analysis import EQBand
from .wizard import MixPreferences
from .dsp_utils import duck_gain_curve, apply_gain_curve, db_to_gain

VOCAL_HINTS = ("vocal", "vox", "voice", "lead")
BASS_HINTS = ("bass", "sub")
DRUM_HINTS = ("drum", "kick", "snare", "perc")


def classify_role(stem_name: str) -> str:
    lowered = stem_name.lower()
    if any(h in lowered for h in VOCAL_HINTS):
        return "vocal"
    if any(h in lowered for h in BASS_HINTS):
        return "bass"
    if any(h in lowered for h in DRUM_HINTS):
        return "drums"
    return "other"  # instrumental bed, "other" demucs stem, guitars, etc.


def _eq_plugin(band: EQBand):
    if band.kind == "low_shelf":
        return LowShelfFilter(cutoff_frequency_hz=band.freq, gain_db=band.gain_db, q=band.q)
    if band.kind == "high_shelf":
        return HighShelfFilter(cutoff_frequency_hz=band.freq, gain_db=band.gain_db, q=band.q)
    return PeakFilter(cutoff_frequency_hz=band.freq, gain_db=band.gain_db, q=band.q)


def _scaled_bands(bands: list[EQBand], warmth: float) -> list[EQBand]:
    """Tilts the genre EQ by the wizard's warmth answer: warm pulls highs down
    / low-mids up slightly, cold does the opposite."""
    scaled = []
    for b in bands:
        gain = b.gain_db
        if b.kind == "high_shelf":
            gain -= warmth * 1.5
        elif b.freq < 300:
            gain += warmth * 0.8
        scaled.append(EQBand(freq=b.freq, gain_db=gain, q=b.q, kind=b.kind))
    return scaled


def _process_stem(audio: np.ndarray, sr: int, role: str, analysis: AnalysisResult, prefs: MixPreferences) -> np.ndarray:
    board_fx: list = []

    # Rule: only bass/drums keep sub content; everything else gets high-passed
    # to stop low-end masking (the classic "mud" problem).
    if role == "vocal":
        board_fx.append(HighpassFilter(cutoff_frequency_hz=100.0))
        board_fx.append(PeakFilter(cutoff_frequency_hz=300.0, gain_db=-1.5, q=1.2))  # mud carve
    elif role == "other":
        board_fx.append(HighpassFilter(cutoff_frequency_hz=60.0))
        board_fx.append(PeakFilter(cutoff_frequency_hz=250.0, gain_db=-1.0, q=1.0))
    elif role == "drums":
        board_fx.append(HighpassFilter(cutoff_frequency_hz=30.0))
    # bass: no HPF, keep the full low end — it owns this range

    # Gentle per-stem compression only (glue/limiting happens once on the bus,
    # per Stavrou's warning that ratios multiply across stages).
    role_comp = {
        "vocal": dict(threshold_db=-20.0, ratio=2.5, attack_ms=8.0, release_ms=120.0),
        "bass": dict(threshold_db=-18.0, ratio=3.0, attack_ms=10.0, release_ms=150.0),
        "drums": dict(threshold_db=-16.0, ratio=2.5, attack_ms=5.0, release_ms=100.0),
        "other": dict(threshold_db=-20.0, ratio=2.0, attack_ms=15.0, release_ms=180.0),
    }[role]
    board_fx.append(Compressor(**role_comp))

    board = Pedalboard(board_fx)
    return board(audio.T, sr).T


def render_mix(stems: Stems, analysis: AnalysisResult, prefs: MixPreferences) -> np.ndarray:
    sr = stems.sample_rate
    n = stems.num_samples()

    roles = {name: classify_role(name) for name in stems.names()}
    processed = {
        name: _process_stem(audio, sr, roles[name], analysis, prefs)
        for name, audio in stems.tracks.items()
    }

    vocal_names = [n for n, r in roles.items() if r == "vocal"]
    if vocal_names:
        vocal_key = sum(processed[n] for n in vocal_names)
        duck_amount_db = 2.5 + prefs.aggressiveness * 0.8  # more aggressive -> more ducking
        gain_curve = duck_gain_curve(vocal_key, sr, amount_db=duck_amount_db)
        for name, role in roles.items():
            if role in ("other", "drums"):
                processed[name] = apply_gain_curve(processed[name], gain_curve)

    # Gain-stage vocal prominence: +/- up to 5dB relative to everything else
    vocal_gain_db = prefs.vocal_prominence * 5.0
    for name in vocal_names:
        processed[name] = processed[name] * db_to_gain(vocal_gain_db)

    mix_bus = np.zeros((n, 2), dtype=np.float32)
    for audio in processed.values():
        mix_bus += audio

    # Bus EQ: genre-informed shape, tilted by the warmth preference
    genre_bands = _scaled_bands(analysis.genre.bus_eq, prefs.warmth)
    bus_fx = [_eq_plugin(b) for b in genre_bands]

    # Bus glue compression, scaled by aggressiveness (1..5 -> ratio multiplier 0.7x..1.6x)
    ratio_scale = 0.7 + (prefs.aggressiveness - 1) * 0.225
    bus_fx.append(
        Compressor(
            threshold_db=analysis.genre.threshold_db,
            ratio=max(1.1, analysis.genre.ratio * ratio_scale),
            attack_ms=analysis.genre.attack_ms,
            release_ms=analysis.genre.release_ms,
        )
    )
    bus_fx.append(Gain(gain_db=1.0))

    bus_board = Pedalboard(bus_fx)
    mixed = bus_board(mix_bus.T, sr).T

    # Safety ceiling so the mix is a sane standalone deliverable even if the
    # user skips the mastering pass — real loudness targeting is master's job.
    peak = np.max(np.abs(mixed)) + 1e-9
    ceiling = db_to_gain(-1.0)
    if peak > ceiling:
        mixed = mixed * (ceiling / peak)

    return mixed
