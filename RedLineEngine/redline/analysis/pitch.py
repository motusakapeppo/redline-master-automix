"""Fundamental-frequency estimation for vocals.

Uses pYIN (probabilistic YIN) instead of plain YIN: plain YIN is notorious
for "octave errors" — it confuses the true fundamental with its first
harmonic (2x) or sub-harmonic (0.5x), which on the real test project made a
clearly-low take read as f0=500Hz and get mis-routed to the falsetto bus.
pYIN runs the candidate pitches through an HMM that models voicing and
octave-transition probabilities, so it doesn't jump octaves frame to frame.

Two more layers of hardening on top of that, both applied only to the
*analysis* copy — the real audio going through the mix is untouched:

1. Voice-activity isolation ("ghost array"): a take with a couple of
   ad-libs in an otherwise-silent 3-minute file has its pitch estimate
   diluted/dominated by silence and room noise if analyzed whole. This
   extracts just the active segments (librosa.effects.split) and
   concatenates them before estimating pitch — pure signal, no dead air.
2. A strict analysis-only band-pass (80-1000Hz): confines the pitch
   search to where a human voice fundamental actually lives, blind to
   mains hum (~50/60Hz) and to high harmonics that YIN-family algorithms
   can lock onto instead of the true fundamental.

A spectral cross-check (high_frequency_ratio, on the *original* signal —
harmonic content, not the band-limited copy) is exposed so the register
classifier can catch any octave error that still slips through: a genuine
falsetto has a lot of energy up high, so a "high f0" with little HF energy
is almost certainly a sub-harmonic mis-read and can be down-ranked.
"""

from __future__ import annotations

import numpy as np
import librosa
from scipy.signal import butter, sosfiltfilt

from redline import config
from redline.logging_setup import get_logger
from .loudness import to_mono

logger = get_logger(__name__)

_PITCH_SR = 22050  # vocal fundamentals sit well under this; keeps pYIN fast
_MAX_ANALYSIS_SECONDS = 25.0  # a stable median f0 doesn't need the whole song
_VAD_TOP_DB = 40.0  # librosa.effects.split threshold below peak
_PITCH_BAND_HZ = (80.0, 1000.0)  # analysis-only band-pass: human voice fundamental range

# Fast path (ENABLE_FAST_ANALYSIS): plain YIN instead of pYIN, on a shorter
# slice. YIN is ~50-80x cheaper but is the octave-error-prone estimator pYIN
# was chosen to replace — so it's only used when the spectral cross-check says
# the take is *not* bright (a genuine falsetto/high take is exactly where YIN
# mis-reads), and the robust pYIN path is kept as the fallback.
_FAST_MAX_ANALYSIS_SECONDS = 12.0  # a median f0 stabilizes well before this
_FAST_HF_RATIO_MAX = 0.35  # above this the take is bright -> keep pYIN


def _isolate_voiced_segments(mono: np.ndarray, sr: int, top_db: float = _VAD_TOP_DB) -> np.ndarray:
    """Concatenates only the energetically-active regions (VAD via
    librosa.effects.split), so a take that's mostly silence/room noise
    between a couple of ad-libs doesn't get its pitch/energy estimate
    diluted by averaging in all that dead air."""
    if mono.size < sr // 4:
        return mono
    try:
        intervals = librosa.effects.split(mono, top_db=top_db)
    except Exception:
        logger.warning("VAD split failed — using full signal", exc_info=True)
        return mono
    if intervals.size == 0:
        return mono
    segments = [mono[start:end] for start, end in intervals]
    concatenated = np.concatenate(segments)
    return concatenated if concatenated.size > 0 else mono


def _band_limit(mono: np.ndarray, sr: int, band_hz: tuple[float, float]) -> np.ndarray:
    """Analysis-only band-pass so the pitch search can't lock onto mains hum
    or high harmonics outside the human voice fundamental range."""
    nyquist = sr / 2.0
    low_n = max(band_hz[0] / nyquist, 1e-5)
    high_n = min(band_hz[1] / nyquist, 0.999)
    if low_n >= high_n:
        return mono
    sos = butter(4, [low_n, high_n], btype="bandpass", output="sos")
    return sosfiltfilt(sos, mono.astype(np.float64)).astype(np.float32)


def _prep_mono(signal: np.ndarray, sr: int, max_seconds: float = _MAX_ANALYSIS_SECONDS) -> tuple[np.ndarray, int]:
    mono = to_mono(signal).astype(np.float32)
    if sr > _PITCH_SR:
        mono = librosa.resample(mono, orig_sr=sr, target_sr=_PITCH_SR)
        sr = _PITCH_SR

    mono = _isolate_voiced_segments(mono, sr)

    # A stable median f0 doesn't need more than ~25s of concentrated,
    # already-silence-free signal — cap it for speed on long takes.
    max_samples = int(max_seconds * sr)
    if mono.size > max_samples:
        mono = mono[:max_samples]

    mono = _band_limit(mono, sr, _PITCH_BAND_HZ)
    return mono, sr


def _median_voiced(f0: np.ndarray, voiced_flag: np.ndarray | None) -> float:
    voiced = f0[np.isfinite(f0) & (voiced_flag if voiced_flag is not None else np.isfinite(f0))]
    voiced = voiced[voiced > 0]
    if voiced.size == 0:
        return 110.0
    return float(np.median(voiced))


def _estimate_fundamental_pyin(mono: np.ndarray, work_sr: int, fmin: float, fmax: float) -> float:
    try:
        f0, voiced_flag, _voiced_prob = librosa.pyin(
            mono, fmin=fmin, fmax=fmax, sr=work_sr,
            frame_length=2048, fill_na=np.nan,
        )
    except Exception:
        # Fall back to plain YIN if pYIN fails for any reason (very short
        # signals, etc.) — better a possibly-octave-off number than a crash.
        logger.warning("pYIN estimation failed — falling back to plain YIN", exc_info=True)
        try:
            f0 = librosa.yin(mono, fmin=fmin, fmax=fmax, sr=work_sr)
            voiced_flag = np.isfinite(f0) & (f0 > 0)
        except Exception:
            logger.warning("Plain YIN also failed — returning default 110 Hz", exc_info=True)
            return 110.0
    return _median_voiced(f0, voiced_flag)


def _estimate_fundamental_fast(mono: np.ndarray, work_sr: int, fmin: float, fmax: float) -> float:
    """Plain YIN on the already-prepared (band-limited, VAD-isolated, capped)
    mono. Only reached when the spectral cross-check says the take isn't bright
    enough for YIN's octave errors to matter."""
    try:
        f0 = librosa.yin(mono, fmin=fmin, fmax=fmax, sr=work_sr, frame_length=2048)
    except Exception:
        logger.warning("Fast YIN failed — falling back to pYIN", exc_info=True)
        return _estimate_fundamental_pyin(mono, work_sr, fmin, fmax)
    return _median_voiced(f0, None)


def estimate_fundamental(signal: np.ndarray, sr: int, fmin: float = 55.0, fmax: float = 900.0) -> float:
    """Median voiced f0 in Hz via pYIN, or a sane default (110Hz) if nothing
    voiced is detected (silence, pure noise/percussive content).

    With ENABLE_FAST_ANALYSIS on, a cheaper plain-YIN path is used when the
    spectral cross-check (high_frequency_ratio on the *original* signal) says
    the take is not bright — i.e. not the falsetto/high case where YIN's
    octave errors would bite. Bright takes keep the robust pYIN path."""
    fast = config.is_enabled("ENABLE_FAST_ANALYSIS")
    if fast:
        # Decide on the original signal's harmonic content, before band-limiting.
        bright = high_frequency_ratio(signal, sr) > _FAST_HF_RATIO_MAX
        max_seconds = _MAX_ANALYSIS_SECONDS if bright else _FAST_MAX_ANALYSIS_SECONDS
    else:
        bright = False
        max_seconds = _MAX_ANALYSIS_SECONDS

    mono, work_sr = _prep_mono(signal, sr, max_seconds=max_seconds)
    if mono.size < work_sr // 4:
        return 110.0

    if fast and not bright:
        return _estimate_fundamental_fast(mono, work_sr, fmin, fmax)
    return _estimate_fundamental_pyin(mono, work_sr, fmin, fmax)


def high_frequency_ratio(signal: np.ndarray, sr: int, cutoff_hz: float = 3500.0) -> float:
    """Fraction of total energy above `cutoff_hz`. A real falsetto/high take
    concentrates a lot of energy up here; a low take barely any — so this is
    the sanity check against pitch octave errors."""
    mono = to_mono(signal).astype(np.float64)
    if mono.size < 256:
        return 0.0
    nyquist = sr / 2.0
    hp_n = min(cutoff_hz / nyquist, 0.999)
    if hp_n <= 0.0:
        return 0.0
    sos = butter(4, hp_n, btype="highpass", output="sos")
    high = sosfiltfilt(sos, mono)
    total_energy = float(np.sum(mono ** 2)) + 1e-12
    high_energy = float(np.sum(high ** 2))
    return float(np.clip(high_energy / total_energy, 0.0, 1.0))
