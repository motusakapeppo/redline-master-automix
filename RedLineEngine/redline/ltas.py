"""Long-Term Average Spectrum (LTAS) matching: clones the tonal "color" of
a reference track onto the mix without a heavyweight stem-separation model
(no Demucs here — this only needs the two full mixes' average spectra).

Pipeline: measure both spectra -> take the dB delta -> clamp it to a safe
range -> turn that curve into a linear-phase FIR filter -> apply with
filtfilt so transients keep their original phase (no smearing)."""

from __future__ import annotations

import numpy as np
from scipy.signal import firwin2, filtfilt, fftconvolve, welch

from redline import config

MAX_DELTA_DB = 2.5  # safety clamp: never fight the mix's own balance by more than this
FIR_TAPS = 256  # wide enough to shape full-band tonal balance without stressing the CPU

# --- Matchering-style v2 (ENABLE_LTAS_V2) -----------------------------------
PIECE_SECONDS = 15.0  # target length of the loudest-pieces analysis chunks
LOWESS_FRAC = 0.0375  # fraction of log-frequency bins in each local regression
RMS_RECORRECTIONS = 3  # iterative gain re-corrects after the EQ (loudness guard)


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
    the delta is interpolated onto the mix's frequency axis regardless.

    With ENABLE_LTAS_V2 off (default) this is the legacy single-FIR path.
    With the flag on, a Matchering-style pipeline runs instead: the target
    spectrum is measured on the loudest pieces only, mid and side are matched
    with separate FIRs whose delta curves are smoothed in log-frequency, and
    the overall RMS is re-corrected after the EQ."""
    if config.is_enabled("ENABLE_LTAS_V2"):
        return _match_ltas_v2(mix, sr, reference, ref_sr, max_delta_db, numtaps)

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


# ---------------------------------------------------------------------------
# Matchering-style v2 pipeline
# ---------------------------------------------------------------------------

def _select_loudest_pieces(signal: np.ndarray, sr: int, piece_seconds: float = PIECE_SECONDS) -> list[np.ndarray]:
    """Split the signal into ~piece_seconds chunks and keep only those whose
    RMS is at or above the average piece RMS — quiet intros/outros must not
    skew the tonal fingerprint of the track."""
    n = signal.shape[0]
    piece_len = max(1, int(sr * piece_seconds))
    pieces = [signal[start:start + piece_len] for start in range(0, n, piece_len)]
    if len(pieces) <= 1:
        return pieces
    rms = np.array([float(np.sqrt(np.mean(p.astype(np.float64) ** 2))) for p in pieces])
    return [p for p, r in zip(pieces, rms) if r >= rms.mean()]


def _average_spectrum_db(pieces: list[np.ndarray], sr: int, nperseg: int = 8192) -> tuple[np.ndarray, np.ndarray]:
    """Welch PSD averaged over the given (loudest) 1-D pieces, in dB."""
    freqs = None
    psd_acc = None
    count = 0
    for piece in pieces:
        mono = piece.astype(np.float64)
        f, psd = welch(mono, fs=sr, nperseg=min(nperseg, mono.shape[0]))
        if freqs is None:
            freqs, psd_acc = f, psd.copy()
        else:
            psd_acc += psd
        count += 1
    return freqs, 10.0 * np.log10(psd_acc / count + 1e-15)


def _lowess_smooth_logfreq(freqs: np.ndarray, delta_db: np.ndarray, frac: float = LOWESS_FRAC) -> np.ndarray:
    """LOWESS-style local linear regression over log-frequency: a moving
    weighted least-squares fit that rounds off narrow spikes in the delta
    curve, which is what keeps the FIR from ringing on transients."""
    log_f = np.log(freqs + 1.0)
    order = np.argsort(log_f)
    log_f = log_f[order]
    y = delta_db[order].astype(np.float64)
    n = len(y)
    window = max(3, int(round(frac * n)))
    if window >= n:
        return delta_db.copy()
    half = window // 2
    smoothed = np.empty(n)
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        xs = log_f[lo:hi]
        ys = y[lo:hi]
        # tricube weights on the normalized distance from the current bin
        d = np.abs(xs - log_f[i]) / max(xs[-1] - xs[0], 1e-9)
        w = (1.0 - d ** 3) ** 3
        sw = w.sum()
        if sw <= 0.0:
            smoothed[i] = y[i]
            continue
        # weighted linear fit (slope via the closed-form weighted covariance)
        xbar = np.average(xs, weights=w)
        ybar = np.average(ys, weights=w)
        sxx = np.sum(w * (xs - xbar) ** 2)
        if sxx <= 0.0:
            smoothed[i] = ybar
        else:
            sxy = np.sum(w * (xs - xbar) * (ys - ybar))
            smoothed[i] = ybar + (sxy / sxx) * (log_f[i] - xbar)
    # restore the original bin order
    out = np.empty(n)
    out[order] = smoothed
    return out


def _lr_to_ms(stereo: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mid = stereo[:, 0] + stereo[:, 1]
    side = stereo[:, 0] - stereo[:, 1]
    return mid, side


def _ms_to_lr(mid: np.ndarray, side: np.ndarray) -> np.ndarray:
    left = (mid + side) / 2.0
    right = (mid - side) / 2.0
    return np.stack([left, right], axis=1)


def _match_ltas_v2(
    mix: np.ndarray,
    sr: int,
    reference: np.ndarray,
    ref_sr: int,
    max_delta_db: float,
    numtaps: int,
) -> tuple[np.ndarray, dict]:
    """Matchering-style pipeline: loudest-pieces target spectrum, separate
    mid/side FIRs with LOWESS-smoothed delta curves, fftconvolve application,
    iterative RMS re-correction. Fail-safe: any unusable reference returns
    the input untouched."""
    ref = np.asarray(reference)
    if ref.size == 0 or not np.isfinite(ref).all():
        return mix, {}

    mix_arr = np.asarray(mix)
    if mix_arr.ndim == 1:
        mix_arr = mix_arr[:, np.newaxis]
    ref = ref if ref.ndim == 2 else ref[:, np.newaxis]

    # 1) target spectrum from the loudest pieces only
    pieces = _select_loudest_pieces(mix_arr, sr)

    # 2) per-component (mid/side) delta curves, clamped + log-smoothed
    channels = mix_arr.shape[1]
    ref_channels = ref.shape[1]
    firs = []
    delta_ranges = []
    for ch in range(channels):
        if channels == 2:
            # M/S decomposition: mid = L+R, side = L-R
            comp = mix_arr[:, 0] + mix_arr[:, 1] if ch == 0 else mix_arr[:, 0] - mix_arr[:, 1]
        else:
            comp = mix_arr[:, ch]
        if ref_channels == 2:
            ref_comp = ref[:, 0] + ref[:, 1] if ch == 0 else ref[:, 0] - ref[:, 1]
        else:
            ref_comp = ref.mean(axis=1)
        comp_freqs, comp_db = _average_spectrum_db([comp], sr)
        ref_comp_freqs, ref_comp_db = _average_spectrum_db([ref_comp], ref_sr)
        delta = compute_delta_curve(comp_freqs, comp_db, ref_comp_freqs, ref_comp_db, max_delta_db)
        delta = _lowess_smooth_logfreq(comp_freqs, delta)
        delta_ranges.append((float(delta.min()), float(delta.max())))
        firs.append(design_fir(delta, comp_freqs, sr, numtaps))

    # 3) apply one FIR per component, then back to L/R
    if channels == 2:
        mid, side = _lr_to_ms(mix_arr)
        mid_f = fftconvolve(mid.astype(np.float64), firs[0], mode="same")
        side_f = fftconvolve(side.astype(np.float64), firs[1], mode="same")
        matched = _ms_to_lr(mid_f, side_f)
    else:
        matched = fftconvolve(mix_arr[:, 0].astype(np.float64), firs[0], mode="same")[:, np.newaxis]

    # 4) iterative RMS re-correction: the EQ may shift overall loudness,
    # re-measure and re-apply a plain gain until it is back where it started
    target_rms = float(np.sqrt(np.mean(mix_arr.astype(np.float64) ** 2)))
    for _ in range(RMS_RECORRECTIONS):
        current_rms = float(np.sqrt(np.mean(matched ** 2)))
        if current_rms <= 0.0:
            break
        gain = target_rms / current_rms
        if abs(20.0 * np.log10(gain)) < 0.05:
            break
        matched = matched * gain

    out = matched.astype(np.float32)
    if out.shape[1] == 1 and np.asarray(mix).ndim == 1:
        out = out[:, 0]
    lo = round(min(r[0] for r in delta_ranges), 2)
    hi = round(max(r[1] for r in delta_ranges), 2)
    report = {
        "max_delta_db": max_delta_db,
        "fir_taps": numtaps,
        "applied_delta_db_range": (lo, hi),
        "pieces_used": len(pieces),
        "mid_side": channels == 2,
        "lowess_frac": LOWESS_FRAC,
    }
    return out, report
