"""Z-axis depth staging for instrumental ("other") stems: front-of-mix
elements (kick, lead synth, percussive/rhythmic material) stay dry and
full-range; back-of-mix elements (pads, sustained arps, ambient beds) get
high-frequency rolloff + heavier reverb — air absorbs highs over distance,
so cutting them plus drowning the element in reverb reads as physically far
away, purely through EQ/reverb, without touching level (which would eat into
the master's headroom)."""

from __future__ import annotations

import numpy as np
import librosa

from .analysis.loudness import to_mono, crest_factor

FOREGROUND = "foreground"
BACKGROUND = "background"

_CREST_FOREGROUND_MIN = 6.0
_FLUX_FOREGROUND_MIN = 0.15

BACKGROUND_LOWPASS_HZ = 6000.0
BACKGROUND_REVERB_SEND = 0.45


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
    """Rhythmic/percussive/transient-rich material (high crest + high flux)
    reads as foreground; continuous/harmonic material (low crest + low flux,
    e.g. pads, sustained arps) reads as background."""
    if crest > _CREST_FOREGROUND_MIN and flux > _FLUX_FOREGROUND_MIN:
        return FOREGROUND
    return BACKGROUND


def classify_stem_depth(signal: np.ndarray, sr: int) -> str:
    return classify_depth(crest_factor(signal), spectral_flux(signal, sr))
