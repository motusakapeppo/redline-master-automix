"""Entry gate for audio: every stem is checked before it enters the pipeline,
so a corrupted file fails fast with a clear message instead of propagating
NaNs through a dozen DSP stages and crashing somewhere unrelated."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from redline.logging_setup import get_logger

logger = get_logger(__name__)

_MIN_SAMPLES = 256
_SILENCE_DBFS = -90.0
_DC_OFFSET_DBFS = -40.0
_MIN_SR = 8000
_MAX_SR = 192000
_MAX_DURATION_SEC = 30 * 60
_MAX_PATH_LEN = 260


@dataclass
class PreFlightReport:
    passed: bool = True
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def merge(self, other: "PreFlightReport") -> "PreFlightReport":
        self.passed = self.passed and other.passed
        self.issues.extend(other.issues)
        self.warnings.extend(other.warnings)
        return self


def _to_db(value: float) -> float:
    if value <= 0.0:
        return float("-inf")
    return 20.0 * np.log10(value)


class PreFlightValidator:
    @staticmethod
    def check_audio(audio: np.ndarray, sr: int, name: str) -> PreFlightReport:
        report = PreFlightReport()

        if audio.size == 0 or audio.shape[0] < _MIN_SAMPLES:
            report.passed = False
            report.issues.append(
                f"{name}: solo {audio.shape[0] if audio.ndim else 0} campioni (minimo {_MIN_SAMPLES}, serve per FFT)"
            )
            return report

        if np.isnan(audio).any():
            report.passed = False
            report.issues.append(f"{name}: contiene campioni NaN")
        if np.isinf(audio).any():
            report.passed = False
            report.issues.append(f"{name}: contiene campioni Inf")

        if report.issues:
            # Peak/DC/etc. on NaN/Inf data is meaningless — stop here.
            return report

        peak = float(np.max(np.abs(audio)))
        if _to_db(peak) < _SILENCE_DBFS:
            # WARNING, not blocking: a stem being entirely silent is a real,
            # normal case for section-split exports (e.g. "Horn" genuinely
            # doesn't play at all during the Intro) -- confirmed in practice
            # with a real multi-instrument section-split session where
            # several legitimately tacet stems tripped this as a hard
            # failure and stopped the whole load.
            report.warnings.append(f"{name}: silenzio totale (picco {_to_db(peak):.1f}dBFS)")

        if peak > 1.0:
            report.warnings.append(f"{name}: clipping rilevato (picco {peak:.3f}, {_to_db(peak):.1f}dBFS)")

        dc = float(np.mean(audio))
        if _to_db(abs(dc)) > _DC_OFFSET_DBFS:
            report.warnings.append(f"{name}: DC offset elevato ({_to_db(abs(dc)):.1f}dBFS)")

        if audio.ndim == 2 and audio.shape[1] == 2:
            if np.array_equal(audio[:, 0], audio[:, 1]):
                report.warnings.append(f"{name}: canali L/R identici (falso stereo)")
        if audio.ndim == 2 and audio.shape[1] > 2:
            report.warnings.append(f"{name}: {audio.shape[1]} canali (attesi 1 o 2)")

        duration_sec = audio.shape[0] / sr
        if duration_sec > _MAX_DURATION_SEC:
            report.warnings.append(
                f"{name}: durata {duration_sec / 60:.1f} minuti, considera lo streaming a chunk"
            )

        sr_report = PreFlightValidator.check_sample_rate(sr, name)
        report.merge(sr_report)

        return report

    @staticmethod
    def check_sample_rate(sr: int, name: str) -> PreFlightReport:
        report = PreFlightReport()
        if sr < _MIN_SR or sr > _MAX_SR:
            report.passed = False
            report.issues.append(f"{name}: sample rate {sr}Hz fuori range ({_MIN_SR}-{_MAX_SR}Hz)")
        return report

    @staticmethod
    def check_file_path(path: str) -> PreFlightReport:
        report = PreFlightReport()
        if len(path) > _MAX_PATH_LEN:
            report.warnings.append(f"Path lungo {len(path)} caratteri (oltre {_MAX_PATH_LEN}): {path}")
        return report

    @staticmethod
    def check_mixed_sample_rates(sample_rates: list[int], name: str) -> PreFlightReport:
        """Mixed sample rates are a WARNING, not a blocking ISSUE -- multi-
        session projects with stems recorded at different rates are a real,
        normal case, and input_loader._align() already resamples everything
        to the highest rate found before mixing. Blocking here would refuse
        a file set the pipeline can (and does) handle correctly."""
        report = PreFlightReport()
        if len(set(sample_rates)) > 1:
            report.warnings.append(f"{name}: sample rate misti tra stem ({sorted(set(sample_rates))}), verranno ricampionati al più alto")
        return report
