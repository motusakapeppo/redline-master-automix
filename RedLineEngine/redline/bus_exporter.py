"""Exposes the intermediate buses render_mix() already computes internally
(vocal_main, vocal_doubles, music, parallel, reverb) alongside the finished
stereo mix, via render_mix()'s on_bus_ready callback."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .input_loader import Stems
from .analyze import AnalysisResult
from .wizard import MixPreferences
from .mixengine import render_mix, StepCallback, EventCallback, _noop, _noop_event


@dataclass
class BusExports:
    vocal_main: np.ndarray | None
    vocal_doubles: np.ndarray | None
    music: np.ndarray | None
    parallel: np.ndarray | None
    reverb: np.ndarray | None
    full_mix: np.ndarray


def export_buses(
    stems: Stems,
    analysis: AnalysisResult,
    prefs: MixPreferences,
    on_step: StepCallback = _noop,
    on_event: EventCallback = _noop_event,
) -> BusExports:
    captured: dict[str, np.ndarray] = {}

    def _capture(name: str, audio: np.ndarray) -> None:
        captured[name] = audio

    full_mix = render_mix(stems, analysis, prefs, on_step=on_step, on_event=on_event, on_bus_ready=_capture)

    return BusExports(
        vocal_main=captured.get("vocal_main"),
        vocal_doubles=captured.get("vocal_doubles"),
        music=captured.get("music"),
        parallel=captured.get("parallel"),
        reverb=captured.get("reverb"),
        full_mix=full_mix,
    )
