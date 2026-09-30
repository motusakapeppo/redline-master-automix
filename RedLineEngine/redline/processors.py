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
