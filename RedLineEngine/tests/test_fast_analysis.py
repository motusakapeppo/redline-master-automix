"""Flag-gated fast analysis path (ENABLE_FAST_ANALYSIS).

Contract:
  * flag OFF  -> byte-identical numeric outputs to the pre-feature behavior
                 (pinned against captured baselines below).
  * flag ON   -> cheaper BPM/pitch approximations, within musical tolerance,
                 and measurably faster on a longer signal.

The OFF baselines are captured from the code as merged; regenerate only with a
deliberate, reviewed behavior change.
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from redline import config
from redline.analysis.bpm import detect_bpm
from redline.analysis.pitch import estimate_fundamental
from redline.input_loader import Stems
from redline.analyze import analyze


# --------------------------------------------------------------------------
# Fixed signals
# --------------------------------------------------------------------------

def _click_track(bpm: float = 120.0, sr: int = 22050, seconds: float = 8.0):
    n = int(sr * seconds)
    sig = np.zeros(n, dtype=np.float32)
    interval = int(sr * 60.0 / bpm)
    for i in range(0, n, interval):
        sig[i:i + 64] += 0.9
    return sig, sr


def _tone(freq: float = 150.0, sr: int = 22050, seconds: float = 6.0, seed: int = 3):
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    rng = np.random.default_rng(seed)
    sig = (0.3 * np.sin(2 * np.pi * freq * t) + 0.01 * rng.standard_normal(t.size)).astype(np.float32)
    return sig, sr


def _long_tone(sr: int = 22050, seconds: float = 8.0, seed: int = 5):
    n = int(sr * seconds)
    t = np.linspace(0, seconds, n, endpoint=False)
    rng = np.random.default_rng(seed)
    sig = (
        0.3 * np.sin(2 * np.pi * 150 * t)
        + 0.15 * np.sin(2 * np.pi * 300 * t)
        + 0.05 * rng.standard_normal(n)
    ).astype(np.float32)
    return sig, sr


def _stems(sr: int = 44100, seconds: float = 2.0) -> Stems:
    n = int(sr * seconds)
    t = np.linspace(0, seconds, n, endpoint=False)
    rng = np.random.default_rng(7)
    vocals = 0.2 * np.sin(2 * np.pi * 440.0 * t) + 0.05 * rng.standard_normal(n)
    bass = 0.3 * np.sin(2 * np.pi * 80.0 * t)
    drums = 0.15 * rng.standard_normal(n)
    other = 0.2 * np.sin(2 * np.pi * 220.0 * t)

    def st(m):
        return np.stack([m, m], axis=1).astype(np.float32)

    return Stems(sample_rate=sr, tracks={
        "vocals": st(vocals), "bass": st(bass), "drums": st(drums), "other": st(other),
    })


# --------------------------------------------------------------------------
# Captured OFF baselines (flag OFF)
# --------------------------------------------------------------------------

_BPM_BASELINE = 117.45383522727273
_F0_BASELINE = 150.2644282429835

_ANALYZE_BASELINE = {
    "bpm": 92.28515625,
    "key_tonic": "A",
    "key_mode": "major",
    "key_confidence": 0.7853630538541239,
    "genre": "EDM / Urban",
    "mix_lufs": -6.602611093692435,
    "mix_crest": 3.3933568000793457,
    "mix_sub_bass_ratio": 0.49131699656194905,
    "transient_density": 4.5,
    "stems": {
        "vocals": 2.744210720062256,
        "bass": 1.4142131805419922,
        "drums": 4.530557632446289,
        "other": 1.4142130613327026,
    },
}


@pytest.fixture(autouse=True)
def _reset_flag():
    config.set_override("ENABLE_FAST_ANALYSIS", False)
    yield
    config.set_override("ENABLE_FAST_ANALYSIS", False)


# --------------------------------------------------------------------------
# OFF: bit-identical
# --------------------------------------------------------------------------

def test_bpm_off_matches_baseline_exactly():
    config.set_override("ENABLE_FAST_ANALYSIS", False)
    sig, sr = _click_track()
    assert detect_bpm(sig, sr) == _BPM_BASELINE


def test_f0_off_matches_baseline_exactly():
    config.set_override("ENABLE_FAST_ANALYSIS", False)
    sig, sr = _tone()
    assert estimate_fundamental(sig, sr) == _F0_BASELINE


def test_analyze_off_fields_identical():
    config.set_override("ENABLE_FAST_ANALYSIS", False)
    a = analyze(_stems())
    assert a.bpm == _ANALYZE_BASELINE["bpm"]
    assert a.key_tonic == _ANALYZE_BASELINE["key_tonic"]
    assert a.key_mode == _ANALYZE_BASELINE["key_mode"]
    assert a.key_confidence == _ANALYZE_BASELINE["key_confidence"]
    assert a.genre.name == _ANALYZE_BASELINE["genre"]
    assert a.mix_lufs == _ANALYZE_BASELINE["mix_lufs"]
    assert a.mix_crest == _ANALYZE_BASELINE["mix_crest"]
    assert a.mix_sub_bass_ratio == _ANALYZE_BASELINE["mix_sub_bass_ratio"]
    assert a.transient_density == _ANALYZE_BASELINE["transient_density"]
    assert {k: v.crest for k, v in a.stems.items()} == _ANALYZE_BASELINE["stems"]


# --------------------------------------------------------------------------
# ON: within musical tolerance
# --------------------------------------------------------------------------

def test_bpm_on_within_tolerance():
    config.set_override("ENABLE_FAST_ANALYSIS", True)
    sig, sr = _click_track()
    assert abs(detect_bpm(sig, sr) - _BPM_BASELINE) <= 2.0


def test_f0_on_within_semitone():
    config.set_override("ENABLE_FAST_ANALYSIS", True)
    sig, sr = _tone()
    f0 = estimate_fundamental(sig, sr)
    assert abs(f0 / _F0_BASELINE - 1.0) <= (2 ** (1 / 12) - 1.0)


def test_analyze_on_bpm_within_tolerance_other_fields_identical():
    config.set_override("ENABLE_FAST_ANALYSIS", True)
    a = analyze(_stems())
    assert abs(a.bpm - _ANALYZE_BASELINE["bpm"]) <= 2.0
    # The fast path only touches BPM; every other field must be untouched.
    assert a.key_tonic == _ANALYZE_BASELINE["key_tonic"]
    assert a.key_mode == _ANALYZE_BASELINE["key_mode"]
    assert a.key_confidence == _ANALYZE_BASELINE["key_confidence"]
    assert a.genre.name == _ANALYZE_BASELINE["genre"]
    assert a.mix_lufs == _ANALYZE_BASELINE["mix_lufs"]
    assert a.mix_crest == _ANALYZE_BASELINE["mix_crest"]
    assert a.mix_sub_bass_ratio == _ANALYZE_BASELINE["mix_sub_bass_ratio"]
    assert a.transient_density == _ANALYZE_BASELINE["transient_density"]
    assert {k: v.crest for k, v in a.stems.items()} == _ANALYZE_BASELINE["stems"]


# --------------------------------------------------------------------------
# ON: measurably faster on a longer signal
# --------------------------------------------------------------------------

def _best_time(fn, reps: int = 2) -> float:
    best = float("inf")
    for _ in range(reps):
        start = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - start)
    return best


def test_fast_pitch_is_measurably_faster():
    sig, sr = _long_tone()

    config.set_override("ENABLE_FAST_ANALYSIS", False)
    off_time = _best_time(lambda: estimate_fundamental(sig, sr))

    config.set_override("ENABLE_FAST_ANALYSIS", True)
    on_time = _best_time(lambda: estimate_fundamental(sig, sr))

    assert on_time < off_time * 0.5, f"fast path not faster: on={on_time:.3f}s off={off_time:.3f}s"
