"""Calibration test for the timing-drift fix (README issue #8): confirms the
post-processing re-alignment actually holds for vocal *doubles*, not just
solo stems.

Root cause recap: elastic_align/alignment.py DTW-aligns a double to the
*dry* lead before mixengine.py's per-stem DSP chains run. Those chains
(HPF/EQ/compressor, register-specific for doubles via _process_double_stem)
introduce their own IIR group delay, which differs from the lead's own
chain, so the double can drift back out of alignment with the lead *after*
processing. mixengine.py already had a post-align fix for solo stems
(non-double); this test targets the previously-uncovered double-stem path
that was fixed alongside it.

Uses a real broadband transient (not a single-sample click) run through the
actual per-stem DSP chains via render_mix, so this measures genuine IIR
group delay, not just a resample/padding artifact."""

from __future__ import annotations

import numpy as np
from scipy.signal import correlate

from redline.input_loader import Stems
from redline.analyze import analyze
from redline.wizard import MixPreferences
from redline.mixengine import render_mix
from redline.bus_exporter import export_buses


SR = 44100


def _transient_click_train(sr: int, seconds: float, click_sec: float) -> np.ndarray:
    """A short broadband burst (bandlimited noise pulse), not a single-sample
    impulse -- gives IIR filters something with real frequency content to
    delay, closer to a real vocal consonant/transient than a Dirac impulse."""
    n = int(sr * seconds)
    signal = np.zeros(n, dtype=np.float32)
    rng = np.random.default_rng(3)
    click_len = int(0.01 * sr)  # 10ms burst
    start = int(click_sec * sr)
    signal[start:start + click_len] = 0.6 * rng.standard_normal(click_len).astype(np.float32)
    return signal


def _cross_corr_lag(a: np.ndarray, b: np.ndarray, max_lag: int) -> int:
    corr = correlate(a, b, mode="full")
    center = len(b) - 1
    lo, hi = center - max_lag, center + max_lag + 1
    window = corr[lo:hi]
    return int(np.argmax(window)) - max_lag


def test_double_stays_aligned_with_lead_after_processing():
    seconds = 2.0
    click_sec = 1.0
    burst = _transient_click_train(SR, seconds, click_sec)

    def stereo(mono):
        return np.stack([mono, mono], axis=1).astype(np.float32)

    # Sustained tone underneath the burst so pYIN/register classification and
    # the per-stem DSP chains have real signal to work with, not silence.
    t = np.linspace(0, seconds, int(SR * seconds), endpoint=False)
    lead_tone = (0.15 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32) + burst
    double_tone = (0.15 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32) + burst

    stems = Stems(
        sample_rate=SR,
        tracks={
            "Voce Lead": stereo(lead_tone),
            "Voce Double": stereo(double_tone),
        },
    )
    analysis = analyze(stems)
    prefs = MixPreferences()

    buses = export_buses(stems, analysis, prefs)
    assert buses.vocal_main is not None
    assert buses.vocal_doubles is not None

    lead_mono = buses.vocal_main.mean(axis=1)
    double_mono = buses.vocal_doubles.mean(axis=1)

    max_lag = int(0.05 * SR)  # search +/-50ms
    lag = _cross_corr_lag(lead_mono, double_mono, max_lag)

    # The double bus is scaled to 50% and independently processed (different
    # register recipe, different IIR chain than the lead) -- some residual
    # is plausible, but genuine drift (tens of ms) would be audible timing
    # slop. 5ms is a generous tolerance well below the ~10-20ms threshold
    # where comb-filtering/slap-back becomes perceptible.
    residual_ms = abs(lag) / SR * 1000.0
    assert residual_ms < 5.0, f"double drifted {residual_ms:.1f}ms out of alignment with the lead after processing"
