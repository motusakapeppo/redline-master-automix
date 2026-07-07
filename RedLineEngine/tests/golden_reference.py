"""Three synthetic reference songs with known, reproducible properties.
Not a historical golden-master comparison (the pipeline evolves too fast for
that to be useful yet) -- these check structural invariants that must hold
regardless of DSP tuning changes: the sweep survives, the impulse survives,
the noise floor has energy everywhere. GOLDEN_TOLERANCE_DB is reserved for
future sample-accurate regression comparisons once the DSP chain stabilizes."""

from __future__ import annotations

import numpy as np

GOLDEN_TOLERANCE_DB = -96.0


def _db(value: float) -> float:
    if value <= 0.0:
        return float("-inf")
    return 20.0 * np.log10(value)


def generate_golden(name: str, sr: int = 44100) -> tuple[np.ndarray, int]:
    if name == "sine_sweep":
        duration = 5.0
        n = int(sr * duration)
        t = np.linspace(0, duration, n, endpoint=False)
        f0, f1 = 20.0, 20000.0
        # Exponential (logarithmic) sweep.
        k = (f1 / f0) ** (1.0 / duration)
        phase = 2 * np.pi * f0 * (k ** t - 1.0) / np.log(k)
        mono = (0.5 * np.sin(phase)).astype(np.float32)
        audio = np.stack([mono, mono], axis=1)
        return audio, sr

    if name == "silence_impulse":
        n = int(sr * 2.0) + 1
        audio = np.zeros((n, 2), dtype=np.float32)
        audio[n // 2, :] = 1.0
        return audio, sr

    if name == "white_noise":
        duration = 3.0
        n = int(sr * duration)
        rng = np.random.default_rng(12345)
        audio = (0.3 * rng.standard_normal((n, 2))).astype(np.float32)
        return audio, sr

    raise ValueError(f"Unknown golden reference: {name}")


def assert_golden_match(name: str, actual: np.ndarray, sr: int) -> None:
    """Compares `actual` against a freshly regenerated golden of the same
    name using RMS difference in dB. Only meaningful when `actual` was
    derived from an unmodified copy of the golden itself (e.g. two render
    passes of the same input) -- it is not a fixed historical baseline."""
    expected, _ = generate_golden(name, sr)
    n = min(len(expected), len(actual))
    diff = actual[:n].astype(np.float64) - expected[:n].astype(np.float64)
    rms_diff = float(np.sqrt(np.mean(diff ** 2))) if n > 0 else 0.0
    diff_db = _db(rms_diff)
    assert diff_db < GOLDEN_TOLERANCE_DB, (
        f"Golden '{name}' RMS diff {diff_db:.1f}dB exceeds tolerance {GOLDEN_TOLERANCE_DB}dB"
    )
