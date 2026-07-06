"""First-stage transparent noise reduction for vocal stems: mic hiss, room
tone, headphone bleed etc. compound badly once you sum and compress dozens
of doubles together. This has to run before anything else in the per-stem
chain — compressing first raises the noise floor along with the signal, and
EQing first changes the noise's spectral color enough that a noise-profile
estimator can no longer recognize it as the same noise.

Deliberately conservative: too much reduction produces the classic
"underwater"/robotic spectral-gating artifacts. Default targets roughly the
same modest amount a clean hardware/VST denoiser would use (~6dB), not a
gate.
"""

from __future__ import annotations

import numpy as np
import noisereduce as nr

DEFAULT_REDUCTION_DB = 6.0
_REDUCTION_TO_PROP_DECREASE_DIVISOR = 12.0  # keeps the default modest, not a gate


def denoise(signal: np.ndarray, sr: int, reduction_db: float = DEFAULT_REDUCTION_DB) -> np.ndarray:
    """Stationary spectral-gating noise reduction, applied per channel.
    `reduction_db` is a friendly knob (not a literal calibrated dB figure —
    noisereduce's own parameter is a 0..1 proportion) capped so the effect
    stays transparent rather than gating."""
    if reduction_db <= 0.0:
        return signal

    prop_decrease = float(np.clip(reduction_db / _REDUCTION_TO_PROP_DECREASE_DIVISOR, 0.0, 1.0))

    if signal.ndim == 1:
        return nr.reduce_noise(y=signal, sr=sr, stationary=True, prop_decrease=prop_decrease).astype(np.float32)

    return np.stack(
        [
            nr.reduce_noise(y=signal[:, ch], sr=sr, stationary=True, prop_decrease=prop_decrease)
            for ch in range(signal.shape[1])
        ],
        axis=1,
    ).astype(np.float32)
