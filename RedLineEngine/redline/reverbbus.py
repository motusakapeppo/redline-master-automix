"""Shared reverb buses (Room / Plate / Hall) instead of one Reverb instance
per stem. Two real problems this fixes: CPU (instantiating and running a
convolution/algorithmic reverb per background/midground stem plus every
falsetto double doesn't scale — 15 stems, 15 reverbs, computation exploding),
and acoustic realism (15 separate reverb instances put 15 instruments in 15
subtly different virtual rooms, which reads as mud; sending them all to the
*same* bus instance means they share the exact same early reflections and
tail — the actual trick that makes a mix sound "glued").

Each bus gets the "Abbey Road" EQ treatment on its return: high-pass around
600Hz and low-pass around 10kHz, so the tail never muddies the kick/bass and
never turns vocals sibilant — a reverb "cushion" that's felt, not noticed.
"""

from __future__ import annotations

import numpy as np
from pedalboard import Pedalboard, Reverb, HighpassFilter, LowpassFilter

ROOM = "room"
PLATE = "plate"
HALL = "hall"

_BUS_REVERB_PARAMS = {
    ROOM: dict(room_size=0.25, damping=0.6, wet_level=1.0, dry_level=0.0, width=0.7),
    PLATE: dict(room_size=0.55, damping=0.3, wet_level=1.0, dry_level=0.0, width=0.9),
    HALL: dict(room_size=0.9, damping=0.25, wet_level=1.0, dry_level=0.0, width=1.0),
}

# Abbey Road trick: keep the tail's low end away from the kick/bass and its
# top end away from vocal sibilance, on every bus's return.
_RETURN_HIGHPASS_HZ = 600.0
_RETURN_LOWPASS_HZ = 10000.0

# Bus-specific extra shaping beyond the shared return EQ.
_BUS_EXTRA_LOWPASS_HZ = {
    HALL: 7000.0,  # dark, distant — this bus is specifically for "far away"
}


class ReverbBusSystem:
    """One instance per render (per `render_mix` call) — holds exactly 3
    Reverb instances no matter how many stems send to them."""

    def __init__(self, sr: int) -> None:
        self.sr = sr
        self._sums: dict[str, np.ndarray | None] = {ROOM: None, PLATE: None, HALL: None}
        self._reverbs = {name: Pedalboard([Reverb(**params)]) for name, params in _BUS_REVERB_PARAMS.items()}

    def send(self, signal: np.ndarray, bus: str, level: float) -> None:
        """Accumulates `signal * level` into the named bus. Does not process
        reverb here — that happens once in `render()`."""
        if level <= 0.0 or bus not in self._sums:
            return
        contribution = (signal * level).astype(np.float32)
        if self._sums[bus] is None:
            self._sums[bus] = contribution.copy()
        else:
            self._sums[bus] += contribution

    def render(self, on_step=None) -> np.ndarray:
        """Processes each bus's accumulated sum through its single Reverb
        instance + Abbey Road return EQ, and sums the three bus outputs —
        this is the only place Reverb.process actually runs, once per bus."""
        n_samples = 0
        for s in self._sums.values():
            if s is not None:
                n_samples = s.shape[0]
                break
        if n_samples == 0:
            return None

        total = np.zeros((n_samples, 2), dtype=np.float32)
        for bus_name, bus_sum in self._sums.items():
            if bus_sum is None:
                continue

            wet = self._reverbs[bus_name](bus_sum.T, self.sr).T

            return_fx = [
                HighpassFilter(cutoff_frequency_hz=_RETURN_HIGHPASS_HZ),
                LowpassFilter(cutoff_frequency_hz=_RETURN_LOWPASS_HZ),
            ]
            if bus_name in _BUS_EXTRA_LOWPASS_HZ:
                return_fx.append(LowpassFilter(cutoff_frequency_hz=_BUS_EXTRA_LOWPASS_HZ[bus_name]))
            wet = Pedalboard(return_fx)(wet.T, self.sr).T

            total += wet
            if on_step is not None:
                on_step(f"Bus riverbero '{bus_name}': renderizzato una sola volta (Abbey Road EQ sul ritorno)")

        return total
