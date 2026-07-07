"""Validates the naming parser against the exact real-world file names from
a user's production session ("Come i Tuoni"), so a real project's naming
convention is what defines correctness here, not a synthetic example."""

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
