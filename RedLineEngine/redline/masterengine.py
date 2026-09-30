"""Optional mastering pass: loudness targeting for streaming platforms,
soft-clip + true-peak limiting, mid/side polish, and an automated QC pass —
or reference-matched mastering via `matchering`."""

from __future__ import annotations

from typing import Callable

import numpy as np
import pyloudnorm as pyln
from pedalboard import Pedalboard, Limiter, Gain, HighpassFilter, HighShelfFilter, Compressor
from scipy.signal import butter, sosfiltfilt

from . import config
from .analyze import AnalysisResult
from .dsp_utils import to_mid_side, from_mid_side, db_to_gain
from .ltas import match_ltas
from .platforms import PLATFORM_TARGETS  # canonical registry; re-exported here so existing importers keep working
from .qc import run_qc, _mono_compatibility, assess_qc_pass, resolve_target
from .analysis.loudness import crest_factor, integrated_lufs, spectral_band_energies
from .correlometer import measure_bass_phase_shift_deg_abs

StepCallback = Callable[[str], None]
EventCallback = Callable[[dict], None]
AuditionCallback = Callable[[np.ndarray, np.ndarray, int], None]
BeepCallback = Callable[[], None]


def _noop(_msg: str) -> None:
    pass


def _noop_event(_evt: dict) -> None:
    pass


def _noop_beep() -> None:
    pass


# LUFS integrated-loudness targets per platform (streaming normalizes to
# these) -- canonical values live in redline.platforms and are imported at
# the top of this module, so `from redline.masterengine import
# PLATFORM_TARGETS` keeps working unchanged (same dict object).

TRUE_PEAK_CEILING_DB = -1.0
CLIP_CEILING_DB = -0.3  # soft-clip shaves the sharpest transient overshoots before the limiter does the rest
SIDE_MONO_HZ = 120.0  # below this, side-channel content is removed (mono bass — vital for translation/impact)
SIDE_AIR_SHELF_HZ = 9000.0
SIDE_AIR_GAIN_DB = 1.2

# Multiband glue: low/mid/high split via simple Butterworth filters (not a
# phase-perfect linear-phase crossover — a common, practical compromise, not
# a claim of surgical precision). Each band gets its own gentle compressor
# so the low end doesn't pull the whole mix's dynamics around and vice versa.
MULTIBAND_LOW_HZ = 150.0  # was 200 -- reference mastering chains split lower (120-170Hz), keeping kick fundamental + bass in the low band without also grabbing vocal low-mid body
MULTIBAND_HIGH_HZ = 4000.0
MULTIBAND_RECIPES = {
    "low": dict(threshold_db=-18.0, ratio=2.5, attack_ms=20.0, release_ms=180.0),
    "mid": dict(threshold_db=-16.0, ratio=1.8, attack_ms=10.0, release_ms=120.0),
    "high": dict(threshold_db=-14.0, ratio=1.6, attack_ms=5.0, release_ms=80.0),
}

# --- Iterative reference-profile feedback loop (point 2 of the reference-
# profile upgrade, see reference_profiles.py): after run_qc's own bounded
# spectral-band correction, this measures LUFS/crest-factor/mono-compatibility
# against reference_profiles.resolve_perceptual_target() and applies small,
# director_safety-clamped corrective moves. Tolerances are typical mastering
# QC conventions (documented in DSP_ENGINE_SPECS.md Sezione 7.2):
#   - LUFS: +/-0.5 LU (streaming platforms themselves normalize in roughly
#     this range, so tighter is chasing noise)
#   - Crest factor: +/-1.5dB (audible loudness-war-vs-dynamics differences
#     start below this; QC pass shouldn't fight for less than that)
#   - Mono/stereo-width compatibility: +/-0.08 (qc.py's own pass/fail floor
#     is a much coarser 0.6, this is a tighter *target* band around the
#     genre's ideal, not a new safety floor)
MASTER_CORRECTION_MAX_PASSES = 3
MASTER_LUFS_TOLERANCE = 0.5
MASTER_CREST_TOLERANCE_DB = 1.5
MASTER_MONO_COMPAT_TOLERANCE = 0.08


def _target_lufs_for_genre(genre_name: str, platform: str) -> float:
    if platform == "auto":
        return PLATFORM_TARGETS["club"] if "EDM" in genre_name else PLATFORM_TARGETS["spotify"]
    return PLATFORM_TARGETS.get(platform, PLATFORM_TARGETS["spotify"])


def _perceptual_lufs_target(genre_name: str, platform: str, genre_default: float) -> float:
    """LUFS target for the iterative feedback loop. The user's chosen platform
    wins whenever it isn't "auto" (so an explicit "apple" pulls toward -16
    instead of the genre default); "auto" keeps the genre-based default that
    resolve_perceptual_target() already resolved (club for EDM, spotify
    otherwise). Pure and side-effect-free so the override is unit-testable
    without running the whole mastering chain."""
    if platform == "auto":
        return genre_default
    return _target_lufs_for_genre(genre_name, platform)


def _soft_clip(signal: np.ndarray, ceiling_db: float, drive: float = 1.6) -> np.ndarray:
    """Transparent-ish tanh soft clip: shaves only the extreme peaks that
    poke above the ceiling, leaving everything under it untouched — this is
    what lets the final limiter work far less hard (it no longer has to
    catch every transient on its own), preserving more of the track's punch."""
    ceiling = 10.0 ** (ceiling_db / 20.0)
    scaled = signal / ceiling
    clipped = np.tanh(scaled * drive) / np.tanh(drive)
    return (clipped * ceiling).astype(np.float32)


def _band_split_filters(sr: int) -> tuple[np.ndarray, np.ndarray]:
    """Filter design (sos coefficients) depends only on `sr`, not on the
    signal -- computed once per _multiband_compress call and reused across
    channels instead of re-running butter() identically for every channel."""
    nyquist = sr / 2.0
    sos_low = butter(4, MULTIBAND_LOW_HZ / nyquist, btype="lowpass", output="sos")
    sos_high = butter(4, MULTIBAND_HIGH_HZ / nyquist, btype="highpass", output="sos")
    return sos_low, sos_high


def _split_three_bands(
    mono: np.ndarray, sr: int, sos_filters: tuple[np.ndarray, np.ndarray] | None = None
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    sos_low, sos_high = sos_filters if sos_filters is not None else _band_split_filters(sr)
    low = sosfiltfilt(sos_low, mono)
    high = sosfiltfilt(sos_high, mono)
    mid = mono - low - high
    return low, mid, high


def _multiband_compress(
    signal: np.ndarray,
    sr: int,
    on_step: StepCallback,
    on_event: EventCallback,
    on_audition: AuditionCallback | None = None,
) -> np.ndarray:
    """Splits into low/mid/high, compresses each band independently with its
    own gentle recipe, sums back — glue that doesn't let the sub-bass's
    transients drag the vocal/presence range's dynamics around, or vice versa."""
    out = np.zeros_like(signal)
    sos_filters = _band_split_filters(sr)
    for ch in range(signal.shape[1]):
        low, mid, high = _split_three_bands(signal[:, ch].astype(np.float64), sr, sos_filters)
        low = Pedalboard([Compressor(**MULTIBAND_RECIPES["low"])])(low.reshape(1, -1).astype(np.float32), sr).reshape(-1)
        mid = Pedalboard([Compressor(**MULTIBAND_RECIPES["mid"])])(mid.reshape(1, -1).astype(np.float32), sr).reshape(-1)
        high = Pedalboard([Compressor(**MULTIBAND_RECIPES["high"])])(high.reshape(1, -1).astype(np.float32), sr).reshape(-1)
        out[:, ch] = low + mid + high

    on_step(
        f"Compressione multibanda: basso <{MULTIBAND_LOW_HZ:.0f}Hz ({MULTIBAND_RECIPES['low']['ratio']}:1), "
        f"medio ({MULTIBAND_RECIPES['mid']['ratio']}:1), alto >{MULTIBAND_HIGH_HZ:.0f}Hz ({MULTIBAND_RECIPES['high']['ratio']}:1)"
    )
    on_event({"type": "multiband_compressor", "low_hz": MULTIBAND_LOW_HZ, "high_hz": MULTIBAND_HIGH_HZ, "recipes": MULTIBAND_RECIPES})

    # Neural Monitor / Live Audition (off by default): lets the user actually
    # hear the glue compression's effect through real speakers instead of
    # only reading a ratio number. Kept entirely optional/callback-driven so
    # masterengine.py never has to know about pywebview or audio hardware --
    # app/api.py supplies on_audition only when ENABLE_LIVE_AUDITION is on.
    if on_audition is not None:
        on_audition(signal, out, sr)

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


def _crest_factor_db(signal: np.ndarray) -> float:
    """crest_factor() in analysis/loudness.py returns a linear peak/rms
    ratio, not dB -- but reference_profiles.py's CREST_FACTOR_TARGETS (and
    every comparison against them below) are expressed in dB. Convert here
    rather than at the source, since crest_factor() is also used elsewhere
    (genre detection, depth staging) where its linear-ratio thresholds are
    the ones actually in use."""
    return 20.0 * float(np.log10(crest_factor(signal)))


def _measure_perceptual(signal: np.ndarray, sr: int, meter: pyln.Meter) -> dict:
    mono = signal.mean(axis=1) if signal.ndim == 2 else signal
    try:
        lufs = float(meter.integrated_loudness(mono))
    except ValueError:
        lufs = -70.0
    return {
        "lufs": lufs,
        "crest_factor": _crest_factor_db(signal),
        "mono_compatibility": _mono_compatibility(signal),
    }


def _apply_reference_correction(
    mastered: np.ndarray,
    sr: int,
    genre_name: str,
    ceiling: float,
    on_step: StepCallback,
    on_event: EventCallback,
    on_beep: BeepCallback = _noop_beep,
    platform: str = "auto",
) -> tuple[np.ndarray, list[str]]:
    """Bounded iterative feedback loop against reference_profiles.py's
    non-spectral targets (LUFS, crest factor, mono/stereo-width
    compatibility) -- complementary to run_qc's own spectral-band (LTAS)
    correction loop in qc.py. Every corrective move is passed through
    director_safety.clamp_params() before being applied, so it can never
    exceed the safe ranges already defined there. Runs up to
    MASTER_CORRECTION_MAX_PASSES passes, stopping early once every metric is
    within tolerance or a pass fails to improve on the last (avoids
    oscillation between two corrections fighting each other).

    `platform` (default "auto") overrides the LUFS target with the user's
    chosen platform target -- otherwise this loop would fight the
    platform-aware target render_master already computed and passed to
    run_qc. Crest-factor and mono/stereo-width targets stay genre-based
    (they aren't platform-dependent)."""
    from .reference_profiles import resolve_perceptual_target
    from .director_safety import clamp_params

    target = resolve_perceptual_target(genre_name)
    target["target_lufs"] = _perceptual_lufs_target(genre_name, platform, target["target_lufs"])
    meter = pyln.Meter(sr)
    notes: list[str] = []
    corrected = mastered
    prev_total_delta = None

    for pass_idx in range(MASTER_CORRECTION_MAX_PASSES):
        m = _measure_perceptual(corrected, sr, meter)
        lufs_delta = target["target_lufs"] - m["lufs"]
        crest_delta = target["crest_factor"] - m["crest_factor"]
        width_delta = target["mono_compatibility"] - m["mono_compatibility"]
        total_delta = abs(lufs_delta) + abs(crest_delta) + abs(width_delta)

        on_step(
            f"Feedback iterativo mastering (pass {pass_idx + 1}/{MASTER_CORRECTION_MAX_PASSES}): "
            f"LUFS {m['lufs']:.1f} (target {target['target_lufs']:.1f}), "
            f"crest {m['crest_factor']:.1f}dB (target {target['crest_factor']:.1f}dB), "
            f"mono compat {m['mono_compatibility']:.2f} (target {target['mono_compatibility']:.2f})"
        )
        on_event({
            "type": "master_feedback_pass", "pass": pass_idx + 1,
            "lufs": round(m["lufs"], 2), "crest_factor": round(m["crest_factor"], 2),
            "mono_compatibility": round(m["mono_compatibility"], 3),
            "lufs_delta": round(lufs_delta, 2), "crest_delta": round(crest_delta, 2), "width_delta": round(width_delta, 3),
        })
        on_beep()

        within_tolerance = (
            abs(lufs_delta) < MASTER_LUFS_TOLERANCE
            and abs(crest_delta) < MASTER_CREST_TOLERANCE_DB
            and abs(width_delta) < MASTER_MONO_COMPAT_TOLERANCE
        )
        if within_tolerance:
            break
        if prev_total_delta is not None and total_delta >= prev_total_delta:
            notes.append(f"feedback loop fermato dopo {pass_idx} pass: nessun ulteriore miglioramento")
            break
        prev_total_delta = total_delta

        applied_any = False

        if abs(lufs_delta) >= MASTER_LUFS_TOLERANCE:
            clamped, _ = clamp_params({"gain_db": lufs_delta})
            gain_db = clamped["gain_db"]
            corrected = Pedalboard([Gain(gain_db=gain_db)])(corrected.T, sr).T
            notes.append(f"pass {pass_idx + 1}: makeup loudness {gain_db:+.2f}dB")
            applied_any = True

        if crest_delta < -MASTER_CREST_TOLERANCE_DB:
            # Measured crest factor is higher than the genre target (too
            # peaky/dynamic) -- a gentle extra glue pass brings it down.
            # The opposite direction (crest already too LOW/over-compressed)
            # can't be corrected by adding more DSP -- that needs expansion,
            # out of scope for a bounded corrective safety pass.
            clamped, _ = clamp_params({"compressor_ratio": 1.3, "compressor_threshold_db": -10.0})
            comp = Compressor(
                threshold_db=clamped["compressor_threshold_db"],
                ratio=clamped["compressor_ratio"],
                attack_ms=15.0,
                release_ms=150.0,
            )
            corrected = Pedalboard([comp])(corrected.T, sr).T
            notes.append(f"pass {pass_idx + 1}: compressione glue extra (crest {m['crest_factor']:.1f}dB oltre target)")
            applied_any = True

        if abs(width_delta) >= MASTER_MONO_COMPAT_TOLERANCE:
            # width_delta > 0: target wants MORE mono compatibility than
            # measured -- narrow the side channel. < 0: target wants a wider
            # image -- widen it. Reuses director_safety's eq_gain_db safe
            # range (+/-6dB); there's no dedicated "width" parameter defined
            # there, and a side-channel gain nudge is functionally the same
            # kind of bounded gain move.
            side_gain_db = float(np.clip(-width_delta * 8.0, -6.0, 6.0))
            clamped, _ = clamp_params({"eq_gain_db": side_gain_db})
            side_gain_db = clamped["eq_gain_db"]
            mid, side = to_mid_side(corrected)
            side = side * db_to_gain(side_gain_db)
            corrected = from_mid_side(mid, side)
            notes.append(f"pass {pass_idx + 1}: larghezza stereo {side_gain_db:+.2f}dB (canale Side)")
            applied_any = True

        # Corrective moves can push over the true-peak ceiling -- re-clamp
        # every pass, same guarantee render_master already enforces after
        # the limiter and after run_qc's own correction.
        peak = np.max(np.abs(corrected)) + 1e-9
        if peak > ceiling:
            corrected = corrected * (ceiling / peak)

        if not applied_any:
            break

    return corrected.astype(np.float32), notes


def render_master(
    mixed: np.ndarray,
    sr: int,
    analysis: AnalysisResult,
    platform: str = "auto",
    on_step: StepCallback = _noop,
    on_event: EventCallback = _noop_event,
    reference: np.ndarray | None = None,
    reference_sr: int | None = None,
    on_audition: AuditionCallback | None = None,
    on_beep: BeepCallback = _noop_beep,
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

    glued = _multiband_compress(gained, sr, on_step, on_event, on_audition)

    on_step(f"Soft clipper a {CLIP_CEILING_DB}dB (scarica i picchi estremi prima del limiter)")
    on_event({"type": "soft_clip", "ceiling_db": CLIP_CEILING_DB})
    on_beep()
    clipped = _soft_clip(glued, CLIP_CEILING_DB)

    polished = _mid_side_polish(clipped, sr, on_step, on_event)
    on_beep()

    if reference is not None and config.is_enabled("ENABLE_LTAS_MATCHING"):
        on_step("Matchering FIR: clono l'impronta spettrale della reference track...")
        on_beep()
        polished, ltas_report = match_ltas(polished, sr, reference, reference_sr or sr)
        on_event({"type": "ltas_match", **ltas_report})
        on_step(f"LTAS: delta applicato entro +/-{ltas_report['max_delta_db']}dB, FIR a {ltas_report['fir_taps']} tap")
        on_beep()

    on_step(f"Limiting finale a {TRUE_PEAK_CEILING_DB}dB true-peak ceiling")
    on_event({"type": "limiter", "ceiling_db": TRUE_PEAK_CEILING_DB})
    on_beep()
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
    on_beep()
    mastered, report = run_qc(mastered, sr, analysis.genre.name, target_lufs, TRUE_PEAK_CEILING_DB)
    on_beep()

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

    on_step("Feedback iterativo: confronto LUFS/crest/larghezza stereo contro il profilo di riferimento del genere...")
    on_beep()
    mastered, feedback_notes = _apply_reference_correction(
        mastered, sr, analysis.genre.name, ceiling, on_step, on_event, on_beep, platform=platform
    )
    if feedback_notes:
        report.corrections_applied = list(report.corrections_applied) + feedback_notes

    # The feedback loop above changes the audio (loudness makeup, extra glue,
    # side-channel width), so every metric run_qc measured *before* it ran is
    # now stale — including `passed`, which could otherwise claim True while
    # quoting a mono-compatibility value that no longer matches the returned
    # audio. Re-measure all of them against the FINAL signal, reusing the same
    # helpers run_qc itself uses (no new measurement math), and recompute the
    # pass/fail decision via the shared assess_qc_pass() helper.
    report.lufs = integrated_lufs(mastered, sr)
    report.true_peak_db = 20.0 * np.log10(np.max(np.abs(mastered)) + 1e-12)
    report.mono_compatibility = _mono_compatibility(mastered)
    report.bass_phase_shift_deg = measure_bass_phase_shift_deg_abs(mastered, sr)
    _target = resolve_target(analysis.genre.name)
    _bands = spectral_band_energies(mastered, sr)
    report.band_deviations = {name: _bands[name] - _target[name] for name in _target}
    report.passed = assess_qc_pass(
        lufs=report.lufs,
        target_lufs=target_lufs,
        true_peak_db=report.true_peak_db,
        ceiling_db=TRUE_PEAK_CEILING_DB,
        mono_compatibility=report.mono_compatibility,
        bass_phase_shift_deg=report.bass_phase_shift_deg,
        deviations=report.band_deviations,
    )

    on_event({
        "type": "qc_report",
        "lufs": round(report.lufs, 1),
        "true_peak_db": round(report.true_peak_db, 2),
        "mono_compatibility": round(report.mono_compatibility, 2),
        "bass_phase_shift_deg": round(report.bass_phase_shift_deg, 1),
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


def render_master_reference(
    mix_path: str,
    reference_path: str,
    output_path: str,
    on_step: StepCallback = _noop,
    on_beep: BeepCallback = _noop_beep,
) -> None:
    """Alternative mastering strategy: match tonal balance and loudness to a
    user-supplied reference track via matchering, instead of fixed platform
    LUFS targets. `mg.process` is a single opaque blocking call with no
    internal progress hooks, so `on_beep` is fired from a background
    heartbeat thread for the duration of the call -- otherwise this whole
    mastering path (which can take a while on a long track) would run with
    the Neural Monitor completely silent even when it's turned on."""
    import threading
    import matchering as mg

    on_step(f"Mastering per riferimento: adatto il timbro/loudness a '{reference_path}'")

    stop = threading.Event()

    def _heartbeat() -> None:
        while not stop.wait(1.5):
            on_beep()

    beeper = threading.Thread(target=_heartbeat, daemon=True)
    beeper.start()
    try:
        mg.process(
            target=mix_path,
            reference=reference_path,
            results=[mg.pcm24(output_path)],
        )
    finally:
        stop.set()
        beeper.join(timeout=0.1)

    on_step("Mastering per riferimento completato.")
    on_beep()
