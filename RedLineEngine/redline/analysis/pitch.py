"""Fundamental-frequency estimation for vocals.

Uses pYIN (probabilistic YIN) instead of plain YIN: plain YIN is notorious
for "octave errors" — it confuses the true fundamental with its first
harmonic (2x) or sub-harmonic (0.5x), which on the real test project made a
clearly-low take read as f0=500Hz and get mis-routed to the falsetto bus.
pYIN runs the candidate pitches through an HMM that models voicing and
octave-transition probabilities, so it doesn't jump octaves frame to frame.

A spectral cross-check (high_frequency_ratio) is exposed so the register
classifier can catch any octave error that still slips through: a genuine
falsetto has a lot of energy up high, so a "high f0" with little HF energy
is almost certainly a sub-harmonic mis-read and can be down-ranked.
"""

from __future__ import annotations

import numpy as np
import librosa
from scipy.signal import butter, sosfiltfilt

from .loudness import to_mono

_PITCH_SR = 22050  # vocal fundamentals sit well under this; keeps pYIN fast
_MAX_ANALYSIS_SECONDS = 25.0  # a stable median f0 doesn't need the whole song


def _prep_mono(signal: np.ndarray, sr: int) -> tuple[np.ndarray, int]:
    mono = to_mono(signal).astype(np.float32)
    if sr > _PITCH_SR:
        mono = librosa.resample(mono, orig_sr=sr, target_sr=_PITCH_SR)
        sr = _PITCH_SR
    # Analyze the loudest contiguous window (skips leading/trailing silence
    # that would otherwise dilute the median with unvoiced frames).
    max_samples = int(_MAX_ANALYSIS_SECONDS * sr)
    if mono.size > max_samples:
        block = max(1, sr // 2)
        n_blocks = mono.size // block
        energy = np.array([np.sum(mono[i * block:(i + 1) * block] ** 2) for i in range(n_blocks)])
        window_blocks = max(1, max_samples // block)
        if n_blocks > window_blocks:
            csum = np.cumsum(energy)
            windowed = csum[window_blocks:] - csum[:-window_blocks]
            start_block = int(np.argmax(windowed))
            start = start_block * block
            mono = mono[start:start + max_samples]
    return mono, sr


def estimate_fundamental(signal: np.ndarray, sr: int, fmin: float = 55.0, fmax: float = 900.0) -> float:
    """Median voiced f0 in Hz via pYIN, or a sane default (110Hz) if nothing
    voiced is detected (silence, pure noise/percussive content)."""
    mono, work_sr = _prep_mono(signal, sr)
    if mono.size < work_sr // 4:
        return 110.0
    try:
        f0, voiced_flag, _voiced_prob = librosa.pyin(
            mono, fmin=fmin, fmax=fmax, sr=work_sr,
            frame_length=2048, fill_na=np.nan,
        )
    except Exception:
        # Fall back to plain YIN if pYIN fails for any reason (very short
        # signals, etc.) — better a possibly-octave-off number than a crash.
        try:
            f0 = librosa.yin(mono, fmin=fmin, fmax=fmax, sr=work_sr)
            voiced_flag = np.isfinite(f0) & (f0 > 0)
        except Exception:
            return 110.0

    voiced = f0[np.isfinite(f0) & (voiced_flag if voiced_flag is not None else np.isfinite(f0))]
    voiced = voiced[voiced > 0]
    if voiced.size == 0:
        return 110.0
    return float(np.median(voiced))


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
