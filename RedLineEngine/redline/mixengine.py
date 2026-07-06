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
    boosted, minimally processed.
  - Doubles/harmonies are support, routed through a Backing Vocals bus with
    four register sub-buses (Low/Unison/High/Falsetto) — a wall of doubles
    only sounds like one big, defined thing if each register actually gets a
    different treatment (vocalstack.py), not one generic "double" recipe.
    Register is classified from each double's own measured pitch relative to
    the lead, not trusted blindly from the file name. Doubles are time-
    aligned to the lead first (cross-correlation) so they reinforce it
    instead of smearing it.
  - Vocal is ducked into the mix spectrally (only the ~1-4kHz band the
    vocal actually occupies gets pulled back in the instrumental), not by
    ducking the instrumental broadband, which pumps audibly. The kick/bass
    relationship gets its own separate, faster, broadband sidechain — the
    classic low-end "pumping" trick, distinct from the vocal's spectral duck.
  - Instrumental ("other") stems get a preventive, measured masking cut where
    they structurally pile up energy in the vocal's presence band, and are
    grouped into a Music bus with Mid/Side EQ (mono dip in the center where
    the vocal sits, a touch of side width) instead of each fighting for space
    independently.
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
    LowpassFilter,
    LowShelfFilter,
    HighShelfFilter,
    PeakFilter,
    Compressor,
    Gain,
    Reverb,
)

from .input_loader import Stems
from .analyze import AnalysisResult, has_sub_content
from .analysis import EQBand
from .analysis.pitch import estimate_fundamental, high_frequency_ratio
from .wizard import MixPreferences
from .dsp_utils import (
    duck_gain_curve,
    apply_gain_curve,
    apply_band_gain_curve,
    apply_eq_cut,
    saturate,
    db_to_gain,
    pan_stereo,
)
from .naming import parse_stem, StemDescriptor
from .deesser import deess, detect_sibilance_band
from .resonance import find_resonance
from .alignment import align_to_reference
from .masking import find_masking_cut
from .vocalstack import classify_register, RECIPES, EqCut
from .fxsends import genre_space_amount, vocal_send, drum_room_send
from .leveling import concurrent_take_gain_curves
from .denoise import denoise as denoise_signal
from .elastic_align import elastic_align
from .depth import (
    classify_stem_depth,
    FOREGROUND,
    MIDGROUND,
    BACKGROUND,
    FOREGROUND_AIR_SHELF_HZ,
    FOREGROUND_AIR_GAIN_DB,
    FOREGROUND_COMP_ATTACK_MS,
    FOREGROUND_COMP_RATIO,
    FOREGROUND_COMP_THRESHOLD_DB,
    BACKGROUND_LOWPASS_HZ,
    BACKGROUND_REVERB_SEND,
    BACKGROUND_COMP_ATTACK_MS,
    BACKGROUND_COMP_RATIO,
    BACKGROUND_COMP_THRESHOLD_DB,
    MIDGROUND_LOWPASS_HZ,
    MIDGROUND_REVERB_SEND,
)

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


LEAD_PRESENCE_FREQ_HZ = 3000.0
LEAD_PRESENCE_GAIN_DB = 1.5
VOCAL_DUCK_BAND_HZ = (1000.0, 4000.0)  # the band a lead vocal actually occupies most
PARALLEL_BUS_MIX = 0.22
BACKING_VOCALS_GLUE_RATIO = 2.0

# Kick/bass sidechain: a pure, fast broadband duck of the bass every time the
# drums hit — the classic "pumping" low-end trick that keeps the kick and
# bass from fighting for the same transient, separate from (and faster than)
# the vocal's spectral ducking above.
KICK_BASS_DUCK_ATTACK_MS = 2.0
KICK_BASS_DUCK_RELEASE_MS = 90.0
KICK_BASS_DUCK_BASE_DB = 3.5

# Music bus (the "other"/harmonic instruments grouped together) Mid/Side EQ:
# dip the mono center where the vocal needs to sit, widen the sides a touch
# so the instrumental still reads as large despite the dip.
MUSIC_BUS_MID_DIP_DB = -1.5
MUSIC_BUS_SIDE_WIDTH_DB = 1.0
MUSIC_BUS_SIDE_WIDTH_HZ = 6000.0


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


def _eq_cut_plugin(cut: EqCut):
    if cut.kind == "highpass":
        return HighpassFilter(cutoff_frequency_hz=cut.freq)
    if cut.kind == "low_shelf":
        return LowShelfFilter(cutoff_frequency_hz=cut.freq, gain_db=cut.gain_db, q=cut.q)
    if cut.kind == "high_shelf":
        return HighShelfFilter(cutoff_frequency_hz=cut.freq, gain_db=cut.gain_db, q=cut.q)
    return PeakFilter(cutoff_frequency_hz=cut.freq, gain_db=cut.gain_db, q=cut.q)


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
    """Lead vocal, bass, drums, other — doubles are handled separately by
    _process_double_stem, since their treatment depends on register, not
    just "is a double"."""
    role = descriptor.role
    is_lead_vocal = role == "vocal" and descriptor.layer == "primary"

    if is_lead_vocal:
        # Denoise is the very first thing that happens to a vocal, before
        # even the HPF: compressing or EQing first raises the noise floor
        # along with everything else, or changes the noise's spectral color
        # enough that the noise-profile estimator can't recognize it anymore.
        on_step(f"  '{name}': riduzione rumore di fondo")
        on_event({"type": "denoise", "stem": name})
        audio = denoise_signal(audio, sr)

    board_fx: list = []

    if is_lead_vocal:
        fundamental = estimate_fundamental(audio, sr)
        hpf_hz = float(np.clip(fundamental / 2.0, 40.0, 150.0))
        on_event({"type": "dynamic_hpf", "stem": name, "fundamental_hz": round(fundamental, 1), "cutoff_hz": round(hpf_hz, 1)})
        board_fx.append(HighpassFilter(cutoff_frequency_hz=hpf_hz))
    elif role == "other":
        board_fx.append(HighpassFilter(cutoff_frequency_hz=60.0))
    elif role == "drums":
        board_fx.append(HighpassFilter(cutoff_frequency_hz=30.0))
    # bass: no HPF — it's the one element allowed to own the low end

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
        # A chorus take gets a touch more (the section that's meant to lift),
        # a verse take stays closer to the baseline (more intimate) — reusing
        # naming.py's already-parsed section field instead of treating every
        # vocal take identically regardless of where it sits in the song.
        section_boost = 0.7 if descriptor.section == "chorus" else (-0.3 if descriptor.section == "verse" else 0.0)
        presence_gain = LEAD_PRESENCE_GAIN_DB + section_boost
        board_fx.append(PeakFilter(cutoff_frequency_hz=LEAD_PRESENCE_FREQ_HZ, gain_db=presence_gain, q=1.0))

    role_comp = {
        "vocal": dict(threshold_db=-20.0, ratio=2.2, attack_ms=8.0, release_ms=120.0),
        "bass": dict(threshold_db=-18.0, ratio=3.0, attack_ms=10.0, release_ms=150.0),
        "drums": dict(threshold_db=-16.0, ratio=2.5, attack_ms=5.0, release_ms=100.0),
        "other": dict(threshold_db=-20.0, ratio=2.0, attack_ms=15.0, release_ms=180.0),
    }[role]
    on_event({"type": "compressor", "stem": name, **role_comp})
    board_fx.append(Compressor(**role_comp))

    board = Pedalboard(board_fx)
    out = board(audio.T, sr).T

    if is_lead_vocal:
        band = detect_sibilance_band(out, sr)
        on_event({"type": "deesser", "stem": name, "low_hz": round(band.low_hz, 0), "high_hz": round(band.high_hz, 0)})
        out = deess(out, sr, band=band)

    return out


def _process_double_stem(
    name: str,
    audio: np.ndarray,
    sr: int,
    register: str,
    on_step: StepCallback,
    on_event: EventCallback,
) -> np.ndarray:
    """Register-specific chain for a vocal double/harmony (see vocalstack.py
    for why each register needs genuinely different treatment, not one
    generic "double" recipe)."""
    on_step(f"  '{name}': riduzione rumore di fondo")
    on_event({"type": "denoise", "stem": name})
    audio = denoise_signal(audio, sr)

    recipe = RECIPES[register]

    board_fx = [_eq_cut_plugin(cut) for cut in recipe.extra_eq]
    board_fx.append(
        Compressor(
            threshold_db=recipe.comp_threshold_db,
            ratio=recipe.comp_ratio,
            attack_ms=recipe.comp_attack_ms,
            release_ms=recipe.comp_release_ms,
        )
    )
    on_event({"type": "vocal_stack_register", "stem": name, "register": register, "comp_ratio": recipe.comp_ratio})

    out = Pedalboard(board_fx)(audio.T, sr).T

    # Register-appropriate de-esser aggressiveness — unisons especially need
    # a much heavier hand: several unaligned "S"s at once is a dead giveaway.
    band = detect_sibilance_band(out, sr)
    on_event({"type": "deesser", "stem": name, "low_hz": round(band.low_hz, 0), "high_hz": round(band.high_hz, 0), "register": register})
    out = deess(out, sr, band=band, threshold_db=recipe.deess_threshold_db, max_reduction_db=recipe.deess_max_reduction_db)

    if recipe.saturation_drive > 0.0:
        out = saturate(out, recipe.saturation_drive)
        on_event({"type": "saturation", "stem": name, "drive": recipe.saturation_drive})

    return out


def _reverb_send(signal: np.ndarray, sr: int, mix: float) -> np.ndarray:
    """A long, diffuse reverb blended in at `mix` — used to make falsettos
    feel like a distant cloud rather than individually-placed singers."""
    wet = Pedalboard([Reverb(room_size=0.9, damping=0.3, wet_level=1.0, dry_level=0.0, width=1.0)])(signal.T, sr).T
    return signal * (1.0 - mix) + wet * mix


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

    lead_names = [name for name, d in descriptors.items() if d.role == "vocal" and d.layer == "primary"]
    double_names = [name for name, d in descriptors.items() if d.role == "vocal" and d.layer == "double"]

    # --- Mass phase control: before any panning, align every double's
    # transients to the lead vocal via cross-correlation. Summing several
    # takes of the same person/mic without this creates real phase
    # cancellation ("boxy" comb-filtered sound), not just a timing blur.
    working_tracks = dict(stems.tracks)
    lead_fundamental = 110.0
    if lead_names:
        lead_reference_dry = sum(working_tracks[n] for n in lead_names)
        lead_fundamental = estimate_fundamental(lead_reference_dry, sr)
        if double_names:
            for name in double_names:
                aligned, delay = align_to_reference(working_tracks[name], lead_reference_dry, sr)
                if delay != 0:
                    on_step(f"  '{name}' allineata alla voce principale ({delay / sr * 1000:+.1f}ms)")
                    on_event({"type": "time_align", "stem": name, "delay_ms": round(delay / sr * 1000.0, 1)})

                # Elastic (syllable-level) correction on top of the coarse
                # cross-correlation shift above: a dragged vowel or an early
                # consonant creates smearing that a single global delay can't
                # fix. Safety-netted — a window whose required warp is too
                # large to trust is left alone rather than force-stretched.
                elastic = elastic_align(aligned, lead_reference_dry, sr)
                if elastic.windows_stretched > 0:
                    on_step(
                        f"  '{name}': allineamento elastico sillabico "
                        f"({elastic.windows_stretched}/{elastic.windows_total} finestre corrette, "
                        f"{elastic.windows_skipped_unsafe} saltate per sicurezza)"
                    )
                    on_event({
                        "type": "elastic_align",
                        "stem": name,
                        "windows_stretched": elastic.windows_stretched,
                        "windows_total": elastic.windows_total,
                        "windows_skipped": elastic.windows_skipped_unsafe,
                    })
                working_tracks[name] = elastic.audio

    processed: dict[str, np.ndarray] = {}
    for name, audio in working_tracks.items():
        d = descriptors[name]
        if d.role == "vocal" and d.layer == "double":
            continue  # handled below, register by register
        on_step(f"Elaborazione stem '{name}' ({_describe(d)})...")
        processed[name] = _process_stem(name, audio, sr, d, on_step, on_event)

        if d.role == "other":
            # Z-axis depth staging: percussive/rhythmic material (high crest
            # + high spectral flux) stays dry and full-range in front; sustained/
            # harmonic material (pads, arps) gets HF rolloff + heavy reverb —
            # air absorbs highs over distance, so this reads as "far away"
            # through EQ/reverb alone, without spending level/headroom on it.
            depth = classify_stem_depth(processed[name], sr)
            on_event({"type": "depth_stage", "stem": name, "depth": depth})

            if depth == BACKGROUND:
                # Hard low-pass (air absorbs highs over distance) + fast-attack
                # heavy compression to flatten it into an undifferentiated bed,
                # plus a big reverb send.
                on_step(f"  '{name}': sfondo (taglio sopra {BACKGROUND_LOWPASS_HZ / 1000:.0f}kHz, compressione {BACKGROUND_COMP_RATIO:.0f}:1, riverbero {BACKGROUND_REVERB_SEND * 100:.0f}%)")
                board = Pedalboard([
                    LowpassFilter(cutoff_frequency_hz=BACKGROUND_LOWPASS_HZ),
                    Compressor(threshold_db=BACKGROUND_COMP_THRESHOLD_DB, ratio=BACKGROUND_COMP_RATIO, attack_ms=BACKGROUND_COMP_ATTACK_MS, release_ms=150.0),
                ])
                processed[name] = board(processed[name].T, sr).T
                processed[name] = _reverb_send(processed[name], sr, BACKGROUND_REVERB_SEND)
            elif depth == MIDGROUND:
                # Split the difference: milder LPF/reverb, no strong dynamic
                # push either way — these stems already sit ambiguously.
                on_step(f"  '{name}': centro (taglio sopra {MIDGROUND_LOWPASS_HZ / 1000:.0f}kHz, riverbero {MIDGROUND_REVERB_SEND * 100:.0f}%)")
                processed[name] = Pedalboard([LowpassFilter(cutoff_frequency_hz=MIDGROUND_LOWPASS_HZ)])(processed[name].T, sr).T
                processed[name] = _reverb_send(processed[name], sr, MIDGROUND_REVERB_SEND)
            else:
                # Foreground: no cut, a touch of "air" shelf instead, and a
                # slower compressor attack so it doesn't squash the transients
                # that keep it sounding close and up-front.
                on_step(f"  '{name}': primo piano (aria +{FOREGROUND_AIR_GAIN_DB:.1f}dB sopra {FOREGROUND_AIR_SHELF_HZ / 1000:.0f}kHz, secco)")
                board = Pedalboard([
                    HighShelfFilter(cutoff_frequency_hz=FOREGROUND_AIR_SHELF_HZ, gain_db=FOREGROUND_AIR_GAIN_DB, q=0.7),
                    Compressor(threshold_db=FOREGROUND_COMP_THRESHOLD_DB, ratio=FOREGROUND_COMP_RATIO, attack_ms=FOREGROUND_COMP_ATTACK_MS, release_ms=150.0),
                ])
                processed[name] = board(processed[name].T, sr).T

    # --- Concurrent-take level compensation: when several lead ("Main")
    # takes are simultaneously active (alternate lines/ad-libs across
    # sections), summing them raises the level unpredictably. Power-
    # preserving compensation (1/sqrt(active_count)) instead of a fixed pad.
    if len(lead_names) > 1:
        lead_tracks = {name: processed[name] for name in lead_names}
        gain_curves = concurrent_take_gain_curves(lead_tracks, sr)
        on_step(f"Compensazione livello prese vocali multiple ({len(lead_names)} prese Main simultanee possibili)")
        on_event({"type": "concurrent_take_leveling", "stems": lead_names})
        for name in lead_names:
            processed[name] = apply_gain_curve(processed[name], gain_curves[name])

    # --- Space: a short send-style reverb + BPM-synced delay on the lead
    # vocal (genre/aggressiveness-informed amount), a subtle room send on
    # drums for cohesion. Parallel, not insert — the dry signal underneath
    # is preserved.
    if lead_names:
        base_space_mix = genre_space_amount(analysis.genre.name, prefs.aggressiveness)
        on_step(f"Spazio voce: riverbero + delay sincronizzato al BPM ({analysis.bpm:.0f}), base {base_space_mix * 100:.0f}%")
        on_event({"type": "vocal_space", "mix": round(base_space_mix, 2), "bpm": analysis.bpm})
        for name in lead_names:
            # Chorus lifts (more space, meant to open up), verse stays more
            # intimate/dry — same section-aware idea as the presence boost.
            section = descriptors[name].section
            section_scale = 1.4 if section == "chorus" else (0.7 if section == "verse" else 1.0)
            space_mix = float(np.clip(base_space_mix * section_scale, 0.0, 0.45))
            processed[name] = vocal_send(processed[name], sr, analysis.bpm, space_mix)

    drum_names_for_space = [n for n, r in roles.items() if r == "drums"]
    if drum_names_for_space:
        for name in drum_names_for_space:
            processed[name] = drum_room_send(processed[name], sr)

    # --- Vocal stack: classify each double's register from its own measured
    # pitch relative to the lead, process it with that register's recipe,
    # then route into four sub-buses (matrioska routing) so a wall of
    # doubles reads as one big, defined thing instead of mush.
    register_buses: dict[str, np.ndarray] = {}
    if double_names:
        on_step(f"Voce principale: fondamentale misurata {lead_fundamental:.0f}Hz — classifico le doppie per registro")
        for name in double_names:
            d = descriptors[name]
            audio = working_tracks[name]
            double_fundamental = estimate_fundamental(audio, sr)
            hf_ratio = high_frequency_ratio(audio, sr)
            register = classify_register(double_fundamental, lead_fundamental, hf_ratio=hf_ratio)
            on_step(f"  '{name}': fondamentale {double_fundamental:.0f}Hz, energia alte {hf_ratio * 100:.0f}% -> registro '{register}'")
            on_event({"type": "register_classified", "stem": name, "fundamental_hz": round(double_fundamental, 1), "hf_ratio": round(hf_ratio, 3), "register": register})

            out = _process_double_stem(name, audio, sr, register, on_step, on_event)

            recipe = RECIPES[register]
            hard_pan = recipe.pan_magnitude if d.pan >= 0 else -recipe.pan_magnitude
            out = pan_stereo(out, hard_pan)

            if recipe.reverb_send > 0.0:
                out = _reverb_send(out, sr, recipe.reverb_send)
                on_step(f"  '{name}': inviata al riverbero lungo ({recipe.reverb_send * 100:.0f}%) per un effetto diffuso")
                on_event({"type": "reverb_send", "stem": name, "mix": recipe.reverb_send})

            register_buses.setdefault(register, np.zeros((n, 2), dtype=np.float32))
            register_buses[register] += out

    backing_vocals_bus = None
    if register_buses:
        backing_vocals_bus = np.zeros((n, 2), dtype=np.float32)
        for sub in register_buses.values():
            backing_vocals_bus += sub
        backing_vocals_bus = Pedalboard(
            [Compressor(threshold_db=-18.0, ratio=BACKING_VOCALS_GLUE_RATIO, attack_ms=10.0, release_ms=150.0)]
        )(backing_vocals_bus.T, sr).T
        on_step(f"Bus voci di supporto: {len(register_buses)} sub-bus per registro ({', '.join(register_buses.keys())}), colla finale {BACKING_VOCALS_GLUE_RATIO:.1f}:1")
        on_event({"type": "backing_vocals_bus", "registers": list(register_buses.keys())})

    # --- Preventive masking: cut instrumental stems that structurally pile
    # up energy in the vocal's presence band (2-5kHz), sized by how much
    # real overlap there is — a static, measured carve, complementing the
    # dynamic (vocal-triggered) ducking below rather than replacing it.
    if lead_names:
        vocal_reference = sum(processed[n] for n in lead_names)
        for name, role in roles.items():
            if role != "other":
                continue
            cut = find_masking_cut(processed[name], vocal_reference, sr)
            if cut is not None:
                on_step(f"  '{name}': mascheramento con la voce a {cut.freq:.0f}Hz, taglio preventivo {cut.gain_db:.1f}dB")
                on_event({"type": "masking_cut", "stem": name, "freq_hz": cut.freq, "gain_db": round(cut.gain_db, 1)})
                processed[name] = apply_eq_cut(processed[name], sr, cut.freq, cut.gain_db, cut.q)

    # --- Kick/bass sidechain: pure, fast duck of the bass every time the
    # drums hit, independent of the vocal ducking — the classic low-end
    # "pumping" trick that keeps kick and bass from smearing on transients.
    drum_names = [n for n, r in roles.items() if r == "drums"]
    bass_names = [n for n, r in roles.items() if r == "bass"]
    if drum_names and bass_names:
        drum_key = sum(processed[n] for n in drum_names)
        duck_db = KICK_BASS_DUCK_BASE_DB + prefs.aggressiveness * 0.6
        on_step(f"Sidechain kick/basso: il basso si abbassa di {duck_db:.1f}dB ad ogni colpo di batteria")
        on_event({"type": "kick_bass_sidechain", "amount_db": round(duck_db, 1)})
        kb_curve = duck_gain_curve(
            drum_key, sr, amount_db=duck_db,
            attack_ms=KICK_BASS_DUCK_ATTACK_MS, release_ms=KICK_BASS_DUCK_RELEASE_MS,
        )
        for name in bass_names:
            processed[name] = apply_gain_curve(processed[name], kb_curve)

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

    # --- Music bus Mid/Side: group harmonic instruments together and dip the
    # mono center where the vocal needs to sit, widen the sides a touch so
    # the instrumental still reads as large despite the dip.
    other_names = [n for n, r in roles.items() if r == "other"]
    music_bus = None
    if other_names:
        music_bus = np.zeros((n, 2), dtype=np.float32)
        for name in other_names:
            music_bus += processed[name]
        mid = (music_bus[:, 0] + music_bus[:, 1]) * 0.5
        side = (music_bus[:, 0] - music_bus[:, 1]) * 0.5
        mid = Pedalboard([PeakFilter(cutoff_frequency_hz=LEAD_PRESENCE_FREQ_HZ, gain_db=MUSIC_BUS_MID_DIP_DB, q=1.0)])(mid.reshape(1, -1), sr).reshape(-1)
        side = Pedalboard([HighShelfFilter(cutoff_frequency_hz=MUSIC_BUS_SIDE_WIDTH_HZ, gain_db=MUSIC_BUS_SIDE_WIDTH_DB, q=0.7)])(side.reshape(1, -1), sr).reshape(-1)
        music_bus = np.stack([mid + side, mid - side], axis=1).astype(np.float32)
        on_step(f"Bus musicale Mid/Side: buco vocale {MUSIC_BUS_MID_DIP_DB:+.1f}dB a {LEAD_PRESENCE_FREQ_HZ:.0f}Hz, lati {MUSIC_BUS_SIDE_WIDTH_DB:+.1f}dB sopra {MUSIC_BUS_SIDE_WIDTH_HZ / 1000:.0f}kHz")
        on_event({"type": "music_bus_ms", "mid_dip_db": MUSIC_BUS_MID_DIP_DB, "side_width_db": MUSIC_BUS_SIDE_WIDTH_DB})

    # Gain-stage vocal prominence: +/- up to 5dB relative to everything else
    # (applies to the lead and the whole backing vocals bus alike, preserving
    # their relative internal balance)
    vocal_gain_db = prefs.vocal_prominence * 5.0
    if lead_names or backing_vocals_bus is not None:
        on_step(f"Regolazione presenza voce: {vocal_gain_db:+.1f}dB")
    for name in lead_names:
        processed[name] = processed[name] * db_to_gain(vocal_gain_db)
    if backing_vocals_bus is not None:
        backing_vocals_bus = backing_vocals_bus * db_to_gain(vocal_gain_db)

    # --- Parallel (New York) compression bus for drums + lead vocal: adds
    # weight/punch by blending in a hard-compressed copy, rather than
    # crushing the clean signal's own transients.
    parallel_source_names = [n for n in lead_names if n in processed] + [
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
    for name, audio in processed.items():
        if name in other_names:
            continue  # folded into the Mid/Side-processed music_bus instead
        mix_bus += audio
    if music_bus is not None:
        mix_bus += music_bus
    if backing_vocals_bus is not None:
        mix_bus += backing_vocals_bus
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
