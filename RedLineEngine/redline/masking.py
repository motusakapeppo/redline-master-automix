"""Preventive masking analysis: measures whether an instrumental stem is
piling up energy in the ~2-5kHz "presence" band where the lead vocal needs
to sit, and recommends a static corrective cut sized by how bad the overlap
actually is — a structural carve decided from measurement, not a guess,
complementing the dynamic (vocal-triggered) spectral ducking already applied
on the bus."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .dsp_utils import split_band

PRESENCE_BAND_HZ = (2000.0, 5000.0)
PRESENCE_CENTER_HZ = 3200.0

# An instrumental stem needs to hold a meaningful share of its own energy in
# the presence band before it's worth cutting; below this it's not really
# competing with the vocal there. Was 0.16 -- most real instrumental beds
# that do genuinely mask the vocal only carry 11-15% of their energy there,
# so the original threshold rarely fired on real material.
OVERLAP_THRESHOLD = 0.12
# The vocal itself needs to actually live in the presence band for this to
# matter — if it doesn't, there's nothing to protect. Was 0.08.
VOCAL_PRESENCE_MIN = 0.06

MAX_CUT_DB = 4.5

# Mid-range "mud/honk/hollow" band: where a vocal's body (fundamental + 1st
# harmonic for most singers) lives, and where a crowded instrumental bed
# (rhythm guitars, pads, low piano voicings) tends to pile up in a way that
# reads as murky rather than as a direct presence-band fight. The original
# masking analysis only ever looked at 2-5kHz -- a stem could be completely
# clean there while still burying the vocal's clarity/body in this lower
# band. Thresholds are more permissive than the presence band: some mud is
# normal and expected here, only real accumulation gets cut, and the cut is
# gentler (clutter reduction, not a direct masking fight).
MIDRANGE_BAND_HZ = (300.0, 800.0)
MIDRANGE_CENTER_HZ = 500.0
MIDRANGE_OVERLAP_THRESHOLD = 0.18
MIDRANGE_VOCAL_MIN = 0.08
MIDRANGE_MAX_CUT_DB = 3.5


@dataclass
class MaskingCut:
    freq: float
    gain_db: float
    q: float = 1.0


def _band_ratio(signal: np.ndarray, sr: int, band_hz: tuple[float, float]) -> float:
    band, _rest = split_band(signal, sr, *band_hz)
    band_energy = float(np.sum(band.astype(np.float64) ** 2))
    total_energy = float(np.sum(signal.astype(np.float64) ** 2)) + 1e-12
    return band_energy / total_energy


def find_masking_cut(
    instrumental_audio: np.ndarray, vocal_audio: np.ndarray, sr: int, _ratio_cache: dict | None = None
) -> MaskingCut | None:
    """`_ratio_cache`, when given, memoizes the vocal-side band ratio
    (a pure function of `vocal_audio`/`sr` only) under key "presence" --
    callers that invoke this once per instrumental stem against the same
    `vocal_audio` (mixengine's per-stem masking loop) pass the same dict
    across calls so the vocal side's band-split filtering isn't redone
    identically for every stem. Callers that call this once (or with a
    different vocal_audio each time) simply don't pass a cache and get
    the exact same result as before."""
    if _ratio_cache is not None and "presence" in _ratio_cache:
        vocal_ratio = _ratio_cache["presence"]
    else:
        vocal_ratio = _band_ratio(vocal_audio, sr, PRESENCE_BAND_HZ)
        if _ratio_cache is not None:
            _ratio_cache["presence"] = vocal_ratio
    if vocal_ratio < VOCAL_PRESENCE_MIN:
        return None  # the vocal doesn't really occupy this band in this song

    other_ratio = _band_ratio(instrumental_audio, sr, PRESENCE_BAND_HZ)
    if other_ratio < OVERLAP_THRESHOLD:
        return None  # not enough real accumulation there to justify a cut

    severity = min(1.0, (other_ratio - OVERLAP_THRESHOLD) / OVERLAP_THRESHOLD)
    cut_db = -2.0 - severity * (MAX_CUT_DB - 2.0)
    return MaskingCut(freq=PRESENCE_CENTER_HZ, gain_db=cut_db, q=1.0)


def find_midrange_masking_cut(
    instrumental_audio: np.ndarray, vocal_audio: np.ndarray, sr: int, _ratio_cache: dict | None = None
) -> MaskingCut | None:
    """Same principle as find_masking_cut, but for the 300-800Hz body/mud
    band instead of the 2-5kHz presence band -- catches instrumental
    clutter that muddies vocal clarity without ever showing up as presence-
    band competition. See find_masking_cut for `_ratio_cache` semantics
    (memoized here under key "midrange", independent of the "presence" key)."""
    if _ratio_cache is not None and "midrange" in _ratio_cache:
        vocal_ratio = _ratio_cache["midrange"]
    else:
        vocal_ratio = _band_ratio(vocal_audio, sr, MIDRANGE_BAND_HZ)
        if _ratio_cache is not None:
            _ratio_cache["midrange"] = vocal_ratio
    if vocal_ratio < MIDRANGE_VOCAL_MIN:
        return None

    other_ratio = _band_ratio(instrumental_audio, sr, MIDRANGE_BAND_HZ)
    if other_ratio < MIDRANGE_OVERLAP_THRESHOLD:
        return None

    severity = min(1.0, (other_ratio - MIDRANGE_OVERLAP_THRESHOLD) / MIDRANGE_OVERLAP_THRESHOLD)
    cut_db = -1.5 - severity * (MIDRANGE_MAX_CUT_DB - 1.5)
    return MaskingCut(freq=MIDRANGE_CENTER_HZ, gain_db=cut_db, q=1.2)
