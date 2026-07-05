"""Optional mastering pass: loudness targeting for streaming platforms,
soft-clip + true-peak limiting, mid/side polish, and an automated QC pass —
or reference-matched mastering via `matchering`."""

from __future__ import annotations

from typing import Callable

import numpy as np
import pyloudnorm as pyln
from pedalboard import Pedalboard, Limiter, Gain, HighpassFilter, HighShelfFilter, Compressor
from scipy.signal import butter, sosfiltfilt

from .analyze import AnalysisResult
from .dsp_utils import to_mid_side, from_mid_side
from .qc import run_qc

StepCallback = Callable[[str], None]
EventCallback = Callable[[dict], None]


def _noop(_msg: str) -> None:
    pass


def _noop_event(_evt: dict) -> None:
    pass


# LUFS integrated-loudness targets per platform (streaming normalizes to these)
PLATFORM_TARGETS = {
    "spotify": -14.0,
    "apple": -16.0,
    "youtube": -13.0,
    "club": -9.0,  # louder target for EDM/club-oriented material
}

TRUE_PEAK_CEILING_DB = -1.0
CLIP_CEILING_DB = -0.3  # soft-clip shaves the sharpest transient overshoots before the limiter does the rest
SIDE_MONO_HZ = 120.0  # below this, side-channel content is removed (mono bass — vital for translation/impact)
SIDE_AIR_SHELF_HZ = 9000.0
SIDE_AIR_GAIN_DB = 1.2

# Multiband glue: low/mid/high split via simple Butterworth filters (not a
# phase-perfect linear-phase crossover — a common, practical compromise, not
# a claim of surgical precision). Each band gets its own gentle compressor
# so the low end doesn't pull the whole mix's dynamics around and vice versa.
MULTIBAND_LOW_HZ = 200.0
MULTIBAND_HIGH_HZ = 4000.0
MULTIBAND_RECIPES = {
    "low": dict(threshold_db=-18.0, ratio=2.5, attack_ms=20.0, release_ms=180.0),
    "mid": dict(threshold_db=-16.0, ratio=1.8, attack_ms=10.0, release_ms=120.0),
    "high": dict(threshold_db=-14.0, ratio=1.6, attack_ms=5.0, release_ms=80.0),
}


def _target_lufs_for_genre(genre_name: str, platform: str) -> float:
    if platform == "auto":
        return PLATFORM_TARGETS["club"] if "EDM" in genre_name else PLATFORM_TARGETS["spotify"]
    return PLATFORM_TARGETS.get(platform, PLATFORM_TARGETS["spotify"])


def _soft_clip(signal: np.ndarray, ceiling_db: float, drive: float = 1.6) -> np.ndarray:
    """Transparent-ish tanh soft clip: shaves only the extreme peaks that
    poke above the ceiling, leaving everything under it untouched — this is
    what lets the final limiter work far less hard (it no longer has to
    catch every transient on its own), preserving more of the track's punch."""
    ceiling = 10.0 ** (ceiling_db / 20.0)
    scaled = signal / ceiling
    clipped = np.tanh(scaled * drive) / np.tanh(drive)
    return (clipped * ceiling).astype(np.float32)


def _split_three_bands(mono: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    nyquist = sr / 2.0
    sos_low = butter(4, MULTIBAND_LOW_HZ / nyquist, btype="lowpass", output="sos")
    sos_high = butter(4, MULTIBAND_HIGH_HZ / nyquist, btype="highpass", output="sos")
    low = sosfiltfilt(sos_low, mono)
    high = sosfiltfilt(sos_high, mono)
    mid = mono - low - high
    return low, mid, high


def _multiband_compress(signal: np.ndarray, sr: int, on_step: StepCallback, on_event: EventCallback) -> np.ndarray:
    """Splits into low/mid/high, compresses each band independently with its
    own gentle recipe, sums back — glue that doesn't let the sub-bass's
    transients drag the vocal/presence range's dynamics around, or vice versa."""
    out = np.zeros_like(signal)
    for ch in range(signal.shape[1]):
        low, mid, high = _split_three_bands(signal[:, ch].astype(np.float64), sr)
        low = Pedalboard([Compressor(**MULTIBAND_RECIPES["low"])])(low.reshape(1, -1).astype(np.float32), sr).reshape(-1)
        mid = Pedalboard([Compressor(**MULTIBAND_RECIPES["mid"])])(mid.reshape(1, -1).astype(np.float32), sr).reshape(-1)
        high = Pedalboard([Compressor(**MULTIBAND_RECIPES["high"])])(high.reshape(1, -1).astype(np.float32), sr).reshape(-1)
        out[:, ch] = low + mid + high

    on_step(
        f"Compressione multibanda: basso <{MULTIBAND_LOW_HZ:.0f}Hz ({MULTIBAND_RECIPES['low']['ratio']}:1), "
        f"medio ({MULTIBAND_RECIPES['mid']['ratio']}:1), alto >{MULTIBAND_HIGH_HZ:.0f}Hz ({MULTIBAND_RECIPES['high']['ratio']}:1)"
    )
    on_event({"type": "multiband_compressor", "low_hz": MULTIBAND_LOW_HZ, "high_hz": MULTIBAND_HIGH_HZ, "recipes": MULTIBAND_RECIPES})
    return out.astype(np.float32)


def _mid_side_polish(signal: np.ndarray, sr: int, on_step: StepCallback, on_event: EventCallback) -> np.ndarray:
    """Mono-izes sub-bass (mono compatibility + translation on small speakers)
    and adds a touch of high-frequency width — both done on the side channel
    only, so the mono/mid content (where most of the track's weight lives)
    is untouched."""
    mid, side = to_mid_side(signal)

    board = Pedalboard(
        [
            HighpassFilter(cutoff_frequency_hz=SIDE_MONO_HZ),
            HighShelfFilter(cutoff_frequency_hz=SIDE_AIR_SHELF_HZ, gain_db=SIDE_AIR_GAIN_DB, q=0.7),
        ]
    )
    side_processed = board(side.reshape(1, -1), sr).reshape(-1).astype(np.float32)

    on_step(f"Mid/Side: basso mono sotto {SIDE_MONO_HZ:.0f}Hz, aria {SIDE_AIR_GAIN_DB:+.1f}dB sopra {SIDE_AIR_SHELF_HZ / 1000:.0f}kHz (solo canale Side)")
    on_event({"type": "mid_side", "mono_below_hz": SIDE_MONO_HZ, "air_shelf_hz": SIDE_AIR_SHELF_HZ, "air_gain_db": SIDE_AIR_GAIN_DB})

    return from_mid_side(mid, side_processed)


def render_master(
    mixed: np.ndarray,
    sr: int,
    analysis: AnalysisResult,
    platform: str = "auto",
    on_step: StepCallback = _noop,
    on_event: EventCallback = _noop_event,
) -> np.ndarray:
    meter = pyln.Meter(sr)
    mono_ref = mixed.mean(axis=1) if mixed.ndim == 2 else mixed
    try:
        current_lufs = meter.integrated_loudness(mono_ref)
    except ValueError:
        current_lufs = -70.0

    target_lufs = _target_lufs_for_genre(analysis.genre.name, platform)
    gain_db = target_lufs - current_lufs
    # Guardrails: never boost more than +12dB (would just raise noise floor) or
    # cut more than -12dB (source was already far louder than any sane target).
    gain_db = float(np.clip(gain_db, -12.0, 12.0))

    on_step(f"Loudness misurata: {current_lufs:.1f} LUFS -> target {target_lufs:.1f} LUFS ({gain_db:+.1f}dB)")
    on_event({"type": "loudness_gain", "current_lufs": round(current_lufs, 1), "target_lufs": target_lufs, "gain_db": round(gain_db, 1)})

    gained = Pedalboard([Gain(gain_db=gain_db)])(mixed.T, sr).T

    glued = _multiband_compress(gained, sr, on_step, on_event)

    on_step(f"Soft clipper a {CLIP_CEILING_DB}dB (scarica i picchi estremi prima del limiter)")
    on_event({"type": "soft_clip", "ceiling_db": CLIP_CEILING_DB})
    clipped = _soft_clip(glued, CLIP_CEILING_DB)

    polished = _mid_side_polish(clipped, sr, on_step, on_event)

    on_step(f"Limiting finale a {TRUE_PEAK_CEILING_DB}dB true-peak ceiling")
    on_event({"type": "limiter", "ceiling_db": TRUE_PEAK_CEILING_DB})
    limiter_board = Pedalboard([Limiter(threshold_db=TRUE_PEAK_CEILING_DB, release_ms=100.0)])
    mastered = limiter_board(polished.T, sr).T

    # pedalboard's Limiter can still overshoot on hard transients when the
    # requested makeup gain is large (its envelope needs a moment to react) —
    # this hard clamp is the actual guarantee that the promised ceiling holds,
    # the limiter above just keeps it musical rather than doing all the work.
    ceiling = 10.0 ** (TRUE_PEAK_CEILING_DB / 20.0)
    peak = np.max(np.abs(mastered)) + 1e-9
    if peak > ceiling:
        mastered = mastered * (ceiling / peak)

    on_step("Controllo qualità automatico: misuro il risultato e correggo se serve...")
    mastered, report = run_qc(mastered, sr, analysis.genre.name, target_lufs, TRUE_PEAK_CEILING_DB)

    # The QC correction pass can itself push a band back over the ceiling
    # (a boost is still a boost) — re-clamp so the promised true-peak
    # ceiling holds no matter what correction was applied.
    peak = np.max(np.abs(mastered)) + 1e-9
    if peak > ceiling:
        mastered = mastered * (ceiling / peak)

    # report.true_peak_db was measured *inside* run_qc, before this final
    # clamp — reporting that stale number would claim a peak that no longer
    # exists in the actual output (confirmed in practice: it printed +0.58dB
    # while the saved file was correctly at -1.00dB). Overwrite it with the
    # real final measurement so what's printed matches what's on disk.
    report.true_peak_db = 20.0 * np.log10(np.max(np.abs(mastered)) + 1e-12)

    on_event({
        "type": "qc_report",
        "lufs": round(report.lufs, 1),
        "true_peak_db": round(report.true_peak_db, 2),
        "mono_compatibility": round(report.mono_compatibility, 2),
        "corrections": report.corrections_applied,
        "passed": report.passed,
    })
    if report.corrections_applied:
        on_step("QC: correzioni applicate — " + "; ".join(report.corrections_applied))
    on_step(
        f"QC: {report.lufs:.1f} LUFS, true peak {report.true_peak_db:.2f}dB, "
        f"compatibilità mono {report.mono_compatibility:.2f} — {'OK' if report.passed else 'entro i limiti ma non perfetto, vedi dettagli'}"
    )

    on_step("Mastering completato.")
    return mastered


def render_master_reference(mix_path: str, reference_path: str, output_path: str, on_step: StepCallback = _noop) -> None:
    """Alternative mastering strategy: match tonal balance and loudness to a
    user-supplied reference track via matchering, instead of fixed platform
    LUFS targets."""
    import matchering as mg

    on_step(f"Mastering per riferimento: adatto il timbro/loudness a '{reference_path}'")
    mg.process(
        target=mix_path,
        reference=reference_path,
        results=[mg.pcm24(output_path)],
    )
    on_step("Mastering per riferimento completato.")
