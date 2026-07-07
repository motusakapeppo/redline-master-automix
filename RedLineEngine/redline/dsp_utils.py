"""Small numpy DSP helpers shared by the mix and master engines that pedalboard
doesn't provide out of the box (block-rate envelope following for sidechain
ducking, simple stereo utilities, band-limited processing, mid-side)."""

from __future__ import annotations

import logging
import numpy as np
from numba import njit
from scipy.signal import butter, sosfiltfilt


@njit(cache=True)
def _attack_release_recursion(block_rms: np.ndarray, attack_coef: float, release_coef: float) -> np.ndarray:
    """Native-compiled attack/release one-pole recursion. The coefficient
    switches per-sample depending on whether the signal is rising or falling,
    so it can't be expressed as a single linear IIR filter (no lfilter
    shortcut) — numba JIT makes the still-inherently-sequential loop run at
    native speed instead of the ~100x slower pure-Python interpreter loop."""
    n_blocks = block_rms.shape[0]
    env = np.zeros(n_blocks, dtype=np.float64)
    state = 0.0
    for i in range(n_blocks):
        v = block_rms[i]
        coef = attack_coef if v > state else release_coef
        state = coef * state + (1.0 - coef) * v
        env[i] = state
    return env


def envelope_follower(mono: np.ndarray, sr: int, attack_ms: float, release_ms: float, block: int = 512) -> np.ndarray:
    """Block-rate RMS envelope with attack/release smoothing, upsampled back to
    sample rate. Block-based on purpose: a per-sample python loop over a full
    song would be far too slow; music-rate ducking doesn't need per-sample
    resolution anyway."""
    n = mono.shape[0]
    n_blocks = int(np.ceil(n / block))
    padded = np.pad(mono, (0, n_blocks * block - n))
    blocks = padded.reshape(n_blocks, block)
    block_rms = np.sqrt(np.mean(blocks**2, axis=1) + 1e-12)

    block_rate = sr / block
    attack_coef = np.exp(-1.0 / (block_rate * max(attack_ms, 1.0) / 1000.0))
    release_coef = np.exp(-1.0 / (block_rate * max(release_ms, 1.0) / 1000.0))

    env = _attack_release_recursion(block_rms, attack_coef, release_coef)

    # Linear interpolation between block-center values, NOT np.repeat.
    # np.repeat produces a hard staircase -- every `block` (512) samples the
    # gain jumps discontinuously to the next block's value. Multiplying audio
    # by that step function (as every caller here does: de-esser, sidechain
    # ducking, concurrent-take leveling) injects a broadband click at every
    # step edge -- at 512 samples/~11.6ms this is frequent enough to be
    # audible as persistent crackle/zipper noise across a whole render,
    # especially since several of these gain curves stack on the same
    # signal. Interpolating removes the discontinuity entirely.
    block_centers = (np.arange(env.shape[0], dtype=np.float64) + 0.5) * block
    sample_positions = np.arange(n, dtype=np.float64)
    upsampled = np.interp(sample_positions, block_centers, env)
    return upsampled.astype(np.float32)


def duck_gain_curve(key_signal: np.ndarray, sr: int, amount_db: float, attack_ms: float = 15.0, release_ms: float = 200.0) -> np.ndarray:
    """Returns a per-sample linear gain curve (0..1) that dips by up to
    `amount_db` when `key_signal` is present, for ducking a bed under a lead."""
    mono_key = key_signal.mean(axis=1) if key_signal.ndim == 2 else key_signal
    env = envelope_follower(np.abs(mono_key), sr, attack_ms, release_ms)

    reference = np.percentile(env, 95) + 1e-9
    normalized = np.clip(env / reference, 0.0, 1.0)

    reduction_db = -amount_db * normalized
    gain = 10.0 ** (reduction_db / 20.0)
    return gain.astype(np.float32)


def apply_gain_curve(signal: np.ndarray, gain_curve: np.ndarray) -> np.ndarray:
    if signal.ndim == 2:
        return signal * gain_curve[:, None]
    return signal * gain_curve


def db_to_gain(db: float) -> float:
    return float(10.0 ** (db / 20.0))


def split_band(signal: np.ndarray, sr: int, low_hz: float, high_hz: float, order: int = 4) -> tuple[np.ndarray, np.ndarray]:
    """Splits `signal` into (band, rest) via a bandpass filter — `rest` is
    everything outside [low_hz, high_hz], `band` is what's inside. Works
    per-channel automatically. Used for spectral (band-limited) ducking
    instead of ducking the whole signal broadband."""
    nyquist = sr / 2.0
    low_n = max(low_hz / nyquist, 1e-5)
    high_n = min(high_hz / nyquist, 0.999)
    sos = butter(order, [low_n, high_n], btype="bandpass", output="sos")

    if signal.ndim == 1:
        band = sosfiltfilt(sos, signal.astype(np.float64)).astype(np.float32)
        return band, signal - band

    band = np.stack(
        [sosfiltfilt(sos, signal[:, ch].astype(np.float64)) for ch in range(signal.shape[1])],
        axis=1,
    ).astype(np.float32)
    return band, signal - band


def apply_band_gain_curve(signal: np.ndarray, sr: int, low_hz: float, high_hz: float, gain_curve: np.ndarray) -> np.ndarray:
    """Applies a time-varying gain curve to only the [low_hz, high_hz] band
    of `signal`, leaving everything outside that band untouched. This is
    the "spectral ducking" building block: ducking only the vocal-occupied
    band (~1-4kHz) of an instrumental bed avoids the broadband "pumping"
    feeling of ducking the whole signal."""
    band, rest = split_band(signal, sr, low_hz, high_hz)
    return rest + apply_gain_curve(band, gain_curve)


def to_mid_side(signal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Stereo -> (mid, side). mid = (L+R)/2, side = (L-R)/2."""
    left, right = signal[:, 0], signal[:, 1]
    mid = (left + right) * 0.5
    side = (left - right) * 0.5
    return mid.astype(np.float32), side.astype(np.float32)


def from_mid_side(mid: np.ndarray, side: np.ndarray) -> np.ndarray:
    """(mid, side) -> stereo. Inverse of to_mid_side."""
    left = mid + side
    right = mid - side
    return np.stack([left, right], axis=1).astype(np.float32)


def saturate(signal: np.ndarray, drive: float) -> np.ndarray:
    """Gentle tanh harmonic saturation — helps a thin register (high
    harmonies/falsettos) read as present without needing more level, a
    cheap stand-in for "analog warmth" without a third-party plugin."""
    if drive <= 0.0:
        return signal
    driven = np.tanh(signal * (1.0 + drive))
    normalize = np.tanh(1.0 + drive)
    return (driven / normalize).astype(np.float32)


def apply_eq_cut(signal: np.ndarray, sr: int, freq_hz: float, gain_db: float, q: float = 1.0) -> np.ndarray:
    """One-off peak EQ application without building a Pedalboard by hand at
    the call site — used for the ad-hoc corrective cuts (masking, resonance)
    that get computed per-stem rather than assembled into a fixed chain."""
    from pedalboard import Pedalboard, PeakFilter

    board = Pedalboard([PeakFilter(cutoff_frequency_hz=freq_hz, gain_db=gain_db, q=q)])
    return board(signal.T, sr).T


def timed_gain_curve(
    n_samples: int, sr: int, start_sec: float, end_sec: float, gain_db: float, fade_sec: float = 0.15
) -> np.ndarray:
    """Per-sample linear gain curve that is unity (1.0) outside
    [start_sec, end_sec] and db_to_gain(gain_db) inside, with a fade_sec
    crossfade ramp at both edges -- the building block for "only apply
    this EQ/gain change during the chorus" without an audible click at
    the section boundary. Built via np.interp over a handful of control
    points rather than a per-sample loop, so it stays fast on full songs."""
    target = db_to_gain(gain_db)
    start_s = start_sec * sr
    end_s = end_sec * sr
    fade_s = max(fade_sec * sr, 1.0)

    control_x = np.array(
        [0.0, max(0.0, start_s - fade_s), start_s, end_s, min(float(n_samples), end_s + fade_s), float(n_samples)],
        dtype=np.float64,
    )
    control_y = np.array([1.0, 1.0, target, target, 1.0, 1.0], dtype=np.float64)
    order = np.argsort(control_x, kind="stable")
    control_x, control_y = control_x[order], control_y[order]

    x = np.arange(n_samples, dtype=np.float64)
    return np.interp(x, control_x, control_y).astype(np.float32)


def pan_stereo(signal: np.ndarray, pan: float) -> np.ndarray:
    """Constant-power pan. `pan` is -1 (hard left) .. +1 (hard right), 0 = center.
    Used for vocal doubles/harmonies named e.g. '... dx.wav' / '... sx.wav',
    which are meant to sit hard-panned rather than centered like the lead."""
    mono = signal.mean(axis=1) if signal.ndim == 2 else signal
    pan = float(np.clip(pan, -1.0, 1.0))
    angle = (pan + 1.0) * (np.pi / 4.0)  # 0 -> hard left, pi/2 -> hard right
    left_gain = np.cos(angle)
    right_gain = np.sin(angle)
    return np.stack([mono * left_gain, mono * right_gain], axis=1).astype(np.float32)


def stereo_widen(audio: np.ndarray, sr: int, width: float = 0.3, mono_crossover_hz: float = 120.0) -> np.ndarray:
    """Mid/Side stereo widening. `width` 0=mono, 1=original, >1=wider.
    Frequencies below mono_crossover_hz stay mono to preserve bass compatibility.
    Uses to_mid_side/from_mid_side already in this module.
    Guard: if audio is mono (1D or 2D with 1 channel), return unchanged."""
    if audio.ndim == 1 or (audio.ndim == 2 and audio.shape[1] == 1):
        return audio
    if audio.ndim != 2 or audio.shape[1] != 2:
        return audio  # not stereo, return unchanged

    width = float(width)
    if width <= 0.0:
        # Sum to mono
        mono = audio.mean(axis=1, keepdims=True)
        return np.repeat(mono, 2, axis=1).astype(np.float32)

    mid, side = to_mid_side(audio)

    # Apply width to side signal
    widened_side = side * width

    # Frequencies below mono_crossover_hz stay mono: zero the side content
    # in that range by high-pass filtering the widened side
    nyquist = sr / 2.0
    if mono_crossover_hz > 0.0 and mono_crossover_hz < nyquist:
        from scipy.signal import butter, sosfiltfilt

        # High-pass the widened side at the crossover frequency
        sos = butter(4, mono_crossover_hz / nyquist, btype="highpass", output="sos")
        side_high = sosfiltfilt(sos, widened_side.astype(np.float64)).astype(np.float32)
        # Low frequencies keep the original (unwidened) side content
        sos_low = butter(4, mono_crossover_hz / nyquist, btype="lowpass", output="sos")
        side_low_orig = sosfiltfilt(sos_low, side.astype(np.float64)).astype(np.float32)
        widened_side = side_high + side_low_orig

    return from_mid_side(mid, widened_side)


def transient_shaper(audio: np.ndarray, sr: int, attack_gain_db: float = 3.0, sustain_gain_db: float = -2.0, attack_time_ms: float = 5.0) -> np.ndarray:
    """Envelope follower separates attack from sustain.
    `attack_gain_db` boosts the transient, `sustain_gain_db` reduces the tail.
    `attack_time_ms` sets the split point between attack and sustain.
    Uses envelope_follower already in this module.
    Guard: clamp gain to ±12dB."""
    attack_gain_db = float(np.clip(attack_gain_db, -12.0, 12.0))
    sustain_gain_db = float(np.clip(sustain_gain_db, -12.0, 12.0))
    attack_time_ms = float(max(attack_time_ms, 0.5))

    # Work on summed mono for envelope detection
    if audio.ndim == 2:
        mono = audio.mean(axis=1)
    else:
        mono = audio

    # Two envelopes: a fast one that catches the transient peak, and a slow
    # one that tracks the body/sustain. The ratio between them determines
    # how much of each sample is "attack" vs "sustain".
    fast_env = envelope_follower(np.abs(mono), sr, attack_ms=attack_time_ms * 0.3, release_ms=attack_time_ms * 2.0)
    slow_env = envelope_follower(np.abs(mono), sr, attack_ms=attack_time_ms * 3.0, release_ms=attack_time_ms * 6.0)

    # Ensure same length (envelope_follower returns same-length signal)
    n = mono.shape[0]
    if fast_env.shape[0] != n:
        fast_env = np.interp(np.arange(n, dtype=np.float64),
                             np.linspace(0, n, fast_env.shape[0], dtype=np.float64),
                             fast_env.astype(np.float64)).astype(np.float32)
    if slow_env.shape[0] != n:
        slow_env = np.interp(np.arange(n, dtype=np.float64),
                             np.linspace(0, n, slow_env.shape[0], dtype=np.float64),
                             slow_env.astype(np.float64)).astype(np.float32)

    # Transient blend: where fast exceeds slow, we're in the attack phase.
    # The ratio fast/slow gives a continuous blend 0..1+ for attack vs sustain.
    slow_env = np.maximum(slow_env, 1e-12)
    transient_ratio = np.clip(fast_env / slow_env - 1.0, 0.0, 1.0)

    # Convert gains to linear
    attack_gain_linear = db_to_gain(attack_gain_db)
    sustain_gain_linear = db_to_gain(sustain_gain_db)

    # Blend gain: at peak transient (ratio=1) use attack_gain, at sustain (ratio=0) use sustain_gain
    gain_curve = (1.0 - transient_ratio) * sustain_gain_linear + transient_ratio * attack_gain_linear

    # Smooth the gain curve to avoid clicks (~1ms moving average)
    smooth_samples = max(1, int(sr * 0.001))
    kernel = np.ones(smooth_samples, dtype=np.float32) / smooth_samples
    gain_curve = np.convolve(gain_curve, kernel, mode="same").astype(np.float32)

    if audio.ndim == 2:
        return (audio * gain_curve[:, None]).astype(np.float32)
    return (audio * gain_curve).astype(np.float32)


def loudness_match(audio: np.ndarray, target_lufs: float = -16.0) -> np.ndarray:
    """Normalizza l'audio al target LUFS specificato usando pyloudnorm.

    Se pyloudnorm non è disponibile, ritorna l'audio invariato con un warning
    loggato. Se l'audio è silenzioso (RMS < 0.001), ritorna l'audio invariato.
    Il gain applicato è clampato a ±12dB per sicurezza.

    Parameters
    ----------
    audio : np.ndarray
        Segnale mono (1D) o stereo (2D, shape [n_samples, n_channels]).
    target_lufs : float
        LUFS target di normalizzazione (default -16.0, standard Apple Music).

    Returns
    -------
    np.ndarray
        Audio normalizzato (stesso dtype dell'input).
    """
    log = logging.getLogger(__name__)

    # Silent audio guard
    rms = np.sqrt(np.mean(audio**2))
    if rms < 0.001:
        log.warning("loudness_match: audio silenzioso (RMS=%.6f), ritorno invariato", rms)
        return audio

    try:
        import pyloudnorm as pyln
    except ImportError:
        log.warning("loudness_match: pyloudnorm non installato, ritorno audio invariato")
        return audio

    # pyloudnorm expects (n_samples, n_channels) — 1D arrays need reshaping
    if audio.ndim == 1:
        data = audio[:, np.newaxis]
    else:
        data = audio

    # Measure integrated LUFS. pyloudnorm's Meter uses the rate for gating
    # block duration; 48000 Hz is a safe default — the measurement error from
    # using 48000 for a 44100 signal is <0.1 LUFS.
    meter = pyln.Meter(48000.0)  # rate in Hz
    measured_lufs = meter.integrated_loudness(data)

    # Compute gain, clamp to ±12 dB
    gain_db = target_lufs - measured_lufs
    gain_db = float(np.clip(gain_db, -12.0, 12.0))
    gain_linear = 10.0 ** (gain_db / 20.0)

    result = audio * gain_linear

    log.debug(
        "loudness_match: %.2f LUFS -> %.2f LUFS (gain %.2f dB)",
        measured_lufs, target_lufs, gain_db,
    )
    return result.astype(audio.dtype)
