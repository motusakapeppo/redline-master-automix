"""Tape-style feedback delay: a low-pass filter sits *inside* the feedback
loop so each successive repeat is progressively darker, not just the first
one. `pedalboard.Delay` has native feedback but no way to place a filter
inside that loop -- a `Pedalboard([LowpassFilter(), Delay()])` chain only
filters the signal once on the way in, so every repeat comes back equally
bright. `fxsends.vocal_send()` already covers the simple pre-filtered slap
delay case; this module is complementary, not a replacement.

Implementation: each repeat is generated as an independent cascade -- repeat
k is the input filtered through a one-pole low-pass k times, scaled by
feedback**k, and placed at offset k*delay_samples. Applying the same one-pole
filter k times in cascade is exactly equivalent to running the input through
a circular buffer with a one-pole filter re-applied on every loop iteration
(both are the same IIR system evaluated k times), and is far cheaper than a
literal sample-by-sample Python loop.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import lfilter

_MAX_REPEATS = 12
_MIN_FEEDBACK_TO_CONTINUE = 1e-4


@dataclass
class FeedbackDelayParams:
    delay_ms: float = 300.0
    feedback: float = 0.4       # 0.0 - 0.95
    lowpass_hz: float = 5000.0  # filter INSIDE the feedback loop (recursive darkening)
    mix: float = 0.3            # 0.0 - 1.0
    ping_pong: bool = False


def _one_pole_lowpass(signal: np.ndarray, sr: int, cutoff_hz: float) -> np.ndarray:
    alpha = float(np.exp(-2.0 * np.pi * cutoff_hz / sr))
    b = [1.0 - alpha]
    a = [1.0, -alpha]
    return lfilter(b, a, signal, axis=0).astype(np.float32)


def feedback_delay(audio: np.ndarray, sr: int, params: FeedbackDelayParams | None = None) -> np.ndarray:
    params = params or FeedbackDelayParams()
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 1:
        audio = audio[:, None]

    if params.mix <= 0.0:
        return audio

    delay_samples = max(int(params.delay_ms / 1000.0 * sr), 1)
    feedback = float(np.clip(params.feedback, 0.0, 0.95))

    n_repeats = 1
    if feedback > _MIN_FEEDBACK_TO_CONTINUE:
        # How many repeats until the feedback gain decays below -60dB.
        n_repeats = min(_MAX_REPEATS, int(np.log(1e-3) / np.log(feedback)) + 1) if feedback < 1.0 else _MAX_REPEATS
        n_repeats = max(n_repeats, 1)

    n_samples, n_channels = audio.shape
    out_len = n_samples + delay_samples * n_repeats
    wet = np.zeros((out_len, n_channels), dtype=np.float32)

    filtered_stage = audio
    for k in range(1, n_repeats + 1):
        filtered_stage = _one_pole_lowpass(filtered_stage, sr, params.lowpass_hz)
        repeat = filtered_stage * (feedback ** k)
        offset = delay_samples * k

        if params.ping_pong and n_channels == 2:
            repeat = repeat[:, ::-1] if k % 2 == 1 else repeat

        wet[offset:offset + n_samples] += repeat

    wet = wet[:out_len]
    dry_padded = np.zeros((out_len, n_channels), dtype=np.float32)
    dry_padded[:n_samples] = audio

    mix = float(np.clip(params.mix, 0.0, 1.0))
    return (dry_padded * (1.0 - mix) + wet * mix).astype(np.float32)
