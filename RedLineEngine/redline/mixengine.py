"""The actual mixing logic. Takes the Stems + AnalysisResult + MixPreferences
and renders a stereo mixdown via pedalboard (JUCE-based DSP).

Design rules encoded here (from DSP_Rules_Summary.md / Stavrou / Eargle /
Katz-Owsinski, and this time actually applied to the audio, unlike the old
plugin):
  - Only one element should "own" the low end: bass/kick keep full range,
    everything else gets high-passed to reduce mud and masking — but the
    vocal's high-pass cutoff tracks its actual measured fundamental instead
    of a fixed 100Hz that would gut a baritone/bass voice.
  - Avoid solo-EQing every stem with the same favorite frequency (Stavrou's
    warning) — the bus EQ, not per-stem EQ, carries the genre-specific tonal
    shape; per-stem EQ only does corrective, *measured* resonance cuts.
  - The lead vocal ("Main") is the star: full-range, centered, presence-
    boosted, minimally processed. Doubles/harmonies are support: time-
    aligned to the lead so they don't smear it, then thinned, panned hard,
    and pulled back in level — they are not supposed to compete with the
    lead for space.
  - Vocal is ducked into the mix spectrally (only the ~1-4kHz band the
    vocal actually occupies gets pulled back in the instrumental), not by
    ducking the instrumental broadband, which pumps audibly.
  - Compression ratios are multiplicative across stages (Stavrou's warning),
    so per-stem compression stays gentle; a parallel (New York-style) bus
    adds punch/weight without crushing transients, and glue/limiting happens
    once, on the bus.
"""

from __future__ import annotations

from typing import Callable

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
from .analyze import AnalysisResult, has_sub_content
from .analysis import EQBand
from .analysis.pitch import estimate_fundamental
from .wizard import MixPreferences
from .dsp_utils import (
    duck_gain_curve,
    apply_gain_curve,
    apply_band_gain_curve,
    db_to_gain,
    pan_stereo,
)
from .naming import parse_stem, StemDescriptor
from .deesser import deess
from .resonance import find_resonance
from .alignment import align_to_reference

# Narration (text, for the log) and structured events (real parameter values,
# for the future animated UI — an EQ knob turning to an actual cut/boost, a
# gain-reduction meter moving with the real GR amount, etc. — not a generic
# stock animation). Both are optional so tests/CLI can ignore either.
StepCallback = Callable[[str], None]
EventCallback = Callable[[dict], None]


def _noop(_msg: str) -> None:
    pass


def _noop_event(_evt: dict) -> None:
    pass


# A vocal "double"/harmony take sits hard-panned and slightly under the lead,
# never as loud or as central — this is what the take actually is for.
DOUBLE_GAIN_DB = -4.0
DOUBLE_HPF_HZ = 150.0
DOUBLE_AIR_CUT_DB = -1.5  # gentle high-shelf pullback so doubles sit *behind* the lead
LEAD_PRESENCE_FREQ_HZ = 3000.0
LEAD_PRESENCE_GAIN_DB = 1.5
VOCAL_DUCK_BAND_HZ = (1000.0, 4000.0)  # the band a lead vocal actually occupies most
PARALLEL_BUS_MIX = 0.22


def _describe(d: StemDescriptor) -> str:
    bits = [d.role]
    if d.role == "vocal":
        bits.append(d.layer)
        if d.pan > 0:
            bits.append("pan dx")
        elif d.pan < 0:
            bits.append("pan sx")
    if d.section:
        bits.append(d.section)
    if d.register:
        bits.append(d.register)
    return "/".join(bits)


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


def _process_stem(
    name: str,
    audio: np.ndarray,
    sr: int,
    descriptor: StemDescriptor,
    on_step: StepCallback,
    on_event: EventCallback,
) -> np.ndarray:
    role = descriptor.role
    is_lead_vocal = role == "vocal" and descriptor.layer == "primary"
    is_double_vocal = role == "vocal" and descriptor.layer == "double"

    board_fx: list = []

    # --- High-pass: adaptive for the lead vocal (tracks its real range),
    # fixed but role-appropriate for everything else. Only bass keeps the
    # full low end — it's the one element allowed to own that space.
    if is_lead_vocal:
        fundamental = estimate_fundamental(audio, sr)
        hpf_hz = float(np.clip(fundamental / 2.0, 40.0, 150.0))
        on_event({"type": "dynamic_hpf", "stem": name, "fundamental_hz": round(fundamental, 1), "cutoff_hz": round(hpf_hz, 1)})
        board_fx.append(HighpassFilter(cutoff_frequency_hz=hpf_hz))
    elif is_double_vocal:
        hpf_hz = DOUBLE_HPF_HZ
        board_fx.append(HighpassFilter(cutoff_frequency_hz=hpf_hz))
    elif role == "other":
        hpf_hz = 60.0
        board_fx.append(HighpassFilter(cutoff_frequency_hz=hpf_hz))
    elif role == "drums":
        hpf_hz = 30.0
        board_fx.append(HighpassFilter(cutoff_frequency_hz=hpf_hz))
    # bass: no HPF

    # --- Adaptive resonance suppression: cut only where THIS stem's energy
    # actually piles up in the mud range, only if it's a real accumulation
    # (replaces a fixed always-on 250-300Hz cut).
    resonance = find_resonance(audio, sr)
    if resonance is not None:
        on_step(f"  '{name}': risonanza rilevata a {resonance.freq:.0f}Hz, taglio {resonance.gain_db:.1f}dB")
        on_event({"type": "resonance_cut", "stem": name, "freq_hz": round(resonance.freq, 1), "gain_db": round(resonance.gain_db, 1)})
        board_fx.append(PeakFilter(cutoff_frequency_hz=resonance.freq, gain_db=resonance.gain_db, q=resonance.q))

    if is_lead_vocal:
        # The lead is the star: give it presence instead of just carving cuts.
        board_fx.append(PeakFilter(cutoff_frequency_hz=LEAD_PRESENCE_FREQ_HZ, gain_db=LEAD_PRESENCE_GAIN_DB, q=1.0))
    elif is_double_vocal:
        # Pull doubles back in the air band so they read as "behind" the lead.
        board_fx.append(HighShelfFilter(cutoff_frequency_hz=6000.0, gain_db=DOUBLE_AIR_CUT_DB, q=0.7))

    # --- Gentle per-stem compression only (glue/limiting happens once on the
    # bus, per Stavrou's warning that ratios multiply across stages).
    role_comp = {
        "vocal": dict(threshold_db=-20.0, ratio=2.2 if is_lead_vocal else 2.8, attack_ms=8.0, release_ms=120.0),
        "bass": dict(threshold_db=-18.0, ratio=3.0, attack_ms=10.0, release_ms=150.0),
        "drums": dict(threshold_db=-16.0, ratio=2.5, attack_ms=5.0, release_ms=100.0),
        "other": dict(threshold_db=-20.0, ratio=2.0, attack_ms=15.0, release_ms=180.0),
    }[role]
    on_event({"type": "compressor", "stem": name, **role_comp})
    board_fx.append(Compressor(**role_comp))

    board = Pedalboard(board_fx)
    out = board(audio.T, sr).T

    if role == "vocal":
        # After compression, not before: compression tends to bring sibilance
        # up along with everything else. Adaptive: finds this stem's real
        # sibilance frequency instead of assuming a fixed 5-9kHz band.
        from .deesser import detect_sibilance_band

        band = detect_sibilance_band(out, sr)
        on_event({"type": "deesser", "stem": name, "low_hz": round(band.low_hz, 0), "high_hz": round(band.high_hz, 0)})
        out = deess(out, sr, band=band)

    return out


def render_mix(
    stems: Stems,
    analysis: AnalysisResult,
    prefs: MixPreferences,
    on_step: StepCallback = _noop,
    on_event: EventCallback = _noop_event,
) -> np.ndarray:
    sr = stems.sample_rate
    n = stems.num_samples()

    descriptors = {name: parse_stem(name) for name in stems.names()}

    # --- Role validation: don't trust a "bass" file name blindly if the
    # actual audio has no real sub content (a mislabeled or midrange-heavy
    # file would otherwise get the "never high-passed, owns the low end"
    # treatment it doesn't deserve, and nothing else would take that role).
    for name, d in descriptors.items():
        if d.role == "bass" and not has_sub_content(stems.tracks[name], sr):
            on_step(f"Attenzione: '{name}' è etichettato come basso ma non ha contenuto sub reale — trattato come 'other'")
            on_event({"type": "role_correction", "stem": name, "from": "bass", "to": "other"})
            descriptors[name] = StemDescriptor(raw_name=d.raw_name, role="other", layer=d.layer, pan=d.pan, section=d.section, register=d.register)

    roles = {name: d.role for name, d in descriptors.items()}
    on_step(
        "Stem riconosciuti: "
        + ", ".join(f"{name} -> {_describe(d)}" for name, d in descriptors.items())
    )

    # --- Time-align vocal doubles to the lead vocal reference so they
    # reinforce it instead of smearing it (doubles recorded even slightly
    # off-time create a flammed, amateurish blur once mixed in).
    lead_names = [name for name, d in descriptors.items() if d.role == "vocal" and d.layer == "primary"]
    double_names = [name for name, d in descriptors.items() if d.role == "vocal" and d.layer == "double"]

    working_tracks = dict(stems.tracks)
    if lead_names and double_names:
        lead_reference = sum(working_tracks[n] for n in lead_names)
        for name in double_names:
            aligned, delay = align_to_reference(working_tracks[name], lead_reference, sr)
            if delay != 0:
                on_step(f"  '{name}' allineata alla voce principale ({delay / sr * 1000:+.1f}ms)")
                on_event({"type": "time_align", "stem": name, "delay_ms": round(delay / sr * 1000.0, 1)})
            working_tracks[name] = aligned

    processed: dict[str, np.ndarray] = {}
    for name, audio in working_tracks.items():
        d = descriptors[name]
        on_step(f"Elaborazione stem '{name}' ({_describe(d)})...")
        processed[name] = _process_stem(name, audio, sr, d, on_step, on_event)

        if d.role == "vocal" and d.layer == "double":
            # Doubles/harmonies: hard-panned per dx/sx and sat under the lead,
            # not centered and not fighting it for level.
            processed[name] = pan_stereo(processed[name], d.pan) * db_to_gain(DOUBLE_GAIN_DB)

    # --- Spectral (not broadband) ducking: pull back only the band the
    # vocal actually occupies (~1-4kHz) in the instrumental/drums, instead
    # of ducking their whole signal — avoids the audible "pumping" of naive
    # broadband sidechain compression while still making room for the vocal.
    if lead_names:
        vocal_key = sum(processed[n] for n in lead_names)
        duck_amount_db = 3.0 + prefs.aggressiveness * 1.0
        on_step(f"Ducking spettrale ({VOCAL_DUCK_BAND_HZ[0]:.0f}-{VOCAL_DUCK_BAND_HZ[1]:.0f}Hz): strumentale/batteria si abbassano solo lì quando canta la voce")
        on_event({"type": "spectral_duck", "band_low_hz": VOCAL_DUCK_BAND_HZ[0], "band_high_hz": VOCAL_DUCK_BAND_HZ[1], "amount_db": round(duck_amount_db, 1)})
        gain_curve = duck_gain_curve(vocal_key, sr, amount_db=duck_amount_db)
        for name, role in roles.items():
            if role in ("other", "drums"):
                processed[name] = apply_band_gain_curve(processed[name], sr, VOCAL_DUCK_BAND_HZ[0], VOCAL_DUCK_BAND_HZ[1], gain_curve)

    # Gain-stage vocal prominence: +/- up to 5dB relative to everything else
    # (applies to lead and doubles alike, preserving their relative balance)
    vocal_gain_db = prefs.vocal_prominence * 5.0
    vocal_names = lead_names + double_names
    if vocal_names:
        on_step(f"Regolazione presenza voce: {vocal_gain_db:+.1f}dB")
    for name in vocal_names:
        processed[name] = processed[name] * db_to_gain(vocal_gain_db)

    # --- Parallel (New York) compression bus for drums + lead vocal: adds
    # weight/punch by blending in a hard-compressed copy, rather than
    # crushing the clean signal's own transients.
    parallel_source_names = [n for n in (list(lead_names)) if n in processed] + [
        n for n, r in roles.items() if r == "drums" and n in processed
    ]
    parallel_bus = None
    if parallel_source_names:
        parallel_bus = np.zeros((n, 2), dtype=np.float32)
        for name in parallel_source_names:
            parallel_bus += processed[name]
        ny_board = Pedalboard(
            [Compressor(threshold_db=-32.0, ratio=8.0, attack_ms=1.0, release_ms=100.0), Gain(gain_db=2.0)]
        )
        parallel_bus = ny_board(parallel_bus.T, sr).T
        on_step(f"Bus parallelo (New York compression) su voce+batteria, mix {PARALLEL_BUS_MIX * 100:.0f}%")
        on_event({"type": "parallel_bus", "mix": PARALLEL_BUS_MIX, "sources": parallel_source_names})

    mix_bus = np.zeros((n, 2), dtype=np.float32)
    for audio in processed.values():
        mix_bus += audio
    if parallel_bus is not None:
        mix_bus += parallel_bus * PARALLEL_BUS_MIX

    on_step(f"Applico EQ di bus per genere '{analysis.genre.name}' (tilt calore: {prefs.warmth:+.1f})")
    genre_bands = _scaled_bands(analysis.genre.bus_eq, prefs.warmth)
    bus_fx = [_eq_plugin(b) for b in genre_bands]
    for b in genre_bands:
        on_event({"type": "bus_eq_band", "freq_hz": b.freq, "gain_db": round(b.gain_db, 1), "q": b.q, "kind": b.kind})

    # Bus glue compression, scaled by aggressiveness (1..5 -> ratio multiplier 0.7x..1.6x)
    ratio_scale = 0.7 + (prefs.aggressiveness - 1) * 0.225
    glue_ratio = max(1.1, analysis.genre.ratio * ratio_scale)
    on_step(f"Compressione glue sul bus: ratio {glue_ratio:.1f}:1 (aggressività {prefs.aggressiveness}/5)")
    on_event({"type": "bus_compressor", "ratio": round(glue_ratio, 2), "threshold_db": analysis.genre.threshold_db})
    bus_fx.append(
        Compressor(
            threshold_db=analysis.genre.threshold_db,
            ratio=glue_ratio,
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
        on_step("Picco oltre -1dBFS: applico gain di sicurezza")
        mixed = mixed * (ceiling / peak)

    on_step("Mix completato.")
    on_event({"type": "done", "stage": "mix"})
    return mixed
