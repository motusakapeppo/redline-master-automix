"""Regression test for a real-world bug report: drums drifting out of time
relative to the rest of the mix, even though the raw stems were verified
sample-aligned before being fed to the engine.

Root cause: mixengine.py's post-processing re-alignment used to
cross-correlate every non-lead stem (drums, bass, other instruments)
against the *processed lead vocal* to estimate the group delay introduced
by that stem's own DSP chain. Cross-correlating two unrelated instruments
(a drum stem's waveform has no real correlation with a vocal's waveform)
finds whatever spurious peak the noise floor produces in the search
window -- not a real delay -- and applies it as a bogus shift.

Fix: each stem is now re-aligned against its OWN dry/pre-processing
signal (self-referential correlation, always valid since the processed
signal genuinely is a filtered copy of the dry one), never against a
different instrument.

This test drives the actual render_mix DSP chains (not a toy function) with
a drum stem containing sharp transients and a vocal with completely
different, unrelated content, and confirms the drum stem's transient stays
at its original sample position (within the small tolerance expected from a
real IIR chain) regardless of what the vocal is doing."""

from __future__ import annotations

import numpy as np

from redline.input_loader import Stems
from redline.analyze import analyze
from redline.wizard import MixPreferences
from redline.bus_exporter import export_buses

SR = 44100


def _drum_transients(sr: int, seconds: float, hits_sec: list[float]) -> np.ndarray:
    """Sharp percussive hits (short exponential-decay bursts) at known times
    -- like a kick/snare pattern, nothing like a vocal waveform."""
    n = int(sr * seconds)
    signal = np.zeros(n, dtype=np.float32)
    decay_len = int(0.05 * sr)
    envelope = np.exp(-np.linspace(0, 8, decay_len)).astype(np.float32)
    rng = np.random.default_rng(11)
    for hit_sec in hits_sec:
        start = int(hit_sec * sr)
        end = min(start + decay_len, n)
        burst = 0.8 * rng.standard_normal(end - start).astype(np.float32) * envelope[: end - start]
        signal[start:end] += burst
    return signal


def _unrelated_vocal(sr: int, seconds: float) -> np.ndarray:
    """A sustained, slowly-varying tone with nothing timing-related to the
    drum hits -- deliberately uncorrelated content."""
    n = int(sr * seconds)
    t = np.linspace(0, seconds, n, endpoint=False)
    vibrato = 0.5 * np.sin(2 * np.pi * 5.0 * t)
    freq = 220.0 + vibrato * 3.0
    return (0.2 * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def test_drums_stay_aligned_to_their_own_timeline_regardless_of_vocal_content():
    seconds = 3.0
    hit_times = [0.5, 1.0, 1.5, 2.0, 2.5]
    drums_dry = _drum_transients(SR, seconds, hit_times)
    vocal_dry = _unrelated_vocal(SR, seconds)

    def stereo(mono):
        return np.stack([mono, mono], axis=1).astype(np.float32)

    stems = Stems(
        sample_rate=SR,
        tracks={
            "Voce Lead": stereo(vocal_dry),
            "Batteria": stereo(drums_dry),
        },
    )
    analysis = analyze(stems)
    prefs = MixPreferences()

    buses = export_buses(stems, analysis, prefs)
    assert buses.full_mix is not None

    # Find the drums' rendered position by isolating the transient content:
    # process the drum stem alone (no vocal in the session) and compare its
    # transient positions to the drums-plus-vocal case above. If the old bug
    # were present, the drum-plus-vocal render would show a spurious shift
    # relative to the drums-alone render (since the "reference" it wrongly
    # cross-correlated against -- the vocal -- differs between the two
    # runs). With the fix, both should land the transients in essentially
    # the same place, since alignment is now self-referential.
    stems_drums_only = Stems(sample_rate=SR, tracks={"Batteria": stereo(drums_dry)})
    analysis_drums_only = analyze(stems_drums_only)
    buses_drums_only = export_buses(stems_drums_only, analysis_drums_only, prefs)

    mix_with_vocal = buses.full_mix.mean(axis=1)
    mix_drums_only = buses_drums_only.full_mix.mean(axis=1)

    # Locate the first drum hit's peak in each render within a window around
    # its expected dry position.
    def _peak_near(signal: np.ndarray, expected_sec: float, window_sec: float = 0.03) -> int:
        center = int(expected_sec * SR)
        half = int(window_sec * SR)
        lo, hi = max(0, center - half), min(len(signal), center + half)
        segment = np.abs(signal[lo:hi])
        return lo + int(np.argmax(segment))

    for hit_sec in hit_times:
        pos_with_vocal = _peak_near(mix_with_vocal, hit_sec)
        pos_drums_only = _peak_near(mix_drums_only, hit_sec)
        drift_ms = abs(pos_with_vocal - pos_drums_only) / SR * 1000.0
        # The presence of an entirely unrelated vocal stem must not change
        # where the drum transients land. A few ms of difference could come
        # from legitimate per-render processing variance; tens of ms would
        # mean the old cross-instrument correlation bug (or an equivalent
        # regression) is back.
        assert drift_ms < 10.0, (
            f"drum hit at {hit_sec}s landed {drift_ms:.1f}ms apart depending on whether an "
            f"unrelated vocal stem was present -- cross-instrument alignment bug is back"
        )
