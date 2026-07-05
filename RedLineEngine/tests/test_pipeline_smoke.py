"""End-to-end smoke test with synthesized stems (no real audio needed).
Exists to catch "computed but never applied" regressions automatically —
the exact bug found in the old JUCE plugin (genre EQ computed, never wired
into the signal path)."""

import numpy as np

from redline.input_loader import Stems
from redline.analyze import analyze
from redline.wizard import MixPreferences
from redline.mixengine import render_mix
from redline.masterengine import render_master


def _make_synthetic_stems(sr: int = 44100, seconds: float = 3.0) -> Stems:
    n = int(sr * seconds)
    t = np.linspace(0, seconds, n, endpoint=False)

    rng = np.random.default_rng(42)
    vocals = 0.2 * np.sin(2 * np.pi * 440.0 * t)
    bass = 0.3 * np.sin(2 * np.pi * 80.0 * t)
    drums = 0.15 * rng.standard_normal(n)
    other = 0.2 * np.sin(2 * np.pi * 220.0 * t) + 0.05 * rng.standard_normal(n)

    def stereo(mono):
        return np.stack([mono, mono], axis=1).astype(np.float32)

    return Stems(
        sample_rate=sr,
        tracks={
            "vocals": stereo(vocals),
            "bass": stereo(bass),
            "drums": stereo(drums),
            "other": stereo(other),
        },
    )


def test_pipeline_produces_nonzero_changed_output():
    stems = _make_synthetic_stems()
    analysis = analyze(stems)
    prefs = MixPreferences()  # defaults, non-interactive

    mixed = render_mix(stems, analysis, prefs)
    assert mixed.shape[0] == stems.num_samples()
    assert mixed.shape[1] == 2
    assert np.max(np.abs(mixed)) > 0.0

    dry_sum = stems.mixdown()
    # The mix must differ from a naive dry sum — otherwise EQ/compression/
    # ducking silently did nothing, which is exactly the old plugin's bug.
    assert not np.allclose(mixed, dry_sum[: mixed.shape[0]], atol=1e-4)

    events = []
    mastered = render_master(mixed, stems.sample_rate, analysis, on_event=events.append)
    assert mastered.shape == mixed.shape
    peak = np.max(np.abs(mastered))
    assert peak <= 10 ** (-0.9 / 20.0) + 1e-3  # respects the -1dB true-peak ceiling

    # The QC report's stated true peak must match reality (found in practice:
    # it was measured before the final post-QC safety clamp and printed a
    # stale, higher value than what actually ended up in the file).
    qc_events = [e for e in events if e["type"] == "qc_report"]
    assert qc_events, "expected a qc_report event"
    assert qc_events[-1]["true_peak_db"] <= -0.9


def test_analysis_fields_are_populated():
    stems = _make_synthetic_stems()
    analysis = analyze(stems)

    assert analysis.bpm > 0
    assert analysis.key_tonic
    assert analysis.genre.name
    assert 0.0 <= analysis.mix_sub_bass_ratio <= 1.0
    assert set(analysis.stems.keys()) == set(stems.names())
