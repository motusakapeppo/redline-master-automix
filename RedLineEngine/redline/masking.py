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


@dataclass
class MaskingCut:
    freq: float
    gain_db: float
    q: float = 1.0


def _presence_ratio(signal: np.ndarray, sr: int) -> float:
    band, _rest = split_band(signal, sr, *PRESENCE_BAND_HZ)
    band_energy = float(np.sum(band.astype(np.float64) ** 2))
    total_energy = float(np.sum(signal.astype(np.float64) ** 2)) + 1e-12
    return band_energy / total_energy


def find_masking_cut(instrumental_audio: np.ndarray, vocal_audio: np.ndarray, sr: int) -> MaskingCut | None:
    vocal_ratio = _presence_ratio(vocal_audio, sr)
    if vocal_ratio < VOCAL_PRESENCE_MIN:
        return None  # the vocal doesn't really occupy this band in this song

    other_ratio = _presence_ratio(instrumental_audio, sr)
    if other_ratio < OVERLAP_THRESHOLD:
        return None  # not enough real accumulation there to justify a cut

    severity = min(1.0, (other_ratio - OVERLAP_THRESHOLD) / OVERLAP_THRESHOLD)
    cut_db = -2.0 - severity * (MAX_CUT_DB - 2.0)
    return MaskingCut(freq=PRESENCE_CENTER_HZ, gain_db=cut_db, q=1.0)
