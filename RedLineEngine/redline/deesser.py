"""Band-split de-esser for vocal stems: reduces sibilance (~5-9kHz) without
touching the rest of the signal. This is deliberately not just "another
compressor on the whole vocal" — it isolates the sibilant band via a
bandpass filter, gain-reduces only that band, then recombines it with the
untouched complementary signal."""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfiltfilt

from .dsp_utils import envelope_follower

SIBILANCE_LOW_HZ = 5000.0
SIBILANCE_HIGH_HZ = 9000.0


def _deess_channel(
    channel: np.ndarray,
    sr: int,
    threshold_db: float,
    max_reduction_db: float,
    attack_ms: float,
    release_ms: float,
) -> np.ndarray:
    nyquist = sr / 2.0
    sos = butter(
        4,
        [SIBILANCE_LOW_HZ / nyquist, min(SIBILANCE_HIGH_HZ / nyquist, 0.999)],
        btype="bandpass",
        output="sos",
    )
    sibilant = sosfiltfilt(sos, channel.astype(np.float64)).astype(np.float32)
    rest = channel - sibilant  # everything outside the sibilance band, untouched

    env = envelope_follower(np.abs(sibilant), sr, attack_ms, release_ms)
    threshold_lin = max(10.0 ** (threshold_db / 20.0), 1e-9)
    excess_db = 20.0 * np.log10(np.maximum(env, 1e-9) / threshold_lin)
    reduction_db = np.clip(excess_db, 0.0, max_reduction_db)
    gain = (10.0 ** (-reduction_db / 20.0)).astype(np.float32)

    return rest + sibilant * gain


def deess(
    signal: np.ndarray,
    sr: int,
    threshold_db: float = -30.0,
    max_reduction_db: float = 9.0,
    attack_ms: float = 2.0,
    release_ms: float = 60.0,
) -> np.ndarray:
    if signal.ndim == 1:
        return _deess_channel(signal, sr, threshold_db, max_reduction_db, attack_ms, release_ms)
    return np.stack(
        [
            _deess_channel(signal[:, ch], sr, threshold_db, max_reduction_db, attack_ms, release_ms)
            for ch in range(signal.shape[1])
        ],
        axis=1,
    )
