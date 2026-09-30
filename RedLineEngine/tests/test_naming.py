"""Validates the naming parser against the exact real-world file names from
a user's production session ("Come i Tuoni"), so a real project's naming
convention is what defines correctness here, not a synthetic example."""

import redline.naming as naming
from redline.naming import parse_stem


def test_instrumental_top_level_file_is_other():
    d = parse_stem("COME I TUONI - INSTRUMENTAL")
    assert d.role == "other"
    # "STR" inside "INSTRUMENTAL" must not be misread as a verse-section hint
    assert d.section is None


def test_vocals_subfolder_gives_vocal_role_even_without_vocal_keyword():
    d = parse_stem("vocals stems/Come i Tuoni (Autotune)_Main (Rap) - Special")
    assert d.role == "vocal"
    assert d.layer == "primary"


def test_double_takes_are_recognized_and_panned():
    dx = parse_stem("vocals stems/Come i Tuoni (Autotune)_Double (Autotune) - Armonizz. Rit dx")
    sx = parse_stem("vocals stems/Come i Tuoni (Autotune)_Double (Autotune) - Armonizz. Rit sx")

    assert dx.role == "vocal"
    assert dx.layer == "double"
    assert dx.pan > 0

    assert sx.role == "vocal"
    assert sx.layer == "double"
    assert sx.pan < 0


def test_section_and_register_are_parsed():
    falsetto_verse = parse_stem("vocals stems/Come i Tuoni (Autotune)_Double (Autotune) - FalsettoStr1 dx")
    assert falsetto_verse.section == "verse"
    assert falsetto_verse.register == "falsetto"

    chorus_low = parse_stem("vocals stems/Come i Tuoni (Autotune)_Double (Autotune) - LowRit sx")
    assert chorus_low.section == "chorus"
    assert chorus_low.register == "low"


def test_main_rap_takes_are_primary_centered_vocal():
    d = parse_stem("vocals stems/Come i Tuoni (Autotune)_Main (Rap) - Str1")
    assert d.role == "vocal"
    assert d.layer == "primary"
    assert d.pan == 0.0


def test_italian_voci_folder_is_recognized_as_vocal():
    # "Voci" (Italian plural of "voce") is a natural real-world folder name
    # that "voce" (singular) alone did not match as a substring -- confirmed
    # in practice with a real multi-section session where Main/Double takes
    # under a "Voci" folder fell through to role="other" and were processed
    # as generic instrumental stems instead of vocals.
    main = parse_stem("Intro - Stems Voci/Main")
    double = parse_stem("Intro - Stems Voci/Double dx")
    assert main.role == "vocal"
    assert main.layer == "primary"
    assert double.role == "vocal"
    assert double.layer == "double"


def test_horn_stem_is_not_misread_as_vocal_double():
    # "cor" as a DOUBLE_HINTS token used to match by substring inside "Corno"
    # (French horn) -- an instrumental stem, wrongly classified as a vocal
    # double and pulled into the vocal bus.
    d = parse_stem("Intro - Stems Instrumental/Corno")
    assert d.role == "other"
    assert d.layer == "primary"


def test_coro_takes_are_still_recognized_as_vocal_doubles():
    d = parse_stem("vocals stems/Coro - Armonizz. Rit dx")
    assert d.role == "vocal"
    assert d.layer == "double"


def test_db_prefix_takes_are_recognized_as_vocal_doubles():
    # "Db"/"Db." (short for Italian "Doppia" = double) is a real naming
    # convention found in a real session's stem exports, distinct from the
    # "double"/"coro" words already covered. Without this, these takes fell
    # through to layer="primary" and got summed straight into the lead
    # vocal bus alongside the real lead -- heard as the vocal comb-filtering
    # / cutting in and out unpredictably.
    falsetto = parse_stem("Vocal Stems Pitch Correction/INTRO REC - AUTOTUNE_Db Falsetto - Autotune - L")
    rap = parse_stem("Vocal Stems Pitch Correction/INTRO REC - AUTOTUNE_Db Rap - L")
    alta = parse_stem("Vocal Stems Pitch Correction/INTRO REC - AUTOTUNE_Db. Alta - Autotune - L")
    bassa = parse_stem("Vocal Stems Pitch Correction/INTRO REC - AUTOTUNE_Db. Bassa - Autotune - L")
    for d in (falsetto, rap, alta, bassa):
        assert d.role == "vocal"
        assert d.layer == "double"
    assert alta.register == "high"
    assert bassa.register == "low"
    # These real filenames end in "- L" -- previously ignored entirely (only
    # dx/sx were recognized), so every one of these doubles silently
    # defaulted to pan=0.0 (dead center, fighting the lead for the same
    # space) despite the file itself already saying which side it belongs on.
    for d in (falsetto, rap, alta, bassa):
        assert d.pan < 0


def test_english_r_and_l_pan_hints_are_recognized():
    right = parse_stem("vocals stems/Double Alta - R")
    left = parse_stem("vocals stems/Double Alta - L")
    assert right.pan > 0
    assert left.pan < 0
    # Single-letter tokens must only match as their own word, never as a
    # substring inside an unrelated word (e.g. "Rap", "Live", "Room").
    assert parse_stem("vocals stems/Main (Rap)").pan == 0.0
    assert parse_stem("vocals stems/Live Room Ambience").pan == 0.0


def test_db_does_not_false_positive_inside_unrelated_words():
    # Word-boundary guard: "Db" must only match as its own token, not as a
    # substring inside an unrelated word.
    d = parse_stem("vocals stems/Adbenture - Main")
    assert d.layer == "primary"


def test_808_is_recognized_as_bass():
    # "808" is as standard a sub-bass filename convention in trap/hip-hop as
    # "kick" is for drums (confirmed with a real trap session's stem
    # export). Previously fell through to role="other" and got a highpass
    # applied that guts the sub-bass content it exists for.
    d = parse_stem("Intro - Stems Instrumental/808")
    assert d.role == "bass"


# --- A1: word-boundary hardening + dead-code removal -----------------------


def test_short_tokens_not_matched_inside_unrelated_words():
    # "perc" inside "Percent"/"perception" must not read as a drum hint.
    assert parse_stem("Percent Strings").role != "drums"
    # "voice" inside "invoice" must not read as a vocal hint.
    assert parse_stem("Invoice").role != "vocal"
    # "str" inside "Spirit"/"Strong" must not read as a verse-section hint.
    assert parse_stem("Vocal Spirit").section is None
    assert parse_stem("Vocal Strong").section is None
    # "low" inside "Slow" must not read as a low-register hint.
    assert parse_stem("Vocal Slow Jam").register != "low"


def test_harmonies_is_a_double():
    # "harmony" alone never matched the plural "Harmonies" -- a real gap.
    assert parse_stem("Vocal Harmonies").layer == "double"


def test_main_hints_removed():
    # MAIN_HINTS was dead code (never read); "Main"/"Lead" always yielded
    # layer="primary" because no DOUBLE_HINTS token matched them.
    assert not hasattr(naming, "MAIN_HINTS")
    assert parse_stem("Vocal Main").layer == "primary"
    assert parse_stem("Vocal Lead").layer == "primary"


# --- A2: DAW conventions + kit elements ------------------------------------


def test_daw_numeric_prefixes():
    # Leading DAW track numbers ("01_Kick", "02 - Snare") and trailing take
    # numbers ("Kick_01") must not hide the role hint.
    assert parse_stem("01_Kick").role == "drums"
    assert parse_stem("Kick_01").role == "drums"


def test_kit_elements_are_drums():
    for name in ("HiHat", "Crash", "Ride", "Tom", "Clap", "OH"):
        assert parse_stem(name).role == "drums", name


def test_short_kit_tokens_do_not_swallow_unrelated_names():
    # Regression: the short kit tokens (tom/hat/rim/ride/...) were originally
    # substring-matched, so ordinary instrument names that merely CONTAIN them
    # were routed into the drum bus -- confirmed in practice, "Custom Pad" and
    # "Automaton"/"Phantom"/"Bottom"/"That"/"Trim"/"Pride"/"Override" all
    # matched. They must be word-boundary matched, so a bare substring match
    # never decides a role.
    for name in (
        "Custom Pad", "Atom", "Automatic", "Phantom", "Bottom", "That", "What",
        "Chat", "Trim", "Prim", "Grim", "Pride", "Stride", "Override", "Tomato",
        "Stomach", "Symptom",
    ):
        assert parse_stem(name).role != "drums", name


# --- A3: multilingual role hints -------------------------------------------


def test_multilingual_roles():
    assert parse_stem("Bateria").role == "drums"
    assert parse_stem("Caisse claire").role == "drums"
    assert parse_stem("Schlagzeug").role == "drums"
    assert parse_stem("Voz").role == "vocal"
    assert parse_stem("Voix").role == "vocal"
    assert parse_stem("Stimme").role == "vocal"
    assert parse_stem("Bajo").role == "bass"
    assert parse_stem("Basse").role == "bass"


def test_multilingual_collisions_do_not_break_existing_registers():
    # "Basse" (FR bass) and "Bassa" (IT low register) are near-identical;
    # the register reading must still win for a vocal take named "Bassa".
    bassa = parse_stem("Vocal Stems/INTRO REC - AUTOTUNE_Db. Bassa - Autotune - L")
    assert bassa.role == "vocal"
    assert bassa.register == "low"
    # A bare "Basse" is a bass instrument, not a vocal register.
    assert parse_stem("Basse").role == "bass"


# --- A4: sections, pan, link tokens ----------------------------------------


def test_new_sections():
    assert parse_stem("Vocal Prechorus").section == "prechorus"
    assert parse_stem("Vocal Pre-Chorus").section == "prechorus"
    assert parse_stem("Vocal Intro").section == "intro"
    assert parse_stem("Vocal Outro").section == "outro"
    assert parse_stem("Vocal Drop").section == "drop"
    assert parse_stem("Vocal Breakdown").section == "breakdown"
    assert parse_stem("Vocal Refrain").section == "refrain"
    assert parse_stem("Vocal Interlude").section == "interlude"
    assert parse_stem("Vocal Coda").section == "coda"
    assert parse_stem("Vocal Tag").section == "tag"


def test_explicit_center_pan():
    assert parse_stem("Vocal Center").pan == 0.0
    assert parse_stem("Vocal Centre").pan == 0.0
    assert parse_stem("Vocal Mono").pan == 0.0


def test_l1_r1_pan():
    assert parse_stem("Vocal L1").pan < 0
    assert parse_stem("Vocal R1").pan > 0
    assert parse_stem("Vocal L100").pan < 0
    assert parse_stem("Vocal R100").pan > 0


def test_new_link_tokens():
    assert parse_stem("Kick_Close").link_id == parse_stem("Kick_Far").link_id
    assert parse_stem("Kick_Near").link_id is not None
    assert parse_stem("Gtr_Mic1").link_id == parse_stem("Gtr_Mic2").link_id
    assert parse_stem("Bass_Amp").link_id is not None
    assert parse_stem("Gtr_Front").link_id == parse_stem("Gtr_Back").link_id
    assert parse_stem("Bass_DI").link_id is not None
