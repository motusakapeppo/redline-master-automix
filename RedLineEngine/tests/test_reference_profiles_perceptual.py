"""Tests for the perceptual (non-spectral) reference targets added to
redline.reference_profiles: crest factor and mono/stereo-width compatibility
targets, used by masterengine.py's iterative feedback loop."""

from __future__ import annotations

from redline.reference_profiles import (
    resolve_perceptual_target,
    CREST_FACTOR_TARGETS,
    MONO_COMPATIBILITY_TARGETS,
)
from redline.analysis.genre import _PROFILES


def test_every_genre_profile_has_a_crest_and_width_target():
    for genre_name in _PROFILES:
        assert genre_name in CREST_FACTOR_TARGETS
        assert genre_name in MONO_COMPATIBILITY_TARGETS


def test_resolve_perceptual_target_returns_all_expected_keys():
    for genre_name in _PROFILES:
        target = resolve_perceptual_target(genre_name)
        assert set(target.keys()) == {"target_lufs", "crest_factor", "mono_compatibility"}
        assert target["crest_factor"] > 0
        assert 0.0 < target["mono_compatibility"] <= 1.0


def test_resolve_perceptual_target_falls_back_for_unknown_genre():
    target = resolve_perceptual_target("Some Made Up Genre")
    assert target["crest_factor"] == CREST_FACTOR_TARGETS["Balanced"]
    assert target["mono_compatibility"] == MONO_COMPATIBILITY_TARGETS["Balanced"]


def test_edm_target_lufs_is_louder_club_target():
    edm = resolve_perceptual_target("EDM / Urban")
    pop = resolve_perceptual_target("Pop / Rock")
    assert edm["target_lufs"] > pop["target_lufs"]  # club (-9) louder than spotify (-14)
