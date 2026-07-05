"""Small numpy DSP helpers shared by the mix and master engines that pedalboard
doesn't provide out of the box (block-rate envelope following for sidechain
ducking, simple stereo utilities)."""

from __future__ import annotations

import numpy as np


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
