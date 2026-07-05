"""Cross-correlation based time/phase alignment. Two uses:
  - Vocal doubles/harmonies recorded slightly off from the lead take create
    smearing/confusion if left as-is — nudge them into time with the lead.
  - Two stems that share low-end content (e.g. a bass stem and a kick/808 in
    a separate drum stem) can partially phase-cancel if their sample-level
    timing doesn't line up — nudge one to match the other before summing.

Both are the same operation: find the sample delay that maximizes
correlation between two signals, restricted to a plausible search window
(doubles/duplicate-mic scenarios are near-simultaneous takes, not full bars
apart), and shift accordingly.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import correlate
import librosa

from .analysis.loudness import to_mono

MAX_SHIFT_MS = 100.0  # doubles/parallel mics are milliseconds apart, not more


def find_sample_delay(signal_a: np.ndarray, signal_b: np.ndarray, sr: int, max_shift_ms: float = MAX_SHIFT_MS) -> int:
    """Returns the delay (in samples, at `sr`) that should be passed to
    `apply_sample_delay(signal_b, delay)` to bring signal_b into alignment
    with signal_a — i.e. if signal_b already lags signal_a, this comes back
    negative (shift b earlier to catch up). Computed on a downsampled mono
    copy for speed, since sample-accurate resolution isn't needed."""
    mono_a = to_mono(signal_a).astype(np.float32)
    mono_b = to_mono(signal_b).astype(np.float32)
    n = min(mono_a.shape[0], mono_b.shape[0])
    if n < sr // 2:
        return 0

    analysis_sr = 8000
    if sr > analysis_sr:
        a_ds = librosa.resample(mono_a[:n], orig_sr=sr, target_sr=analysis_sr)
        b_ds = librosa.resample(mono_b[:n], orig_sr=sr, target_sr=analysis_sr)
    else:
        a_ds, b_ds = mono_a[:n], mono_b[:n]
        analysis_sr = sr

    max_shift_samples = int(max_shift_ms / 1000.0 * analysis_sr)
    if max_shift_samples < 1 or a_ds.size < 2 or b_ds.size < 2:
        return 0

    # Restrict the correlation to the plausible lag window instead of a full
    # (and much slower) cross-correlation over the whole track.
    corr = correlate(a_ds, b_ds, mode="full", method="fft")
    center = len(b_ds) - 1
    lo = max(0, center - max_shift_samples)
    hi = min(len(corr), center + max_shift_samples + 1)
    window = corr[lo:hi]
    if window.size == 0:
        return 0

    best_idx = int(np.argmax(window)) + lo
    lag_ds_samples = best_idx - center  # positive: b should shift forward (delay) to match a

    return int(round(lag_ds_samples * (sr / analysis_sr)))


def apply_sample_delay(signal: np.ndarray, delay_samples: int) -> np.ndarray:
    """Shifts `signal` by delay_samples (positive = push later/pad start with
    silence, negative = trim start) without changing its length."""
    if delay_samples == 0:
        return signal
    n = signal.shape[0]
    out = np.zeros_like(signal)
    if delay_samples > 0:
        d = min(delay_samples, n)
        out[d:] = signal[: n - d]
    else:
        d = min(-delay_samples, n)
        out[: n - d] = signal[d:]
    return out


def align_to_reference(signal: np.ndarray, reference: np.ndarray, sr: int, max_shift_ms: float = MAX_SHIFT_MS) -> tuple[np.ndarray, int]:
    """Convenience wrapper: finds and applies the delay that best aligns
    `signal` to `reference`. Returns (aligned_signal, delay_samples_applied)."""
    delay = find_sample_delay(reference, signal, sr, max_shift_ms)
    return apply_sample_delay(signal, delay), delay
