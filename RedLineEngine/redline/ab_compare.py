"""A/B comparison harness: loudness-matches a "before" and "after" render and
writes a measurement report (spectral balance, crest factor, stereo
correlation, true peak) -- an objective diff instead of trusting the ear
alone or trusting the pipeline's own self-reported QC numbers.

This module NEVER plays audio (no sounddevice, no driver.play_chunk()) --
see redline/qc.py and the project's own no-playback-in-tests convention. It
only reads/writes files and returns numbers; the user listens on their own
terms, in their own player, when they choose to.

Usage:
    python -m redline.ab_compare before.wav after.wav --out report.json
    # optionally also write a loudness-matched comparison WAV (before then
    # after, back to back) for the user to audition manually:
    python -m redline.ab_compare before.wav after.wav --out report.json --render-wav ab_compare.wav
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass

import numpy as np
import soundfile as sf

from .analysis.loudness import integrated_lufs, spectral_band_energies, SPECTRAL_BANDS
from .dsp_utils import finalize_for_export

TARGET_LUFS_FOR_MATCH = -18.0  # neutral common reference point for the comparison, not a mastering target
MAX_MATCH_GAIN_DB = 24.0  # guardrail: don't blow up a near-silent file trying to match loudness


@dataclass
class TrackMeasurement:
    lufs: float
    true_peak_db: float
    crest_factor_db: float
    stereo_correlation: float
    band_energies: dict[str, float]


@dataclass
class AbReport:
    before: TrackMeasurement
    after: TrackMeasurement
    lufs_delta_db: float
    band_energy_delta: dict[str, float]  # after - before, per band
    crest_factor_delta_db: float
    stereo_correlation_delta: float
    notes: list[str]


def _load_stereo(path: str) -> tuple[np.ndarray, int]:
    data, sr = sf.read(path, dtype="float32", always_2d=True)
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    return data, sr


def _crest_factor_db(signal: np.ndarray) -> float:
    peak = float(np.max(np.abs(signal)) + 1e-12)
    rms = float(np.sqrt(np.mean(signal.astype(np.float64) ** 2)) + 1e-12)
    return 20.0 * np.log10(peak / rms)


def _stereo_correlation(signal: np.ndarray) -> float:
    if signal.ndim == 1 or signal.shape[1] < 2:
        return 1.0
    l, r = signal[:, 0].astype(np.float64), signal[:, 1].astype(np.float64)
    if np.std(l) < 1e-9 or np.std(r) < 1e-9:
        return 1.0
    return float(np.corrcoef(l, r)[0, 1])


def _loudness_match(signal: np.ndarray, sr: int, target_lufs: float) -> np.ndarray:
    mono = signal.mean(axis=1) if signal.ndim == 2 else signal
    try:
        current = integrated_lufs(mono, sr)
    except Exception:
        return signal
    gain_db = float(np.clip(target_lufs - current, -MAX_MATCH_GAIN_DB, MAX_MATCH_GAIN_DB))
    return (signal * (10.0 ** (gain_db / 20.0))).astype(np.float32)


def _measure(signal: np.ndarray, sr: int) -> TrackMeasurement:
    mono = signal.mean(axis=1) if signal.ndim == 2 else signal
    try:
        lufs = integrated_lufs(mono, sr)
    except Exception:
        lufs = -70.0
    return TrackMeasurement(
        lufs=round(float(lufs), 2),
        true_peak_db=round(float(20.0 * np.log10(np.max(np.abs(signal)) + 1e-12)), 2),
        crest_factor_db=round(float(_crest_factor_db(signal)), 2),
        stereo_correlation=round(float(_stereo_correlation(signal)), 3),
        band_energies={k: round(float(v), 4) for k, v in spectral_band_energies(signal, sr).items()},
    )


def compare(before_path: str, after_path: str, render_wav_path: str | None = None) -> AbReport:
    """Loads both files, measures them as-is, then loudness-matches copies to
    TARGET_LUFS_FOR_MATCH so the spectral/dynamics comparison isn't confused
    by a plain level difference. Optionally writes a concatenated
    loudness-matched comparison WAV for manual auditioning (never played
    here)."""
    before_audio, before_sr = _load_stereo(before_path)
    after_audio, after_sr = _load_stereo(after_path)

    before_measurement = _measure(before_audio, before_sr)
    after_measurement = _measure(after_audio, after_sr)

    notes: list[str] = []
    if before_sr != after_sr:
        notes.append(f"sample rate differs: before={before_sr}Hz after={after_sr}Hz (measurements taken independently)")

    band_delta = {
        band: round(after_measurement.band_energies[band] - before_measurement.band_energies[band], 4)
        for band in before_measurement.band_energies
    }

    if render_wav_path is not None:
        before_matched = _loudness_match(before_audio, before_sr, TARGET_LUFS_FOR_MATCH)
        after_matched = _loudness_match(after_audio, after_sr, TARGET_LUFS_FOR_MATCH)
        if before_sr != after_sr:
            notes.append("render-wav skipped: sample rates differ, resample before comparing manually")
        else:
            gap = np.zeros((int(before_sr * 0.5), before_matched.shape[1]), dtype=np.float32)
            concatenated = np.concatenate([before_matched, gap, after_matched], axis=0)
            sf.write(render_wav_path, finalize_for_export(concatenated), before_sr, subtype="PCM_24")
            notes.append(f"loudness-matched A/B render written to {render_wav_path} (before, 0.5s gap, after) -- not played automatically")

    return AbReport(
        before=before_measurement,
        after=after_measurement,
        lufs_delta_db=round(float(after_measurement.lufs - before_measurement.lufs), 2),
        band_energy_delta=band_delta,
        crest_factor_delta_db=round(float(after_measurement.crest_factor_db - before_measurement.crest_factor_db), 2),
        stereo_correlation_delta=round(float(after_measurement.stereo_correlation - before_measurement.stereo_correlation), 3),
        notes=notes,
    )


def report_to_dict(report: AbReport) -> dict:
    return asdict(report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Loudness-matched A/B measurement report (no playback).")
    parser.add_argument("before", help="path to the 'before' render")
    parser.add_argument("after", help="path to the 'after' render")
    parser.add_argument("--out", default=None, help="write JSON report to this path (else prints to stdout)")
    parser.add_argument("--render-wav", default=None, help="also write a loudness-matched before/after comparison WAV to this path (for manual auditioning)")
    args = parser.parse_args(argv)

    report = compare(args.before, args.after, render_wav_path=args.render_wav)
    payload = json.dumps(report_to_dict(report), indent=2)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(payload)
        print(f"Report written to {args.out}")
    else:
        print(payload)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
