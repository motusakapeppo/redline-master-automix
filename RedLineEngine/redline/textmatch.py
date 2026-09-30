"""Shared token-matching helpers.

One place for the two matching semantics the engine uses when reading
user-authored names (file names, folder names, free-text requests):

- substring ("substr"): the token appears anywhere in the text. Cheap and
  forgiving, but short tokens false-positive inside unrelated words.
- word ("word"): the token must be its own word, bounded by the start/end
  of the string or one of the separator characters the engine's naming
  conventions actually use (whitespace, underscore, dot, slash, backslash,
  parentheses, braces, brackets, hyphen). This is the exact boundary regex
  naming.py has always used for its short/dangerous tokens ("bass" vs
  "Bassa", "in" vs "Piano", "str" vs "strumentale").

Both modes are case-insensitive: text and token are lowercased before
matching, mirroring naming.py's original implementation exactly. Tokens are
re.escape'd, so regex metacharacters in a token are matched literally.
"""

from __future__ import annotations

import re

# The separator set naming.py's word-boundary patterns have always used:
# whitespace, underscore, dot, slash, backslash, parens, braces, brackets,
# hyphen. Kept as a raw regex character class so it can be embedded in the
# word pattern below.
_BOUNDARY_CLASS = r"[\s_./\\(){}\[\]-]"


def _word_pattern(token: str) -> str:
    return rf"(?:^|{_BOUNDARY_CLASS}){re.escape(token.lower())}(?:{_BOUNDARY_CLASS}|$)"


def _normalize_tokens(tokens: str | tuple[str, ...]) -> tuple[str, ...]:
    """Accepts either a single token string or a tuple/list of tokens, so
    `contains_word(text, "in")` and `contains_word(text, ("in", "out"))`
    both work. A bare string is treated as ONE token, never iterated
    character-by-character."""
    if isinstance(tokens, str):
        return (tokens,)
    return tuple(tokens)


def contains_token(text: str, token: str, mode: str = "substr") -> bool:
    """True if `token` occurs in `text` according to `mode`.

    mode="substr": plain substring match (case-insensitive).
    mode="word": token must be a standalone word, bounded by start/end of
    string or a separator character (case-insensitive, token re.escape'd).

    Raises ValueError for any other mode.
    """
    if mode == "substr":
        return token.lower() in text.lower()
    if mode == "word":
        return re.search(_word_pattern(token), text.lower()) is not None
    raise ValueError(f"unknown match mode: {mode!r} (expected 'substr' or 'word')")


def contains_any(text: str, tokens: str | tuple[str, ...]) -> bool:
    """Substring match: True if any token appears anywhere in text.
    Mirrors naming.py's original _contains_any semantics exactly."""
    lowered = text.lower()
    return any(token.lower() in lowered for token in _normalize_tokens(tokens))


def contains_word(text: str, tokens: str | tuple[str, ...]) -> bool:
    """Word-boundary match: True if any token appears as its own word.
    Mirrors naming.py's original _contains_word semantics exactly."""
    lowered = text.lower()
    return any(
        re.search(_word_pattern(token), lowered) is not None
        for token in _normalize_tokens(tokens)
    )
