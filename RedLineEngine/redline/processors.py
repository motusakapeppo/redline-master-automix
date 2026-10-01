"""Optional built-in "character" processor variants (Wave 2 / Track F).

A tiny registry wrapping the pedalboard classes the engine does NOT already
use in its normal signal path (Distortion, Chorus, Phaser, Bitcrush,
Clipping, NoiseGate, LadderFilter, PitchShift). These are *optional* colour
tools a caller can insert per-stem when the
``ENABLE_BUILTIN_PROCESSOR_VARIANTS`` feature flag is on.

Design contract:
  - Pure factories: ``build_processor(name, params)`` returns a fresh
    pedalboard effect object (or ``None``). It never touches audio itself.
  - Fail-safe: an unknown name, a bad param, or any construction error
    returns ``None`` so the caller simply skips the processor instead of
    aborting a render.
  - Neutral defaults: every factory has a sane default so enabling the flag
    with no params is safe (though the flag being OFF means nothing is ever
    built in the first place).
  - Zero render impact unless a caller explicitly builds a processor and
    inserts it into a chain. Importing this module has no side effects.

This module is intentionally independent of ``redline.config`` -- the flag
gate lives at the call site (mixengine), not here, so the registry stays a
pure, easily-testable factory table.
"""

from __future__ import annotations

import copy
from typing import Callable

# Each entry maps a stable public name to a factory taking a params dict and
# returning a pedalboard effect. Factories are deliberately tiny and read
# only the keys they understand, falling back to neutral defaults.
_FACTORIES: dict[str, Callable[[dict], object]] = {}


def _register(name: str):
    def _decorator(fn: Callable[[dict], object]) -> Callable[[dict], object]:
        _FACTORIES[name] = fn
        return fn

    return _decorator


@_register("distortion")
def _distortion(params: dict):
    from pedalboard import Distortion

    return Distortion(drive_db=float(params.get("drive_db", 6.0)))


@_register("chorus")
def _chorus(params: dict):
    from pedalboard import Chorus

    return Chorus(
        rate_hz=float(params.get("rate_hz", 1.0)),
        depth=float(params.get("depth", 0.25)),
        centre_delay_ms=float(params.get("centre_delay_ms", 7.0)),
        feedback=float(params.get("feedback", 0.0)),
        mix=float(params.get("mix", 0.5)),
    )


@_register("phaser")
def _phaser(params: dict):
    from pedalboard import Phaser

    return Phaser(
        rate_hz=float(params.get("rate_hz", 1.0)),
        depth=float(params.get("depth", 0.5)),
        centre_frequency_hz=float(params.get("centre_frequency_hz", 1300.0)),
        feedback=float(params.get("feedback", 0.0)),
        mix=float(params.get("mix", 0.5)),
    )


@_register("bitcrush")
def _bitcrush(params: dict):
    from pedalboard import Bitcrush

    return Bitcrush(bit_depth=float(params.get("bit_depth", 8.0)))


@_register("clipping")
def _clipping(params: dict):
    from pedalboard import Clipping

    return Clipping(threshold_db=float(params.get("threshold_db", -6.0)))


@_register("noise_gate")
def _noise_gate(params: dict):
    from pedalboard import NoiseGate

    return NoiseGate(
        threshold_db=float(params.get("threshold_db", -100.0)),
        ratio=float(params.get("ratio", 10.0)),
        attack_ms=float(params.get("attack_ms", 1.0)),
        release_ms=float(params.get("release_ms", 100.0)),
    )


@_register("ladder_filter")
def _ladder_filter(params: dict):
    from pedalboard import LadderFilter

    return LadderFilter(
        mode=params.get("mode", LadderFilter.Mode.LPF12),
        cutoff_hz=float(params.get("cutoff_hz", 200.0)),
        resonance=float(params.get("resonance", 0.0)),
        drive=float(params.get("drive", 1.0)),
    )


@_register("pitch_shift")
def _pitch_shift(params: dict):
    from pedalboard import PitchShift

    return PitchShift(semitones=float(params.get("semitones", 0.0)))


def available_processors() -> tuple[str, ...]:
    """Names of every registered built-in character processor, sorted for a
    stable, deterministic order (a GUI listing them shouldn't reshuffle)."""
    return tuple(sorted(_FACTORIES))


def build_processor(name: str, params: dict | None = None):
    """Build a fresh pedalboard effect for ``name``.

    Returns the effect object on success, or ``None`` on ANY failure
    (unknown name, bad params, construction error) -- the caller is expected
    to skip a ``None`` result rather than treat it as fatal. Never raises.
    """
    factory = _FACTORIES.get(name)
    if factory is None:
        return None
    try:
        return factory(params or {})
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Human-facing metadata (additive introspection surface for the GUI)
# ---------------------------------------------------------------------------
#
# Purely descriptive: this table is never read by the render path, so it can
# never affect output. Defaults mirror the factories above exactly; min/max/
# step are sensible UI ranges (not hard DSP limits) so a slider can present a
# usable span. Only numeric params are listed -- ``ladder_filter``'s ``mode``
# is an enum with no meaningful min/max/step, so it is intentionally omitted.
PROCESSOR_META: dict[str, dict] = {
    "distortion": {
        "name": "distortion",
        "label": "Distorsione",
        "params": [
            {"name": "drive_db", "label": "Drive", "default": 6.0, "min": 0.0, "max": 24.0, "step": 0.5, "unit": "dB"},
        ],
    },
    "chorus": {
        "name": "chorus",
        "label": "Chorus",
        "params": [
            {"name": "rate_hz", "label": "Velocità", "default": 1.0, "min": 0.0, "max": 10.0, "step": 0.1, "unit": "Hz"},
            {"name": "depth", "label": "Profondità", "default": 0.25, "min": 0.0, "max": 1.0, "step": 0.01, "unit": ""},
            {"name": "centre_delay_ms", "label": "Ritardo centrale", "default": 7.0, "min": 0.0, "max": 50.0, "step": 0.5, "unit": "ms"},
            {"name": "feedback", "label": "Feedback", "default": 0.0, "min": -0.95, "max": 0.95, "step": 0.05, "unit": ""},
            {"name": "mix", "label": "Mix", "default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01, "unit": ""},
        ],
    },
    "phaser": {
        "name": "phaser",
        "label": "Phaser",
        "params": [
            {"name": "rate_hz", "label": "Velocità", "default": 1.0, "min": 0.0, "max": 10.0, "step": 0.1, "unit": "Hz"},
            {"name": "depth", "label": "Profondità", "default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01, "unit": ""},
            {"name": "centre_frequency_hz", "label": "Frequenza centrale", "default": 1300.0, "min": 20.0, "max": 20000.0, "step": 10.0, "unit": "Hz"},
            {"name": "feedback", "label": "Feedback", "default": 0.0, "min": -0.95, "max": 0.95, "step": 0.05, "unit": ""},
            {"name": "mix", "label": "Mix", "default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01, "unit": ""},
        ],
    },
    "bitcrush": {
        "name": "bitcrush",
        "label": "Bitcrush",
        "params": [
            {"name": "bit_depth", "label": "Profondità di bit", "default": 8.0, "min": 1.0, "max": 16.0, "step": 1.0, "unit": "bit"},
        ],
    },
    "clipping": {
        "name": "clipping",
        "label": "Clipping",
        "params": [
            {"name": "threshold_db", "label": "Soglia", "default": -6.0, "min": -60.0, "max": 0.0, "step": 0.5, "unit": "dB"},
        ],
    },
    "noise_gate": {
        "name": "noise_gate",
        "label": "Noise Gate",
        "params": [
            {"name": "threshold_db", "label": "Soglia", "default": -100.0, "min": -100.0, "max": 0.0, "step": 1.0, "unit": "dB"},
            {"name": "ratio", "label": "Rapporto", "default": 10.0, "min": 1.0, "max": 100.0, "step": 0.5, "unit": ""},
            {"name": "attack_ms", "label": "Attacco", "default": 1.0, "min": 0.1, "max": 100.0, "step": 0.1, "unit": "ms"},
            {"name": "release_ms", "label": "Rilascio", "default": 100.0, "min": 1.0, "max": 1000.0, "step": 1.0, "unit": "ms"},
        ],
    },
    "ladder_filter": {
        "name": "ladder_filter",
        "label": "Filtro Ladder",
        "params": [
            {"name": "cutoff_hz", "label": "Cutoff", "default": 200.0, "min": 20.0, "max": 20000.0, "step": 10.0, "unit": "Hz"},
            {"name": "resonance", "label": "Risonanza", "default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01, "unit": ""},
            {"name": "drive", "label": "Drive", "default": 1.0, "min": 0.0, "max": 10.0, "step": 0.1, "unit": ""},
        ],
    },
    "pitch_shift": {
        "name": "pitch_shift",
        "label": "Pitch Shift",
        "params": [
            {"name": "semitones", "label": "Semitoni", "default": 0.0, "min": -24.0, "max": 24.0, "step": 1.0, "unit": "st"},
        ],
    },
}


def describe_processor(name: str) -> dict | None:
    """Human metadata for a known processor, or ``None`` for an unknown name.

    Returns a *fresh deep copy* every call so a caller (e.g. the GUI bridge)
    can freely mutate the result without corrupting the shared table. Never
    raises -- any unexpected input simply yields ``None``.
    """
    try:
        meta = PROCESSOR_META.get(name)
        if meta is None:
            return None
        return copy.deepcopy(meta)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Curated per-stem presets (data only -- never touches audio)
# ---------------------------------------------------------------------------
#
# The old UX applied ONE processor to every stem, which is musically wrong: a
# kick, a bass, a pad and a lead vocal each need different treatment. This
# table maps a *context* (role, optionally refined by instrument kind or vocal
# register) to a sensible processor + params. It is pure data: importing it
# has no side effects and the render path only reads it when the caller opts
# in (ENABLE_AUTO_PROCESSORS + ENABLE_BUILTIN_PROCESSOR_VARIANTS).
#
# Context key format: ``"<role>"`` or ``"<role>:<instrument_kind|register>"``.
# A missing key means "no processor for this context" -- deliberately the
# default for a lead vocal, which must never get chorus/phaser by default.
#
# Musical rationale (per entry):
#   - drums/percussion -> subtle clipping: transient glue, not a colour effect.
#   - bass/sub -> light distortion: harmonic warmth that reads on small
#     speakers, WITHOUT the pitch-smearing of chorus/phaser on a mono low end.
#   - pads/keys/strings/electric guitar -> chorus: width and movement.
#   - fx/risers -> bitcrush: already-designed ear candy, a touch of grit.
#   - vocal doubles (register context) -> subtle chorus for width; a LEAD
#     vocal (no register) intentionally has no entry -> None.
PROCESSOR_PRESETS: dict[str, dict] = {
    # --- Role-level (most common, no instrument/register refinement) --------
    "drums": {
        "processor": "clipping",
        "params": {"threshold_db": -3.0},
        "reason": "batteria: clipping leggero per incollare i transienti",
    },
    "bass": {
        "processor": "distortion",
        "params": {"drive_db": 3.0},
        "reason": "basso: distorsione leggera per calore e armoniche (niente chorus sul basso)",
    },
    # --- "other" role, refined by instrument kind ---------------------------
    "other:synth_pad": {
        "processor": "chorus",
        "params": {"rate_hz": 0.6, "depth": 0.35, "mix": 0.35},
        "reason": "pad: chorus per ampiezza e movimento",
    },
    "other:keys": {
        "processor": "chorus",
        "params": {"rate_hz": 0.5, "depth": 0.25, "mix": 0.25},
        "reason": "tastiere: chorus leggero per ampiezza",
    },
    "other:strings": {
        "processor": "chorus",
        "params": {"rate_hz": 0.4, "depth": 0.3, "mix": 0.3},
        "reason": "archi: chorus per ampiezza e corpo",
    },
    "other:world_strings": {
        "processor": "chorus",
        "params": {"rate_hz": 0.4, "depth": 0.3, "mix": 0.3},
        "reason": "archi etnici: chorus per ampiezza",
    },
    "other:guitar_electric": {
        "processor": "chorus",
        "params": {"rate_hz": 0.8, "depth": 0.3, "mix": 0.3},
        "reason": "chitarra elettrica: chorus per ampiezza",
    },
    "other:guitar_acoustic": {
        "processor": "chorus",
        "params": {"rate_hz": 0.6, "depth": 0.2, "mix": 0.2},
        "reason": "chitarra acustica: chorus leggero per ampiezza",
    },
    "other:organ": {
        "processor": "chorus",
        "params": {"rate_hz": 0.9, "depth": 0.3, "mix": 0.3},
        "reason": "organo: chorus tipo Leslie per movimento",
    },
    "other:choir": {
        "processor": "chorus",
        "params": {"rate_hz": 0.5, "depth": 0.3, "mix": 0.3},
        "reason": "coro: chorus per ampiezza diffusa",
    },
    "other:percussion": {
        "processor": "clipping",
        "params": {"threshold_db": -4.0},
        "reason": "percussioni: clipping leggero per incollare i transienti",
    },
    "other:fx": {
        "processor": "bitcrush",
        "params": {"bit_depth": 10.0},
        "reason": "fx/riser: bitcrush leggero per carattere",
    },
    # --- Vocal doubles, refined by register (never the lead) ----------------
    "vocal:high": {
        "processor": "chorus",
        "params": {"rate_hz": 0.7, "depth": 0.25, "mix": 0.25},
        "reason": "doppia acuta: chorus leggero per ampiezza",
    },
    "vocal:falsetto": {
        "processor": "chorus",
        "params": {"rate_hz": 0.6, "depth": 0.25, "mix": 0.25},
        "reason": "falsetto: chorus leggero per ampiezza diffusa",
    },
    "vocal:unison": {
        "processor": "chorus",
        "params": {"rate_hz": 0.8, "depth": 0.2, "mix": 0.2},
        "reason": "doppia all'unisono: chorus leggero per ampiezza",
    },
}


def available_presets() -> tuple[str, ...]:
    """Context keys of every curated preset, sorted for a stable, deterministic
    order (a GUI listing them shouldn't reshuffle)."""
    return tuple(sorted(PROCESSOR_PRESETS))


def preset_for(
    role: str,
    instrument_kind: str | None = None,
    register: str | None = None,
) -> dict | None:
    """Resolve the most specific curated preset for a stem context.

    Resolution order (most specific first):
      1. ``"<role>:<register>"`` (vocal doubles)
      2. ``"<role>:<instrument_kind>"`` ("other" instruments)
      3. ``"<role>"`` (drums/bass)
    Returns a *fresh deep copy* of ``{"processor", "params", "reason"}``, or
    ``None`` when no context matches (e.g. a lead vocal, or an unknown role).
    Never raises -- any unexpected input simply yields ``None``.
    """
    try:
        if not role or not isinstance(role, str):
            return None
        role_key = role.strip().lower()
        if not role_key:
            return None
        candidates: list[str] = []
        if register and isinstance(register, str):
            candidates.append(f"{role_key}:{register.strip().lower()}")
        if instrument_kind and isinstance(instrument_kind, str):
            candidates.append(f"{role_key}:{instrument_kind.strip().lower()}")
        candidates.append(role_key)
        for key in candidates:
            preset = PROCESSOR_PRESETS.get(key)
            if preset is not None:
                return copy.deepcopy(preset)
        return None
    except Exception:
        return None
