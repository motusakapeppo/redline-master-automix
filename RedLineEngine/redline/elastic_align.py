"""Syllable-level elastic time alignment for vocal doubles (a lightweight,
dependency-free take on what VocALign does).

The existing cross-correlation alignment (alignment.py) finds one global
sample delay — it fixes "the phrase starts late", not "the singer dragged
one vowel or clipped a consonant early on this specific double". This
module finds a local, time-varying warp path via Dynamic Time Warping
between the double's and the lead's energy envelopes, then time-stretches
short windows of the double to track it — but only where the required
stretch is small enough to be safe.

Deliberately conservative: pyrubberband (the usual professional choice)
needs an external `rubberband-cli` binary not available in this
environment, so this uses librosa's phase-vocoder time_stretch, which
handles small, localized warps well but degrades on large ones — exactly
why the safety net matters here, not just as a nicety.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import librosa

from .dsp_utils import envelope_follower

# If DTW says a window needs to stretch/compress by more than this fraction,
# the take's timing was too different from the lead to trust a correction —
# skip that window rather than risk the robotic "flutter" artifact of
# over-warping a bad match.
MAX_SAFE_WARP_FRACTION = 0.05

_ENVELOPE_BLOCK = 1024  # ~23ms at 44.1kHz — fine enough to catch syllable-level drift
_WINDOW_SECONDS = 0.4
_ANALYSIS_SR = 11025  # DTW/envelope work is cheap and doesn't need full resolution


@dataclass
class ElasticAlignResult:
    audio: np.ndarray
    windows_total: int
    windows_stretched: int
    windows_skipped_unsafe: int


def _envelope(mono: np.ndarray, sr: int) -> np.ndarray:
    return envelope_follower(np.abs(mono), sr, attack_ms=5.0, release_ms=25.0, block=_ENVELOPE_BLOCK)


def _dtw_time_map(double_mono: np.ndarray, lead_mono: np.ndarray, sr: int) -> np.ndarray:
    """Returns, for each frame index in the double's envelope, the matching
    frame index in the lead's envelope (monotonic DTW path), at `sr`."""
    env_double = _envelope(double_mono, sr)[::_ENVELOPE_BLOCK]
    env_lead = _envelope(lead_mono, sr)[::_ENVELOPE_BLOCK]

    # librosa.sequence.dtw wants feature matrices (n_features, n_frames)
    x = np.atleast_2d(env_double)
    y = np.atleast_2d(env_lead)
    _cost, wp = librosa.sequence.dtw(X=x, Y=y, backtrack=True)
    wp = wp[::-1]  # librosa returns the path from end to start

    # wp columns: (index into x/double, index into y/lead) — build a
    # double-frame -> lead-frame map, taking the last match per double frame
    # (a double frame can match multiple lead frames on a real warp path).
    n_double_frames = env_double.shape[0]
    frame_map = np.arange(n_double_frames, dtype=np.float64)
    for d_idx, l_idx in wp:
        frame_map[d_idx] = l_idx
    return frame_map * _ENVELOPE_BLOCK  # back to sample indices at `sr`


def elastic_align(double_signal: np.ndarray, lead_signal: np.ndarray, sr: int, name: str = "") -> ElasticAlignResult:
    """Time-warps `double_signal` window by window to track `lead_signal`'s
    syllable timing, skipping any window whose required warp exceeds
    MAX_SAFE_WARP_FRACTION. Assumes the two signals are already roughly
    aligned (e.g. by alignment.align_to_reference) — this corrects the
    remaining local drift, not gross timing offsets.

    MAIN/LEAD GUARD: if the stem name contains MAIN or LEAD, or if the
    "lead" signal has less than 60% of the double's RMS energy (caller
    likely swapped the arguments), bail out and return the double unchanged.
    """
    # Name-based guard: Main/Lead vocals are the grid, never warped
    if "MAIN" in name.upper() or "LEAD" in name.upper():
        return ElasticAlignResult(audio=double_signal, windows_total=0, windows_stretched=0, windows_skipped_unsafe=0)

    mono_double = double_signal.mean(axis=1) if double_signal.ndim == 2 else double_signal
    mono_lead = lead_signal.mean(axis=1) if lead_signal.ndim == 2 else lead_signal
    n = min(mono_double.shape[0], mono_lead.shape[0])

    # Energy-based guard: lead should have comparable or higher energy than double
    rms_double = float(np.sqrt(np.mean(mono_double.astype(np.float64) ** 2))) if n > 0 else 0.0
    rms_lead = float(np.sqrt(np.mean(mono_lead.astype(np.float64) ** 2))) if n > 0 else 0.0
    if rms_double > 0 and rms_lead < 0.6 * rms_double:
        return ElasticAlignResult(audio=double_signal, windows_total=0, windows_stretched=0, windows_skipped_unsafe=0)
    if n < sr * 2:
        return ElasticAlignResult(audio=double_signal, windows_total=0, windows_stretched=0, windows_skipped_unsafe=0)

    analysis_sr = min(_ANALYSIS_SR, sr)
    d_ds = librosa.resample(mono_double[:n].astype(np.float32), orig_sr=sr, target_sr=analysis_sr) if sr != analysis_sr else mono_double[:n]
    l_ds = librosa.resample(mono_lead[:n].astype(np.float32), orig_sr=sr, target_sr=analysis_sr) if sr != analysis_sr else mono_lead[:n]

    try:
        frame_map_samples = _dtw_time_map(d_ds, l_ds, analysis_sr)
    except Exception:
        return ElasticAlignResult(audio=double_signal, windows_total=0, windows_stretched=0, windows_skipped_unsafe=0)

    # Convert the analysis-rate frame map to a time-ratio curve at the
    # analysis rate, then window over the *original* signal.
    analysis_positions = np.arange(len(frame_map_samples), dtype=np.float64)
    window_samples = int(_WINDOW_SECONDS * sr)
    n_windows = max(1, n // window_samples)

    out_channels = []
    channels = double_signal.shape[1] if double_signal.ndim == 2 else 1
    total, stretched, skipped = 0, 0, 0

    for ch in range(channels):
        chan = double_signal[:, ch] if double_signal.ndim == 2 else double_signal
        out = np.zeros(n, dtype=np.float32)
        window_fn = np.hanning(2 * window_samples)[:window_samples] if window_samples > 1 else np.ones(1)

        for w in range(n_windows):
            total += 1
            start = w * window_samples
            end = min(start + window_samples, n)
            if end <= start:
                continue

            # Map this window's center to the analysis-rate frame domain and
            # read off the corresponding lead-time position to get the
            # local stretch ratio actually required.
            center_sample = (start + end) / 2.0
            center_analysis_frame = center_sample / sr * analysis_sr / _ENVELOPE_BLOCK
            idx = int(np.clip(center_analysis_frame, 0, len(frame_map_samples) - 1))
            mapped_sample_analysis = frame_map_samples[idx]
            mapped_time_s = mapped_sample_analysis / analysis_sr
            own_time_s = center_sample / sr
            # ratio > 1 means the double needs to play back *faster* here to
            # catch up to where the lead already is at this point, and vice versa.
            denom = own_time_s if own_time_s > 1e-6 else 1e-6
            local_ratio = 1.0 + (own_time_s - mapped_time_s) / denom
            local_ratio = float(np.clip(local_ratio, 0.5, 2.0))

            segment = chan[start:end]
            seg_len = segment.size
            is_silent = seg_len == 0 or float(np.sqrt(np.mean(segment.astype(np.float64) ** 2))) < 1e-4

            if is_silent or abs(local_ratio - 1.0) > MAX_SAFE_WARP_FRACTION or seg_len < 64:
                # Silent (nothing audible to warp), unsafe warp, or too short
                # to stretch meaningfully — leave as-is.
                skipped += 1
                stretched_segment = segment
            else:
                try:
                    stretched_segment = librosa.effects.time_stretch(segment.astype(np.float32), rate=local_ratio)
                    stretched += 1
                except Exception:
                    stretched_segment = segment

            # time_stretch changes length — always force back to the window's
            # original sample count so windows overlap-add cleanly regardless
            # of which branch above ran.
            if stretched_segment.size != seg_len:
                if stretched_segment.size > 1:
                    stretched_segment = librosa.resample(
                        stretched_segment, orig_sr=stretched_segment.size, target_sr=seg_len
                    )
                stretched_segment = np.resize(stretched_segment, seg_len)

            fade = window_fn[:seg_len] if window_fn.size >= seg_len else np.ones(seg_len, dtype=np.float32)
            out[start:end] += stretched_segment * fade

        out_channels.append(out)

    aligned = np.stack(out_channels, axis=1) if double_signal.ndim == 2 else out_channels[0]
    return ElasticAlignResult(audio=aligned.astype(np.float32), windows_total=total, windows_stretched=stretched, windows_skipped_unsafe=skipped)
