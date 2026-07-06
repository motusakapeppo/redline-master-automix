"""Z-axis depth staging for instrumental ("other") stems: front-of-mix
elements (kick, lead synth, percussive/rhythmic material) stay dry and
full-range; back-of-mix elements (pads, sustained arps, ambient beds) get
high-frequency rolloff + heavier reverb — air absorbs highs over distance,
so cutting them plus drowning the element in reverb reads as physically far
away, purely through EQ/reverb, without touching level (which would eat into
the master's headroom). A third, "midground" bucket catches stems with
contrasting crest/flux (e.g. a heavily-filtered continuous synth bass: low
crest but high flux) that don't cleanly fit either extreme."""

from __future__ import annotations

import numpy as np
import librosa

from .analysis.loudness import to_mono, crest_factor

FOREGROUND = "foreground"
MIDGROUND = "midground"
BACKGROUND = "background"

_CREST_HIGH = 6.0
_CREST_LOW = 3.5
_FLUX_HIGH = 0.15
_FLUX_LOW = 0.14

# Foreground treatment: a touch of high-shelf "air" instead of a cut, medium/
# slow compression attack so it doesn't squash the transients that keep it
# sounding close and up-front.
FOREGROUND_AIR_SHELF_HZ = 8000.0
FOREGROUND_AIR_GAIN_DB = 1.0
FOREGROUND_COMP_ATTACK_MS = 25.0
FOREGROUND_COMP_RATIO = 2.0
FOREGROUND_COMP_THRESHOLD_DB = -14.0

# Background treatment: hard low-pass (air absorbs highs over distance) +
# fast-attack heavy compression to flatten it into an undifferentiated bed,
# plus a big reverb send.
BACKGROUND_LOWPASS_HZ = 6000.0
BACKGROUND_REVERB_SEND = 0.45
BACKGROUND_COMP_ATTACK_MS = 2.0
BACKGROUND_COMP_RATIO = 6.0
BACKGROUND_COMP_THRESHOLD_DB = -20.0

# Midground: split the difference — a milder LPF/reverb, no strong dynamic
# treatment, since these stems (e.g. a filtered continuous bass synth)
# already sit ambiguously and don't need to be pushed hard either way.
MIDGROUND_LOWPASS_HZ = 9000.0
MIDGROUND_REVERB_SEND = 0.15


def spectral_flux(signal: np.ndarray, sr: int) -> float:
    """Normalized mean frame-to-frame spectral magnitude change — high for
    percussive/changing material, low for sustained/tonal pads."""
    mono = to_mono(signal).astype(np.float32)
    if mono.size < 2048:
        return 0.0
    stft = np.abs(librosa.stft(mono, n_fft=2048, hop_length=512))
    if stft.shape[1] < 2:
        return 0.0
    diff = np.diff(stft, axis=1)
    flux_per_frame = np.sqrt(np.mean(diff ** 2, axis=0))
    norm = np.mean(stft) + 1e-9
    return float(np.mean(flux_per_frame) / norm)


def classify_depth(crest: float, flux: float) -> str:
    """High crest + high flux (percussive, rhythmically distinct) reads as
    foreground; low crest + low flux (sustained, tonally static — pads,
    drones, long strings) reads as background; anything contrasting or
    in-between (e.g. low crest but high flux, a filtered continuous synth)
    is midground."""
    if crest > _CREST_HIGH and flux > _FLUX_HIGH:
        return FOREGROUND
    if crest < _CREST_LOW and flux < _FLUX_LOW:
        return BACKGROUND
    return MIDGROUND


def classify_stem_depth(signal: np.ndarray, sr: int) -> str:
    return classify_depth(crest_factor(signal), spectral_flux(signal, sr))
