"""Regression test for a real-world bug report: instrumental bed sitting far
too quiet relative to the vocal, traced to genuinely-silent stems (broken
FL Studio bounces/placeholder exports) diluting the power-preserving
1/sqrt(N) gain formulas -- a silent stem contributes zero energy but still
counted as "one more real layer" in the denominator, over-attenuating every
actually-audible instrument for nothing.

Confirmed on real material: a 27-stem instrumental session where several
named stems ("Bell reverb", "Horn", "Lead", "Strings", "Trombone", "Upright
Piano (D)") were exported as total silence measured -20.7dB gap between the
vocal and music buses -- much wider than expected from the vocal-prominence
and masking logic alone."""

from __future__ import annotations

import numpy as np

from redline.input_loader import Stems
from redline.analyze import analyze
from redline.wizard import MixPreferences
from redline.bus_exporter import export_buses

SR = 44100


def _tone(freq: float, amp: float, sr: int, seconds: float) -> np.ndarray:
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _stereo(mono: np.ndarray) -> np.ndarray:
    return np.stack([mono, mono], axis=1).astype(np.float32)


def _rms_db(signal: np.ndarray) -> float:
    mono = signal.mean(axis=1) if signal.ndim == 2 else signal
    r = float(np.sqrt(np.mean(mono.astype(np.float64) ** 2))) + 1e-12
    return 20.0 * np.log10(r)


def test_silent_placeholder_stems_do_not_dilute_real_instrument_gain():
    seconds = 2.0
    real_instruments = {
        f"Instrument {i}": _stereo(_tone(200.0 + i * 40.0, 0.2, SR, seconds))
        for i in range(4)
    }
    silence = {
        f"Silent Placeholder {i}": _stereo(np.zeros(int(SR * seconds), dtype=np.float32))
        for i in range(6)
    }

    tracks_without_silence = dict(real_instruments)
    tracks_with_silence = dict(real_instruments)
    tracks_with_silence.update(silence)

    prefs = MixPreferences()

    stems_a = Stems(sample_rate=SR, tracks=tracks_without_silence)
    analysis_a = analyze(stems_a)
    buses_a = export_buses(stems_a, analysis_a, prefs)

    stems_b = Stems(sample_rate=SR, tracks=tracks_with_silence)
    analysis_b = analyze(stems_b)
    buses_b = export_buses(stems_b, analysis_b, prefs)

    # Adding 6 completely silent stems alongside the same 4 real instruments
    # must not measurably change the real instruments' level in the mix --
    # the silent stems carry no signal, so they shouldn't count toward the
    # power-preserving denominator that scales the real ones down.
    level_a = _rms_db(buses_a.music)
    level_b = _rms_db(buses_b.music)
    assert abs(level_a - level_b) < 0.5, (
        f"adding silent placeholder stems changed the real instrumental bed level "
        f"by {abs(level_a - level_b):.1f}dB ({level_a:.1f}dB -> {level_b:.1f}dB) -- "
        f"silent-stem dilution bug is back"
    )
