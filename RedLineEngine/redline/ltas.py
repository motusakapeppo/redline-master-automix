"""Long-Term Average Spectrum (LTAS) matching: clones the tonal "color" of
a reference track onto the mix without a heavyweight stem-separation model
(no Demucs here — this only needs the two full mixes' average spectra).

Pipeline: measure both spectra -> take the dB delta -> clamp it to a safe
range -> turn that curve into a linear-phase FIR filter -> apply with
filtfilt so transients keep their original phase (no smearing)."""

from __future__ import annotations

import numpy as np
from scipy.signal import firwin2, filtfilt, welch

MAX_DELTA_DB = 2.5  # safety clamp: never fight the mix's own balance by more than this
FIR_TAPS = 256  # wide enough to shape full-band tonal balance without stressing the CPU


def compute_ltas(signal: np.ndarray, sr: int, nperseg: int = 8192) -> tuple[np.ndarray, np.ndarray]:
    """Average magnitude spectrum in dB via Welch's method (averages many
    overlapping windows, so short-term loud/quiet moments wash out and only
    the track's persistent tonal balance remains)."""
    mono = signal.mean(axis=1) if signal.ndim == 2 else signal
    freqs, psd = welch(mono.astype(np.float64), fs=sr, nperseg=min(nperseg, len(mono)))
    db = 10.0 * np.log10(psd + 1e-15)
    return freqs, db


def compute_delta_curve(
    mix_freqs: np.ndarray,
    mix_db: np.ndarray,
    ref_freqs: np.ndarray,
    ref_db: np.ndarray,
    max_delta_db: float = MAX_DELTA_DB,
) -> np.ndarray:
    """Reference resampled onto the mix's frequency bins, then the dB
    difference clamped to +/-max_delta_db — this is what keeps the matcher
    from ever trying to invent bass or treble the mix doesn't have."""
    ref_db_on_mix_bins = np.interp(mix_freqs, ref_freqs, ref_db)
    delta = ref_db_on_mix_bins - mix_db
    return np.clip(delta, -max_delta_db, max_delta_db)


def design_fir(delta_db: np.ndarray, freqs: np.ndarray, sr: int, numtaps: int = FIR_TAPS) -> np.ndarray:
    """Converts the (clamped) dB delta curve into a linear-phase FIR filter
    via firwin2 — linear phase means filtfilt-free application would still
    smear transients, so we go through filtfilt anyway for true zero-phase."""
    nyquist = sr / 2.0
    freq_norm = np.clip(freqs / nyquist, 0.0, 1.0)
    # firwin2 needs a strictly increasing, deduplicated frequency axis starting at 0 and ending at 1
    freq_norm, unique_idx = np.unique(freq_norm, return_index=True)
    gain_linear = 10.0 ** (delta_db[unique_idx] / 20.0)
    if freq_norm[0] > 0.0:
        freq_norm = np.concatenate([[0.0], freq_norm])
        gain_linear = np.concatenate([[gain_linear[0]], gain_linear])
    if freq_norm[-1] < 1.0:
        freq_norm = np.concatenate([freq_norm, [1.0]])
        gain_linear = np.concatenate([gain_linear, [gain_linear[-1]]])
    # firwin2 requires an odd tap count unless gain is 0 at Nyquist (Type II
    # constraint) -- forcing odd sidesteps that restriction entirely.
    if numtaps % 2 == 0:
        numtaps += 1
    return firwin2(numtaps, freq_norm, gain_linear)


def apply_fir(signal: np.ndarray, fir: np.ndarray) -> np.ndarray:
    """Zero-phase filtering (filtfilt) so transient timing/phase is
    untouched — only the spectral tilt changes, nothing shifts in time."""
    if signal.ndim == 1:
        return filtfilt(fir, [1.0], signal.astype(np.float64)).astype(np.float32)
    out = np.stack(
        [filtfilt(fir, [1.0], signal[:, ch].astype(np.float64)) for ch in range(signal.shape[1])],
        axis=1,
    )
    return out.astype(np.float32)


def match_ltas(
    mix: np.ndarray,
    sr: int,
    reference: np.ndarray,
    ref_sr: int,
    max_delta_db: float = MAX_DELTA_DB,
    numtaps: int = FIR_TAPS,
) -> tuple[np.ndarray, dict]:
    """Full pipeline: mix + reference in, spectrally-matched mix + a report
    dict out (for the QC cycle / event log). `reference` may be a different
    sample rate than `mix` — compute_ltas measures each at its own rate, and
    the delta is interpolated onto the mix's frequency axis regardless."""
    mix_freqs, mix_db = compute_ltas(mix, sr)
    ref_freqs, ref_db = compute_ltas(reference, ref_sr)
    delta_db = compute_delta_curve(mix_freqs, mix_db, ref_freqs, ref_db, max_delta_db)
    fir = design_fir(delta_db, mix_freqs, sr, numtaps)
    matched = apply_fir(mix, fir)

    report = {
        "max_delta_db": max_delta_db,
        "fir_taps": numtaps,
        "applied_delta_db_range": (round(float(delta_db.min()), 2), round(float(delta_db.max()), 2)),
    }
    return matched, report
