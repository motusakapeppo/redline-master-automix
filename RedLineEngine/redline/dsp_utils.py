"""Small numpy DSP helpers shared by the mix and master engines that pedalboard
doesn't provide out of the box (block-rate envelope following for sidechain
ducking, simple stereo utilities, band-limited processing, mid-side)."""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfiltfilt


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

    env = np.zeros(n_blocks, dtype=np.float64)
    state = 0.0
    for i, v in enumerate(block_rms):
        coef = attack_coef if v > state else release_coef
        state = coef * state + (1.0 - coef) * v
        env[i] = state

    upsampled = np.repeat(env, block)[:n]
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
