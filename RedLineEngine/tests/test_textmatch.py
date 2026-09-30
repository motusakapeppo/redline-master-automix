"""Tests for redline.textmatch: the shared token-matching helper. The word
mode must reproduce naming.py's original boundary semantics exactly (short
tokens like "str"/"in" only match as standalone words), and substring mode
must reproduce the original plain `in` check."""

from redline.textmatch import contains_token, contains_any, contains_word


def test_contains_word_rejects_substring_inside_longer_word():
    assert contains_word("strong", "str") is False


def test_contains_any_accepts_substring_inside_longer_word():
    assert contains_any("strong", "str") is True


def test_contains_word_matches_standalone_token_after_space():
    assert contains_word("nella strofa", "strofa") is True


def test_contains_word_matches_token_bounded_by_underscore():
    assert contains_word("Kick_In", "in") is True


def test_contains_word_matches_token_at_start_and_end():
    assert contains_word("in the mix", "in") is True
    assert contains_word("the mix in", "in") is True


def test_contains_word_rejects_token_inside_unrelated_word():
    # "Piano" contains "in" as a substring but not as a word.
    assert contains_word("Piano", "in") is False
    # "Bassa" contains "bass" as a substring but not as a word.
    assert contains_word("Db. Bassa", "bass") is False
    assert contains_word("Bass DI", "bass") is True


def test_matching_is_case_insensitive():
    assert contains_any("STRONG", "str") is True
    assert contains_word("KICK_IN", "in") is True
    assert contains_word("Nella Strofa", "STROFA") is True
    assert contains_token("Bass DI", "BASS", mode="word") is True
    assert contains_token("Bass DI", "bass", mode="substr") is True


def test_contains_token_mode_selection():
    assert contains_token("strong", "str", mode="substr") is True
    assert contains_token("strong", "str", mode="word") is False
    assert contains_token("nella strofa", "strofa", mode="word") is True


def test_contains_token_rejects_unknown_mode():
    import pytest

    with pytest.raises(ValueError):
        contains_token("text", "token", mode="fuzzy")


def test_empty_token_collections_match_nothing():
    assert contains_any("anything", ()) is False
    assert contains_word("anything", ()) is False


def test_empty_text_matches_nothing_for_nonempty_tokens():
    assert contains_any("", "str") is False
    assert contains_word("", "str") is False


def test_single_string_token_is_treated_as_one_token():
    # A bare string must not be iterated character-by-character.
    assert contains_any("strong", "str") is True
    assert contains_word("Kick_In", "in") is True
    assert contains_word("strong", "str") is False


def test_token_regex_metacharacters_are_escaped():
    # Tokens are re.escape'd, so a token like "e.g." matches literally.
    assert contains_any("track e.g. main", "e.g.") is True
    assert contains_word("track e.g. main", "e.g.") is True
    assert contains_word("track eg main", "e.g.") is False
