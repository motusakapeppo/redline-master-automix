"""Regression test: the "other"-role music bus must not get louder just
because more instrumental layers feed it. Found via a real session with
15+ instrumental stems ("Intro - Stems Instrumental") where music_bus summed
every "other" stem completely unweighted -- whichever stems had the most
natural energy dominated the pile while quieter texture layers got buried,
heard as "the instrumental is unbalanced"."""

import numpy as np

from redline.input_loader import Stems
from redline.analyze import analyze
from redline.wizard import MixPreferences
from redline.bus_exporter import export_buses


def _make_stems(n_instruments: int, sr=44100, seconds=5.0):
    n = int(sr * seconds)
    t = np.linspace(0, seconds, n, endpoint=False)

    def stereo(m):
        return np.stack([m, m], axis=1).astype(np.float32)

    tracks = {"vocal_main": stereo((0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32))}
    for i in range(n_instruments):
        freq = 220.0 + i * 110.0
        tracks[f"instrument_{i}"] = stereo((0.15 * np.sin(2 * np.pi * freq * t)).astype(np.float32))
    return Stems(sample_rate=sr, tracks=tracks)


def _music_bus_rms_db(n_instruments: int) -> float:
    stems = _make_stems(n_instruments)
    analysis = analyze(stems)
    buses = export_buses(stems, analysis, MixPreferences())
    rms = float(np.sqrt(np.mean(buses.music.astype(np.float64) ** 2)))
    return 20.0 * np.log10(rms + 1e-12)


def test_music_bus_rms_stable_regardless_of_instrument_count():
    rms_few = _music_bus_rms_db(2)
    rms_many = _music_bus_rms_db(12)
    # Before the power-preserving scale, 12 unweighted instruments summed to
    # roughly sqrt(12/2) ~= 2.45x (+7.8dB) louder than 2. After the fix,
    # both should land within a couple dB of each other.
    assert abs(rms_many - rms_few) < 3.0, f"music bus RMS grew with instrument count: {rms_few:.1f}dB (2 instr) vs {rms_many:.1f}dB (12 instr)"
