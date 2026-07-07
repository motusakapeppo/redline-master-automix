"""Validates classify_instrument()'s filename-hint detection against real
stem names from real FL Studio sessions (BAGDAD, INTRO REC), the same way
test_naming.py validates naming.py against a real project's file names."""

import numpy as np

from redline.instrumentstack import classify_instrument, STRINGS, BRASS, KEYS, CHOIR, SYNTH_PAD, SYNTH_LEAD


def _dummy_audio(n=4410, sr=44100):
    return (0.1 * np.random.default_rng(0).standard_normal(n)).astype(np.float32)


def test_horn_and_trombone_are_brass():
    assert classify_instrument("Horn", _dummy_audio(), 44100) == BRASS
    assert classify_instrument("Trombone", _dummy_audio(), 44100) == BRASS


def test_bells_are_recognized_not_left_to_spectral_guessing():
    # "Bell 1", "Bell reverb", "Church bell" -- all real stem names with no
    # prior category at all, previously falling through to the spectral
    # fallback instead of a dedicated recipe.
    assert classify_instrument("Bell 1", _dummy_audio(), 44100) == STRINGS
    assert classify_instrument("Bell reverb", _dummy_audio(), 44100) == STRINGS
    assert classify_instrument("Church bell", _dummy_audio(), 44100) == STRINGS


def test_pianos_are_keys():
    assert classify_instrument("Grand Piano", _dummy_audio(), 44100) == KEYS
    assert classify_instrument("Upright Piano (D)", _dummy_audio(), 44100) == KEYS


def test_choir_is_choir():
    assert classify_instrument("Choir", _dummy_audio(), 44100) == CHOIR


def test_atmosphere_is_synth_pad():
    assert classify_instrument("Atmosphere 1", _dummy_audio(), 44100) == SYNTH_PAD


def test_arp_is_synth_lead():
    assert classify_instrument("Arp 1 bright", _dummy_audio(), 44100) == SYNTH_LEAD
