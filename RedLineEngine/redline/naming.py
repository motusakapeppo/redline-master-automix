"""Parses stem role/layer/pan/section/register from how the user actually
named their files and folders — no audio content analysis involved. This is
deliberately convention-based rather than ML-based: real vocal production
sessions (like a "Main"/"Double" take structure with dx/sx hard-panned
harmonies) already encode this information in the file names, so the job is
to read it, not guess it acoustically.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Role hints — checked against the full relative path (folder name included),
# because in real projects the *folder* often says "vocals stems" while the
# individual take names (e.g. "Main (Rap) - Special.wav") don't mention
# "vocal" at all.
VOCAL_ROLE_HINTS = ("vocal", "vox", "voice", "voce", "voci", "canto", "cantante")
# "808" -- the sub-bass instrument name in trap/hip-hop production, as
# standard a convention as "kick" is for drums (confirmed with a real trap
# session: a file literally named "808.wav" sitting next to "Kick"/"Snare").
# Without it, an 808 falls through to role="other" and gets a highpass
# applied that guts the exact sub-bass content it exists for.
BASS_ROLE_HINTS = ("bass", "sub", "basso", "808")
DRUM_ROLE_HINTS = ("drum", "kick", "snare", "perc", "batteria", "cassa", "rullante")

# Take-layer hints, meaningful for vocal stems: a "double"/harmony sits under
# and beside the lead, not centered and not as loud.
# "coro"/"cori" (choir), not the truncated "cor" -- that substring falsely
# matched inside unrelated instrument names (e.g. "Corno", French horn,
# confirmed in practice landing a horn stem in the vocal double bus).
DOUBLE_HINTS = ("double", "armonizz", "harmony", "backing", "coro", "cori")
MAIN_HINTS = ("main", "lead")

# "Db"/"Db." -- short for "Doppia" (Italian for "double"), a real naming
# convention confirmed in practice (e.g. "INTRO_Db Falsetto", "INTRO_Db.
# Alta") distinct from the DOUBLE_HINTS words above. Too short to trust as a
# plain substring (would false-positive inside unrelated text), so it's
# matched the same word-boundary way DX_PATTERN/SX_PATTERN already are --
# without this, these takes defaulted to layer="primary" and got summed
# straight into the lead vocal bus alongside the real lead, comb-filtering
# with it (heard as the vocal cutting in and out unpredictably).
_DB_LAYER_PATTERN = re.compile(r"(?:^|[\s_./\\(){}\[\]-])db\.?(?:[\s_./\\(){}\[\]-]|$)", re.IGNORECASE)

SECTION_HINTS = {
    "chorus": ("rit", "ritornello", "chorus", "hook"),
    "verse": ("str", "strofa", "verse"),
    "bridge": ("bridge", "ponte"),
}

REGISTER_HINTS = {
    "falsetto": ("falsetto", "flasetto"),  # tolerate the common typo
    "low": ("low", "bassa"),  # "bassa" = Italian for "low" (register, not role)
    "high": ("high", "alta"),  # "alta" = Italian for "high"
    "mid": ("mid",),
    "special": ("special",),
}

_DX_PATTERN = re.compile(r"(?:^|[\s_./\\(){}\[\]-])dx(?:[\s_./\\(){}\[\]-]|$)", re.IGNORECASE)
_SX_PATTERN = re.compile(r"(?:^|[\s_./\\(){}\[\]-])sx(?:[\s_./\\(){}\[\]-]|$)", re.IGNORECASE)


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(t in lowered for t in tokens)


def _contains_word(text: str, tokens: tuple[str, ...]) -> bool:
    """Same as _contains_any, but requires each token to be its own word
    (bounded by start/end-of-string or a separator) rather than matching
    anywhere as a bare substring. BASS_ROLE_HINTS needs this: "bass" is a
    real, common role hint, but it's also the first four letters of "Bassa"
    (Italian for a low vocal register, confirmed in a real session's file
    "Db. Bassa" -- a vocal double, misrouted to role=bass entirely because
    of this). Bass instrument filenames are always their own standalone
    word in practice ("Bass DI.wav", "808.wav"), so this loses nothing."""
    lowered = text.lower()
    return any(
        re.search(rf"(?:^|[\s_./\\(){{}}\[\]-]){re.escape(t)}(?:[\s_./\\(){{}}\[\]-]|$)", lowered)
        for t in tokens
    )


def _first_match(text: str, hint_groups: dict[str, tuple[str, ...]]) -> str | None:
    for name, tokens in hint_groups.items():
        if _contains_any(text, tokens):
            return name
    return None


def _pan_from_name(text: str) -> float:
    if _DX_PATTERN.search(text):
        return 0.8
    if _SX_PATTERN.search(text):
        return -0.8
    return 0.0


@dataclass
class StemDescriptor:
    raw_name: str
    role: str                    # vocal | bass | drums | other
    layer: str = "primary"       # primary | double  (only meaningful when role == vocal)
    pan: float = 0.0             # -1 (hard left/sx) .. +1 (hard right/dx)
    section: str | None = None   # chorus | verse | bridge | None
    register: str | None = None  # falsetto | low | mid | special | None
    role_confidence: float = 1.0  # 1.0 = a role hint matched the name; lower = "other" by default, no real signal


def parse_stem(path_like: str) -> StemDescriptor:
    text = path_like.replace("\\", "/")

    if _contains_word(text, BASS_ROLE_HINTS):
        role = "bass"
        role_confidence = 1.0
    elif _contains_any(text, DRUM_ROLE_HINTS):
        role = "drums"
        role_confidence = 1.0
    elif _contains_any(text, VOCAL_ROLE_HINTS):
        role = "vocal"
        role_confidence = 1.0
    else:
        # No naming hint at all -- role defaults to "other" with low
        # confidence, which is exactly the signal the LLM advisory fallback
        # (llm_classifier.py, gated by ENABLE_LLM_ADVISORY) looks for.
        role = "other"
        role_confidence = 0.3

    layer = "double" if _contains_any(text, DOUBLE_HINTS) or _DB_LAYER_PATTERN.search(text) else "primary"
    # Was gated to `layer == "double"` only -- a dx/sx hint in an
    # instrumental stem's name (e.g. "Chitarra_dx.wav") was silently
    # ignored and the stem defaulted to dead center, along with every other
    # "other"-role stem (mixengine.py had no panning logic for them at all).
    # The dx/sx convention is generic, not vocal-specific, so honor it for
    # any stem that has it.
    pan = _pan_from_name(text)

    # Section/register (verse/chorus, falsetto/low/mid...) only mean anything
    # for vocal takes. Gating on role also avoids false positives like "STR"
    # inside "INSTRUMENTAL" being misread as a verse-section hint.
    section = _first_match(text, SECTION_HINTS) if role == "vocal" else None
    register = _first_match(text, REGISTER_HINTS) if role == "vocal" else None

    return StemDescriptor(
        raw_name=path_like,
        role=role,
        layer=layer,
        pan=pan,
        section=section,
        register=register,
        role_confidence=role_confidence,
    )
