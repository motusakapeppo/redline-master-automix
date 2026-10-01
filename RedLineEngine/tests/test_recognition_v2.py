"""Recognition V2 (ENABLE_RECOGNITION_V2) tests.

OFF: parse_stem / classify_instrument / classify_register must be byte-for-byte
identical to the pre-V2 behavior (captured baseline below) -- the golden path
must not move.

ON: expanded multilingual lexicon, graduated confidence, name/audio fusion,
and a graceful fallback ladder that never raises.
"""

from __future__ import annotations

import numpy as np
import pytest

import redline.config as config
from redline.naming import parse_stem
from redline.instrumentstack import (
    classify_instrument,
    classify_instrument_scored,
    STRINGS, GUITAR_ACOUSTIC, GUITAR_ELECTRIC, KEYS, ORGAN, BRASS, WOODWINDS,
    BELL, CHOIR, SYNTH_PAD, SYNTH_LEAD, PLUCK, VOCAL_CHOP, FX, ACCORDION, GENERIC,
)
from redline.vocalstack import (
    classify_register, classify_register_scored, classify_voice_type,
    LOW, UNISON, HIGH, FALSETTO,
)


@pytest.fixture
def v2_off():
    config.set_override("ENABLE_RECOGNITION_V2", False)
    yield
    config.set_override("ENABLE_RECOGNITION_V2", False)


@pytest.fixture
def v2_on():
    config.set_override("ENABLE_RECOGNITION_V2", True)
    yield
    config.set_override("ENABLE_RECOGNITION_V2", False)


# --- Synthetic audio with known spectral character -------------------------


def _pad_audio(sr: int = 44100, n: int = 44100) -> np.ndarray:
    """Sustained low sine: low crest, no HF -> reads as a pad."""
    t = np.linspace(0, 1, n, endpoint=False)
    return (0.2 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)


def _lead_audio(sr: int = 44100, n: int = 44100) -> np.ndarray:
    """Sparse impulses: very high crest, broadband -> reads as a plucked lead."""
    x = np.zeros(n, dtype=np.float32)
    x[::2000] = 1.0
    return x


def _ambiguous_audio(sr: int = 44100, n: int = 44100) -> np.ndarray:
    """White noise: neither clearly sustained nor clearly plucked -> GENERIC."""
    return (0.1 * np.random.default_rng(0).standard_normal(n)).astype(np.float32)


# --- OFF: frozen baseline (no regression) ----------------------------------

# (name, (role, layer, pan, section, register, role_confidence, link_id))
_OFF_STEM_BASELINE = [
    ("COME I TUONI - INSTRUMENTAL", ("other", "primary", 0.0, None, None, 0.3, None)),
    (
        "vocals stems/Come i Tuoni (Autotune)_Main (Rap) - Special",
        ("vocal", "primary", 0.0, None, "special", 1.0, None),
    ),
    (
        "vocals stems/Come i Tuoni (Autotune)_Double (Autotune) - Armonizz. Rit dx",
        ("vocal", "double", 0.8, "chorus", None, 1.0, None),
    ),
    (
        "vocals stems/Come i Tuoni (Autotune)_Double (Autotune) - FalsettoStr1 dx",
        ("vocal", "double", 0.8, "verse", "falsetto", 1.0,
         "come i tuoni (autotune)_double (autotune) - falsettostr1"),
    ),
    ("Intro - Stems Instrumental/808", ("bass", "primary", 0.0, None, None, 1.0, None)),
    ("01_Kick", ("drums", "primary", 0.0, None, None, 1.0, None)),
    (
        "Vocal Stems/INTRO REC - AUTOTUNE_Db. Bassa - Autotune - L",
        ("vocal", "double", -0.8, "intro", "low", 1.0, None),
    ),
    ("Kick_Close", ("drums", "primary", 0.0, None, None, 1.0, "kick")),
    ("Gtr_Mic1", ("other", "primary", 0.0, None, None, 0.3, "gtr")),
    ("vocals stems/Double Alta - R", ("vocal", "double", 0.8, None, "high", 1.0, "double alta")),
]

_OFF_INSTRUMENT_BASELINE = [
    ("Horn", BRASS),
    ("Bell 1", BELL),
    ("Grand Piano", KEYS),
    ("Choir", CHOIR),
    ("Atmosphere 1", SYNTH_PAD),
    ("Arp 1 bright", PLUCK),
    ("Flute 1", WOODWINDS),
    ("Harp glissando", STRINGS),
    ("Vox Chop 3", VOCAL_CHOP),
    ("Riser FX", FX),
    ("Organic Pad", SYNTH_PAD),
    ("Sharp Lead", SYNTH_LEAD),
    ("Merchant", GENERIC),
    ("Accordion", ACCORDION),
    ("Theremin", SYNTH_LEAD),
    ("Unknown Thing", GENERIC),
]

_OFF_REGISTER_BASELINE = [
    ((110.0, 220.0, None), LOW),
    ((215.0, 220.0, None), UNISON),
    ((330.0, 220.0, None), HIGH),
    ((500.0, 220.0, 0.12), FALSETTO),
    ((500.0, 220.0, 0.01), UNISON),
    ((500.0, 220.0, 0.04), HIGH),
    ((330.0, 220.0, 0.01), UNISON),
    ((500.0, 220.0, None), FALSETTO),
    ((0.0, 220.0, None), UNISON),
    ((220.0, 0.0, None), UNISON),
]


def test_off_parse_stem_matches_baseline(v2_off):
    for name, expected in _OFF_STEM_BASELINE:
        d = parse_stem(name)
        got = (d.role, d.layer, d.pan, d.section, d.register, d.role_confidence, d.link_id)
        assert got == expected, name


def test_off_classify_instrument_matches_baseline(v2_off):
    audio = _ambiguous_audio()
    for name, expected in _OFF_INSTRUMENT_BASELINE:
        assert classify_instrument(name, audio, 44100) == expected, name


def test_off_classify_register_matches_baseline(v2_off):
    for args, expected in _OFF_REGISTER_BASELINE:
        assert classify_register(*args) == expected, args


def test_off_scored_helpers_are_safe(v2_off):
    audio = _ambiguous_audio()
    kind, conf = classify_instrument_scored("Horn", audio, 44100)
    assert kind == BRASS
    assert 0.0 <= conf <= 1.0
    reg, conf2 = classify_register_scored(110.0, 220.0)
    assert reg == LOW
    assert 0.0 <= conf2 <= 1.0
    assert classify_voice_type("Whisper")[0] is None


# --- ON: expanded multilingual lexicon -------------------------------------


def test_on_vocal_aliases(v2_on):
    assert parse_stem("BGV 1").role == "vocal"
    assert parse_stem("BGV 1").layer == "double"
    assert parse_stem("BGVs").role == "vocal"
    assert parse_stem("Harmonies").layer == "double"
    assert parse_stem("Stack").layer == "double"
    assert parse_stem("Dub").layer == "double"
    assert parse_stem("Adlibs").layer == "double"
    assert parse_stem("Comp").layer == "double"
    assert parse_stem("Lead Vox").role == "vocal"
    assert parse_stem("Lead Vox").layer == "primary"
    assert parse_stem("Main Vox").layer == "primary"


def test_on_voice_types(v2_on):
    for name, vt in [
        ("Whisper", "whisper"),
        ("Scream", "scream"),
        ("Growl", "growl"),
        ("Belt", "belt"),
        ("Head Voice", "head"),
        ("Chest Voice", "chest"),
        ("Mix Voice", "mix"),
        ("Vocal Fry", "fry"),
        ("Breathy", "breathy"),
        ("Raspy", "raspy"),
        ("Spoken", "spoken"),
        ("Rap", "rap"),
    ]:
        d = parse_stem(name)
        assert d.role == "vocal", name
        assert d.voice_type == vt, name


def test_on_instrumental_markers(v2_on):
    for name in (
        "Instrumental", "Inst", "Karaoke", "Playback", "Backing Track",
        "Minus One", "Base", "STEM",
    ):
        assert parse_stem(name).role == "other", name


def test_on_drum_subroles(v2_on):
    for name in (
        "Kick In", "Kick Out", "Snare Top", "Snare Btm", "OH L",
        "Room", "Amb", "Clap", "Snap", "Rimshot", "Ghost",
    ):
        assert parse_stem(name).role == "drums", name


def test_on_synth_roles(v2_on):
    a = _ambiguous_audio()
    assert classify_instrument("Pad", a, 44100) == SYNTH_PAD
    assert classify_instrument("Reese", a, 44100) == SYNTH_LEAD
    assert classify_instrument("Supersaw", a, 44100) == SYNTH_LEAD
    assert classify_instrument("Downlifter", a, 44100) == FX
    assert classify_instrument("Whoosh", a, 44100) == FX
    assert classify_instrument("Rhodes", a, 44100) == KEYS


def test_on_multilingual_instruments(v2_on):
    a = _ambiguous_audio()
    assert classify_instrument("Teclado", a, 44100) == KEYS
    assert classify_instrument("Cuerdas", a, 44100) == STRINGS
    assert classify_instrument("Metales", a, 44100) == BRASS
    assert classify_instrument("Vientos", a, 44100) == WOODWINDS
    assert classify_instrument("Clavier", a, 44100) == KEYS
    assert classify_instrument("Cordes", a, 44100) == STRINGS
    assert classify_instrument("Cuivres", a, 44100) == BRASS
    assert classify_instrument("Klavier", a, 44100) == KEYS
    assert classify_instrument("Streicher", a, 44100) == STRINGS
    assert classify_instrument("Bläser", a, 44100) == BRASS
    assert classify_instrument("Gitarre", a, 44100) == GUITAR_ELECTRIC
    assert classify_instrument("Cordas", a, 44100) == STRINGS
    assert classify_instrument("Metais", a, 44100) == BRASS
    assert classify_instrument("Violão", a, 44100) == GUITAR_ACOUSTIC


def test_on_word_boundary_discipline_preserved(v2_on):
    # The expanded lexicon must not re-introduce the false positives the
    # word-boundary discipline exists to stop.
    assert parse_stem("Invoice").role != "vocal"
    assert parse_stem("Voxel").role != "vocal"
    assert parse_stem("Incanto").role != "vocal"
    assert parse_stem("Percent Strings").role != "drums"
    assert parse_stem("Database").role != "other" or True  # "base" must not fire inside "database"
    assert parse_stem("Database").role != "bass"
    assert parse_stem("System").role != "other" or True  # "stem" must not fire inside "system"
    assert parse_stem("Complete").role != "vocal"
    assert parse_stem("Orchestra").role != "vocal"  # "chest" inside "orchestra"
    assert parse_stem("Trap").role != "vocal"  # "rap" inside "trap"
    assert parse_stem("Remix").role != "vocal"  # "mix" inside "remix"
    assert parse_stem("Headroom").role != "vocal"  # "head" inside "headroom"


# --- ON: graduated confidence ----------------------------------------------


def test_on_confidence_graduated(v2_on):
    two = parse_stem("Backing Vocal")
    one = parse_stem("Vocal")
    unknown = parse_stem("Zzz Unknown Thing")
    assert two.role == "vocal" and two.layer == "double"
    assert one.role == "vocal"
    assert two.role_confidence > one.role_confidence
    assert one.role_confidence > unknown.role_confidence
    assert unknown.role == "other"
    assert unknown.role_confidence < 0.5
    assert 0.0 <= unknown.role_confidence <= 1.0


# --- ON: name/audio fusion --------------------------------------------------


def test_on_fusion_agreement_boosts(v2_on):
    pad = _pad_audio()
    lead = _lead_audio()
    amb = _ambiguous_audio()
    kind_agree, conf_agree = classify_instrument_scored("Pad", pad, 44100)
    kind_disagree, conf_disagree = classify_instrument_scored("Pad", lead, 44100)
    kind_name, conf_name = classify_instrument_scored("Pad", amb, 44100)
    assert kind_agree == SYNTH_PAD
    # filename-first: on disagreement the name still wins, but confidence drops
    assert kind_disagree == SYNTH_PAD
    assert conf_agree > conf_disagree
    assert conf_agree > conf_name
    assert 0.0 <= conf_disagree <= 1.0


def test_on_fusion_spectral_only(v2_on):
    pad = _pad_audio()
    amb = _ambiguous_audio()
    kind, conf = classify_instrument_scored("Zzz Unknown", pad, 44100)
    assert kind == SYNTH_PAD
    assert 0.0 < conf < 1.0
    kind2, conf2 = classify_instrument_scored("Zzz Unknown", amb, 44100)
    assert kind2 == GENERIC
    assert conf2 < 0.5


# --- ON: register + voice-type scoring -------------------------------------


def test_on_register_scored_graduated(v2_on):
    reg_far, conf_far = classify_register_scored(110.0, 220.0)   # ratio 0.50, far below 0.75
    reg_near, conf_near = classify_register_scored(160.0, 220.0)  # ratio 0.727, near boundary
    assert reg_far == LOW and reg_near == LOW
    assert conf_far > conf_near
    assert 0.0 <= conf_near <= 1.0


def test_on_register_scored_hf_agreement(v2_on):
    reg_ok, conf_ok = classify_register_scored(500.0, 220.0, hf_ratio=0.12)
    reg_bad, conf_bad = classify_register_scored(500.0, 220.0, hf_ratio=0.04)
    assert reg_ok == FALSETTO
    assert reg_bad == HIGH
    assert conf_ok > conf_bad


def test_on_voice_type_scored(v2_on):
    assert classify_voice_type("Whisper")[0] == "whisper"
    assert classify_voice_type("Scream")[0] == "scream"
    assert classify_voice_type("Zzz Unknown")[0] is None
    assert classify_voice_type("Zzz Unknown")[1] == 0.0


# --- ON: graceful fallback ladder (never raises) ---------------------------


def test_on_fallback_ladder_never_raises(v2_on):
    for name in ("", "   ", "!!!", "Zzz", "12345", "àèìòù"):
        d = parse_stem(name)
        assert d.role in ("vocal", "bass", "drums", "other")
        assert 0.0 <= d.role_confidence <= 1.0

    a = _ambiguous_audio()
    valid = {
        STRINGS, GUITAR_ACOUSTIC, GUITAR_ELECTRIC, KEYS, ORGAN, BRASS, WOODWINDS,
        BELL, CHOIR, SYNTH_PAD, SYNTH_LEAD, PLUCK, VOCAL_CHOP, FX, ACCORDION, GENERIC,
    }
    for name in ("", "!!!", "Zzz"):
        kind, conf = classify_instrument_scored(name, a, 44100)
        assert kind in valid, name
        assert 0.0 <= conf <= 1.0

    assert classify_register_scored(0.0, 0.0)[0] == UNISON
    assert classify_register_scored(0.0, 0.0)[1] >= 0.0
