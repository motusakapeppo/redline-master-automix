"""Validates classify_instrument()'s filename-hint detection against real
stem names from real FL Studio sessions (BAGDAD, INTRO REC), the same way
test_naming.py validates naming.py against a real project's file names."""

import numpy as np

from redline.instrumentstack import (
    classify_instrument, genre_bias,
    STRINGS, BRASS, WOODWINDS, KEYS, ORGAN, CHOIR, SYNTH_PAD, SYNTH_LEAD, BELL, PLUCK, VOCAL_CHOP, FX,
    GENERIC,
    ACCORDION, HARPSICHORD, FOLK_PLUCK, WORLD_STRINGS, WORLD_WINDS,
)


def _dummy_audio(n=4410, sr=44100):
    return (0.1 * np.random.default_rng(0).standard_normal(n)).astype(np.float32)


def test_horn_and_trombone_are_brass():
    assert classify_instrument("Horn", _dummy_audio(), 44100) == BRASS
    assert classify_instrument("Trombone", _dummy_audio(), 44100) == BRASS


def test_bells_are_recognized_not_left_to_spectral_guessing():
    # "Bell 1", "Bell reverb", "Church bell" -- all real stem names with no
    # prior category at all, previously falling through to the spectral
    # fallback instead of a dedicated recipe. BELL is now its own category
    # (split from STRINGS) since a bell's sharp metallic attack + shimmer
    # decay wants a different recipe than a bowed string's slow swell.
    assert classify_instrument("Bell 1", _dummy_audio(), 44100) == BELL
    assert classify_instrument("Bell reverb", _dummy_audio(), 44100) == BELL
    assert classify_instrument("Church bell", _dummy_audio(), 44100) == BELL


def test_pianos_are_keys():
    assert classify_instrument("Grand Piano", _dummy_audio(), 44100) == KEYS
    assert classify_instrument("Upright Piano (D)", _dummy_audio(), 44100) == KEYS


def test_choir_is_choir():
    assert classify_instrument("Choir", _dummy_audio(), 44100) == CHOIR


def test_atmosphere_is_synth_pad():
    assert classify_instrument("Atmosphere 1", _dummy_audio(), 44100) == SYNTH_PAD


def test_arp_is_pluck():
    # PLUCK is now its own category (split from SYNTH_LEAD) -- arps/plucks/
    # stabs are rhythmic ear-candy that wants a fast, dry, articulate
    # treatment, distinct from a sustained lead line meant to hold and cut
    # through.
    assert classify_instrument("Arp 1 bright", _dummy_audio(), 44100) == PLUCK


def test_flute_and_oboe_are_woodwinds_not_brass():
    # Split from BRASS -- flute/oboe/clarinet are breathy/airy, not
    # honk-and-bite like trumpet/sax/trombone.
    assert classify_instrument("Flute 1", _dummy_audio(), 44100) == WOODWINDS
    assert classify_instrument("Oboe solo", _dummy_audio(), 44100) == WOODWINDS
    assert classify_instrument("Fiati legni", _dummy_audio(), 44100) == WOODWINDS


def test_harp_is_strings_not_pluck():
    # "harp" contains the substring "arp" (PLUCK's own hint) -- must resolve
    # to STRINGS, not fall through to a false PLUCK match.
    assert classify_instrument("Harp glissando", _dummy_audio(), 44100) == STRINGS
    assert classify_instrument("Arpa", _dummy_audio(), 44100) == STRINGS


def test_vocal_chop_and_fx_are_recognized():
    assert classify_instrument("Vox Chop 3", _dummy_audio(), 44100) == VOCAL_CHOP
    assert classify_instrument("Riser FX", _dummy_audio(), 44100) == FX
    assert classify_instrument("Impact hit", _dummy_audio(), 44100) == FX


def test_genre_bias_defaults_to_no_change():
    assert genre_bias(SYNTH_LEAD, "Balanced") == (0.0, 1.0)
    assert genre_bias(STRINGS, "") == (0.0, 1.0)


def test_genre_bias_nudges_edm_and_acoustic_oppositely():
    edm_makeup, edm_reverb = genre_bias(SYNTH_LEAD, "EDM / Urban")
    acoustic_makeup, acoustic_reverb = genre_bias(SYNTH_LEAD, "Acoustic / Classical")
    assert edm_makeup > acoustic_makeup
    assert edm_reverb < acoustic_reverb


def test_short_token_substring_collisions_are_rejected():
    # Word-boundary hardening: short/dangerous tokens must not fire inside
    # unrelated longer words. "organic" contains "organ", "sharp" contains
    # "harp", "merchant" contains "chant", "umbrella" contains "bell",
    # "padding" contains "pad", "monkeys" contains "keys", "warp" contains
    # "arp" -- all real false positives under plain substring matching.
    assert classify_instrument("Organic Pad", _dummy_audio(), 44100) == SYNTH_PAD
    assert classify_instrument("Sharp Lead", _dummy_audio(), 44100) == SYNTH_LEAD
    assert classify_instrument("Merchant", _dummy_audio(), 44100) == GENERIC
    assert classify_instrument("Umbrella", _dummy_audio(), 44100) == GENERIC
    assert classify_instrument("Padding", _dummy_audio(), 44100) == GENERIC
    assert classify_instrument("Monkeys", _dummy_audio(), 44100) == GENERIC


def test_word_boundary_still_accepts_standalone_short_tokens():
    # The hardening must not reject legitimate standalone short tokens.
    assert classify_instrument("Horn", _dummy_audio(), 44100) == BRASS
    assert classify_instrument("Bell 1", _dummy_audio(), 44100) == BELL
    assert classify_instrument("Church bell", _dummy_audio(), 44100) == BELL
    assert classify_instrument("Harp glissando", _dummy_audio(), 44100) == STRINGS
    assert classify_instrument("Arpa", _dummy_audio(), 44100) == STRINGS
    assert classify_instrument("Grand Piano", _dummy_audio(), 44100) == KEYS
    assert classify_instrument("Choir", _dummy_audio(), 44100) == CHOIR
    assert classify_instrument("Atmosphere 1", _dummy_audio(), 44100) == SYNTH_PAD
    assert classify_instrument("Arp 1 bright", _dummy_audio(), 44100) == PLUCK
    assert classify_instrument("Flute 1", _dummy_audio(), 44100) == WOODWINDS
    assert classify_instrument("Fiati legni", _dummy_audio(), 44100) == WOODWINDS


def test_new_families():
    assert classify_instrument("Accordion", _dummy_audio(), 44100) == ACCORDION
    assert classify_instrument("Harmonica", _dummy_audio(), 44100) == ACCORDION
    assert classify_instrument("Harpsichord", _dummy_audio(), 44100) == HARPSICHORD
    assert classify_instrument("Banjo", _dummy_audio(), 44100) == FOLK_PLUCK
    assert classify_instrument("Mandolin", _dummy_audio(), 44100) == FOLK_PLUCK
    assert classify_instrument("Erhu", _dummy_audio(), 44100) == WORLD_STRINGS
    assert classify_instrument("Oud", _dummy_audio(), 44100) == WORLD_STRINGS
    assert classify_instrument("Duduk", _dummy_audio(), 44100) == WORLD_WINDS
    assert classify_instrument("Shakuhachi", _dummy_audio(), 44100) == WORLD_WINDS
    assert classify_instrument("Bagpipes", _dummy_audio(), 44100) == WORLD_WINDS
    assert classify_instrument("Harmonium", _dummy_audio(), 44100) == ORGAN
    assert classify_instrument("Theremin", _dummy_audio(), 44100) == SYNTH_LEAD


def test_every_category_has_recipe():
    import redline.instrumentstack as istack

    # Every category constant (including GENERIC) must have a RECIPES entry,
    # and no recipe may exist for a non-category. A new category constant
    # added without a recipe (or vice-versa) must fail here.
    categories = {
        getattr(istack, name)
        for name in dir(istack)
        if not name.startswith("_") and name.isupper() and isinstance(getattr(istack, name), str)
    }
    assert categories == set(istack.RECIPES)
