"""Genre override: a user/preset selection of a genre must actually reach the
engine. Before this, MixPreferences.genre_override was stored/serialized but
never consumed -- the genre was always whatever detect_genre() measured, so a
selection had no effect (the same "computed but never applied" class of bug
the pipeline smoke test guards against)."""

import numpy as np

from redline.input_loader import Stems
from redline.analyze import analyze, apply_genre_override
from redline.genres import GENRE_NAMES
from redline.wizard import MixPreferences
from redline.mixengine import render_mix


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


def test_analyze_applies_genre_override():
    """A known override replaces the measured genre regardless of the audio."""
    stems = _make_synthetic_stems()

    overridden = analyze(stems, genre_override="Hip-Hop")
    assert overridden.genre.name == "Hip-Hop"

    # Case-insensitive canonicalization too.
    assert analyze(stems, genre_override="  hip-hop ").genre.name == "Hip-Hop"

    # None keeps the measured genre (whatever the classifier picked).
    measured = analyze(stems, genre_override=None)
    assert measured.genre.name in GENRE_NAMES


def test_analyze_unknown_override_falls_back():
    """An unknown override must never crash -- it keeps the measured genre."""
    stems = _make_synthetic_stems()

    result = analyze(stems, genre_override="Nonexistent Genre")
    assert result.genre.name in GENRE_NAMES

    # Same for a non-string override.
    result2 = analyze(stems, genre_override=123)  # type: ignore[arg-type]
    assert result2.genre.name in GENRE_NAMES


def test_apply_genre_override_helper():
    """The standalone helper mutates the analysis in place and returns it."""
    stems = _make_synthetic_stems()
    analysis = analyze(stems)

    returned = apply_genre_override(analysis, "Balanced")
    assert returned is analysis
    assert analysis.genre.name == "Balanced"

    # Unknown override leaves the existing genre untouched.
    apply_genre_override(analysis, "Nope")
    assert analysis.genre.name == "Balanced"


def test_render_mix_uses_override():
    """Two renders on the same stems with different overrides must differ --
    proving the override reaches the DSP, not just the analysis object."""
    stems = _make_synthetic_stems()
    prefs = MixPreferences()

    analysis_hiphop = analyze(stems, genre_override="Hip-Hop")
    analysis_acoustic = analyze(stems, genre_override="Acoustic / Classical")

    mixed_hiphop = render_mix(stems, analysis_hiphop, prefs)
    mixed_acoustic = render_mix(stems, analysis_acoustic, prefs)

    assert not np.allclose(mixed_hiphop, mixed_acoustic, atol=1e-4)

    # Determinism: override None vs the measured genre for the same input
    # must stay bit-identical across two runs.
    measured = analyze(stems, genre_override=None)
    run_a = render_mix(stems, measured, prefs)
    run_b = render_mix(stems, measured, prefs)
    assert np.array_equal(run_a, run_b)
