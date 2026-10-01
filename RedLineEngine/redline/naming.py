"""Parses stem role/layer/pan/section/register from how the user actually
named their files and folders — no audio content analysis involved. This is
deliberately convention-based rather than ML-based: real vocal production
sessions (like a "Main"/"Double" take structure with dx/sx hard-panned
harmonies) already encode this information in the file names, so the job is
to read it, not guess it acoustically.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from . import config
from .textmatch import contains_any as _tm_contains_any
from .textmatch import contains_word as _tm_contains_word

# The separator set the engine's naming conventions use (whitespace,
# underscore, dot, slash, backslash, parens, braces, brackets, hyphen). Kept
# local so the camelCase-aware matcher below can build its own patterns
# without reaching into textmatch's private constant.
_SEP_CLASS = r"[\s_./\\(){}\[\]-]"

# Role hints — checked against the full relative path (folder name included),
# because in real projects the *folder* often says "vocals stems" while the
# individual take names (e.g. "Main (Rap) - Special.wav") don't mention
# "vocal" at all.
#
# Split into substring-safe tokens and word-boundary tokens: "vocal" must
# still match the plural "vocals" (a real folder name), so it stays a
# substring, while the short/ambiguous tokens ("vox" inside "voxel", "voice"
# inside "invoice", "canto" inside "incanto"/"recanto") are word-boundary.
VOCAL_ROLE_HINTS = ("vocal", "voce", "voci", "cantante")
VOCAL_WORD_HINTS = ("vox", "voice", "voices", "canto", "voz", "voces", "voix", "stimme", "gesang")
# "808" -- the sub-bass instrument name in trap/hip-hop production, as
# standard a convention as "kick" is for drums (confirmed with a real trap
# session: a file literally named "808.wav" sitting next to "Kick"/"Snare").
# Without it, an 808 falls through to role="other" and gets a highpass
# applied that guts the exact sub-bass content it exists for.
# "bajo" (ES) / "basse" (FR) are the same instrument in other languages;
# "basse" is word-boundary so it never swallows the Italian register "Bassa".
BASS_ROLE_HINTS = ("bass", "sub", "basso", "808", "bajo", "basse")
# Drum role hints. The whole tuple is word-boundary matched so "perc" stops
# matching inside "percent"/"perception"; "drums" is listed explicitly
# because word-boundary "drum" alone would not match the plural.
#
# Kit elements are split by how dangerous a bare substring is. Short tokens
# ("hat", "tom", "rim", "ride", "clap", "crash") MUST be word-boundary: as
# substrings they silently swallowed common unrelated names -- confirmed in
# practice, "Custom Pad" contains "tom" and "Atom"/"Automatic"/"Phantom"/
# "Bottom"/"That"/"Trim"/"Pride"/"Override" all matched, routing ordinary
# instrument stems into the drum bus. Only genuinely unambiguous multi-char
# tokens stay substring.
# "room"/"loop"/"break"/"beat"/"top"/"bottom" are deliberately NOT role
# hints -- too ambiguous (they'd misfire on "Room Ambience" / "Top Loop").
DRUM_ROLE_HINTS = (
    "drum", "drums", "kick", "snare", "perc", "batteria", "cassa", "rullante",
    # ES / FR / DE
    "bateria", "bombo", "caja", "batterie", "caisse claire", "schlagzeug", "trommel",
)
DRUM_SUBSTR_HINTS = (
    "hihat", "hi-hat", "cymbal", "overhead",
)
DRUM_WORD_HINTS = ("oh", "hh", "hat", "tom", "rim", "ride", "clap", "crash")

# Take-layer hints, meaningful for vocal stems: a "double"/harmony sits under
# and beside the lead, not centered and not as loud.
# "coro"/"cori" (choir), not the truncated "cor" -- that substring falsely
# matched inside unrelated instrument names (e.g. "Corno", French horn,
# confirmed in practice landing a horn stem in the vocal double bus).
# "harmony" alone never matched the plural "Harmonies" (a real gap), so the
# plural/stem forms are listed too; "armonizz" stays a substring because it's
# an Italian stem ("armonizzazione", "armonizzato").
DOUBLE_HINTS = ("double", "armonizz", "backing")
DOUBLE_WORD_HINTS = ("harmony", "harmonies", "harmoni", "coro", "cori")

# "Db"/"Db." -- short for "Doppia" (Italian for "double"), a real naming
# convention confirmed in practice (e.g. "INTRO_Db Falsetto", "INTRO_Db.
# Alta") distinct from the DOUBLE_HINTS words above. Too short to trust as a
# plain substring (would false-positive inside unrelated text), so it's
# matched the same word-boundary way DX_PATTERN/SX_PATTERN already are --
# without this, these takes defaulted to layer="primary" and got summed
# straight into the lead vocal bus alongside the real lead, comb-filtering
# with it (heard as the vocal cutting in and out unpredictably).
_DB_LAYER_PATTERN = re.compile(r"(?:^|[\s_./\\(){}\[\]-])db\.?(?:[\s_./\\(){}\[\]-]|$)", re.IGNORECASE)

# Section hints. "prechorus" is listed before "chorus" so a "Prechorus" take
# resolves to prechorus, not the shorter "chorus" substring; the matcher is
# word-boundary anyway, but dict order is the tie-breaker for the
# "Pre-Chorus" case where "chorus" is a genuine standalone token.
SECTION_HINTS = {
    "prechorus": ("prechorus", "pre-chorus", "prerit"),
    "chorus": ("rit", "ritornello", "chorus", "hook"),
    "verse": ("str", "strofa", "verse"),
    "bridge": ("bridge", "ponte"),
    "intro": ("intro",),
    "outro": ("outro",),
    "drop": ("drop",),
    "breakdown": ("breakdown", "break"),
    "refrain": ("refrain",),
    "interlude": ("interlude",),
    "coda": ("coda",),
    "tag": ("tag",),
}

REGISTER_HINTS = {
    "falsetto": ("falsetto", "flasetto"),  # tolerate the common typo
    "low": ("low", "bassa"),  # "bassa" = Italian for "low" (register, not role)
    "high": ("high", "alta"),  # "alta" = Italian for "high"
    "mid": ("mid",),
    "special": ("special",),
}

# ---------------------------------------------------------------------------
# Recognition V2 lexicons (ENABLE_RECOGNITION_V2, OFF by default).
#
# Everything below is only consulted when the flag is ON, so the frozen
# OFF-path lexicons above stay exactly as they are (golden stays green).
# The V2 sets are *additive*: the OFF tuples are still checked first, then
# these, so a token that already worked keeps working and only genuinely new
# vocabulary is added.
#
# Word-boundary discipline is preserved throughout: every short/ambiguous
# token is matched with contains_word (never a bare substring), so "base"
# never fires inside "database", "stem" never inside "system", "rap" never
# inside "trap", "mix" never inside "remix", "head" never inside "headroom".
# ---------------------------------------------------------------------------

# Vocal role aliases (role == "vocal"). "vox"/"voice" already live in the OFF
# VOCAL_WORD_HINTS; these are the producer-slang additions.
VOCAL_ROLE_HINTS_V2 = (
    "bgv", "bgvs", "bkg vocal", "backing vocal", "backing vox", "back vox",
    "harmony vocal", "harmonies", "harm vox", "stack", "stacks", "dub", "dubs",
    "adlib", "adlibs", "ad-lib", "ad-libs", "comp", "comps", "comped",
    "lead vocal", "lead vox", "main vocal", "main vox", "lead vox",
    "coro", "cori", "voci", "cantato", "canto", "voce", "voz", "voces",
    "voix", "stimme", "gesang", "corista", "coristi",
)
# Voice-type / delivery hints (voice_type attribute). Word-boundary matched:
# "rap" must not fire inside "trap", "mix" not inside "remix", "head" not
# inside "headroom", "chest" not inside "orchestra".
VOICE_TYPE_HINTS = {
    "whisper": ("whisper", "whispered", "sussurro", "sussurrato"),
    "scream": ("scream", "screaming", "screamo", "urlo", "urlato"),
    "growl": ("growl", "growling", "growls", "grugnito"),
    "belt": ("belt", "belted", "belting"),
    "head": ("head voice", "headvoice", "head vox", "testa"),
    "chest": ("chest voice", "chestvoice", "chest vox", "petto"),
    "mix": ("mix voice", "mixvoice", "mixed voice", "voce mista"),
    "fry": ("vocal fry", "fry", "fry voice"),
    "breathy": ("breathy", "breath", "breathiness", "soffiato", "sospirato"),
    "raspy": ("raspy", "rasp", "raspiness", "rauco", "rauca"),
    "spoken": ("spoken", "spoken word", "parlato", "recitato"),
    "rap": ("rap", "rapped", "rapping", "ragga", "flow"),
}
# Instrumental markers: a stem that is explicitly the instrumental/karaoke/
# backing-track version of the song. These are role="other" (not a vocal),
# and are matched word-boundary so "base" never fires inside "database" and
# "stem" never inside "system".
INSTRUMENTAL_MARKERS = (
    "instrumental", "instrumentale", "strumentale", "inst", "karaoke",
    "playback", "backing track", "backingtrack", "minus one", "minusone",
    "base", "basi", "stem", "stems", "solo instrumental", "no vocals",
    "senza voce", "senza voci", "versione strumentale",
)
# Drum sub-roles (role == "drums"). "oh"/"hh"/"clap" already live in the OFF
# DRUM_WORD_HINTS; these are the multi-mic / production additions. All
# word-boundary matched ("snap" must not fire inside "snapshot", "room" not
# inside "bathroom").
DRUM_SUBROLE_HINTS = (
    "kick in", "kick out", "kickin", "kickout", "snare top", "snare btm",
    "snare bottom", "snaretop", "snarebtm", "snare bot", "oh l", "oh r",
    "overhead l", "overhead r", "room", "amb", "ambience", "ambient mic",
    "clap", "claps", "snap", "snaps", "rimshot", "rim shot", "ghost",
    "ghost note", "ghostnote", "top snare", "bottom snare", "side stick",
    "cross stick", "hi hat", "hihat", "hat", "ride", "crash", "tom", "toms",
    "floor tom", "rack tom", "china", "splash", "shaker", "tambourine",
    "cowbell", "perc", "percussion", "batteria", "cassa", "rullante",
    "grancassa", "timpani", "timpano",
)
# Bass aliases (role == "bass"). "808"/"bass"/"sub"/"bajo"/"basse" already
# live in the OFF BASS_ROLE_HINTS; these are the additions. Word-boundary
# matched so "sub" never fires inside "subway"/"subject".
BASS_ROLE_HINTS_V2 = (
    "sub bass", "subbass", "sub-bass", "bassline", "bass line", "bass guitar",
    "bass gtr", "bass synth", "synth bass", "reese bass", "wobble bass",
    "contrabbasso", "contrabajo", "basso elettrico", "bajo electrico",
    "baixo", "baixo elétrico", "bass guitar", "e-bass", "ebass",
)
# Take-layer additions (layer == "double"). "double"/"backing"/"harmony"/
# "harmonies"/"coro"/"cori" already live in the OFF DOUBLE hints; these are
# the producer-slang additions. Word-boundary matched ("stack" must not fire
# inside "stacked" is fine -- "stacked" is a double too -- but "dub" must not
# fire inside "dubstep").
DOUBLE_HINTS_V2 = (
    "bgv", "bgvs", "bkg", "backing", "back vox", "backvox", "harmony",
    "harmonies", "harm", "harms", "stack", "stacks", "stacked", "dub",
    "dubs", "adlib", "adlibs", "ad-lib", "ad-libs", "comp", "comps",
    "comped", "vocal comp", "vox comp", "coro", "cori", "corista", "coristi",
    "doppia", "doppie", "doppiaggio",
)


def _v2_enabled() -> bool:
    """True when ENABLE_RECOGNITION_V2 is on. Wrapped so a config failure can
    never break parsing -- an exception here degrades to the frozen OFF path."""
    try:
        return config.is_enabled("ENABLE_RECOGNITION_V2")
    except Exception:
        return False

_DX_PATTERN = re.compile(r"(?:^|[\s_./\\(){}\[\]-])dx(?:[\s_./\\(){}\[\]-]|$)", re.IGNORECASE)
_SX_PATTERN = re.compile(r"(?:^|[\s_./\\(){}\[\]-])sx(?:[\s_./\\(){}\[\]-]|$)", re.IGNORECASE)

# Explicit-center tokens: "Center"/"Centre"/"Mono" say "this belongs dead
# center" out loud, so they're honored as 0.0 even if some other token in the
# name might otherwise suggest a side.
_CENTER_PATTERN = re.compile(
    r"(?:^|[\s_./\\(){}\[\]-])(?:center|centre|mono)(?:[\s_./\\(){}\[\]-]|$)", re.IGNORECASE
)

# Link-group tokens: mark one member of a multi-mic/multi-take pair (e.g.
# "Kick_In.wav" + "Kick_Out.wav", "Synth_Pad_L.wav" + "Synth_Pad_R.wav").
# Word-boundary matched exactly like DX/SX/R/L above, for the same reason:
# "in"/"out"/"top"/"bottom" are common English words and would false-positive
# as plain substrings (e.g. "Outro", "Piano", "Bottomless_Pad") if not
# bounded to a standalone token. "oh"/"a"/"b" are deliberately NOT link
# tokens -- too short/ambiguous to add without a collision test proving they
# don't misfire on ordinary names.
_LINK_TOKEN_PATTERN = re.compile(
    r"(?:^|[\s_./\\(){}\[\]-])"
    r"(dx|sx|r|right|l|left|in|out|top|bottom|close|far|near|mic1|mic2|amp|front|back|di)"
    r"(?:[\s_./\\(){}\[\]-]|$)",
    re.IGNORECASE,
)
# English R/L convention (as common as dx/sx in practice, especially for
# doubles/harmonies exported by non-Italian DAW templates: "Double_R.wav",
# "Harmony (L).wav"). Single-letter tokens are dangerous as a plain
# substring (would match "r" or "l" inside almost anything), so these are
# matched the same word-boundary way as dx/sx -- only a standalone "r"/"l"
# token bounded by a separator or the start/end of the string counts, never
# a letter inside a longer word.
_R_PATTERN = re.compile(r"(?:^|[\s_./\\(){}\[\]-])(?:r|right)(?:[\s_./\\(){}\[\]-]|$)", re.IGNORECASE)
_L_PATTERN = re.compile(r"(?:^|[\s_./\\(){}\[\]-])(?:l|left)(?:[\s_./\\(){}\[\]-]|$)", re.IGNORECASE)
# Numbered take variants ("L1", "R1", "L100", "R100") -- the plain R/L
# patterns above require a separator/end right after the letter, so a digit
# suffix would otherwise be invisible.
_R_NUM_PATTERN = re.compile(r"(?:^|[\s_./\\(){}\[\]-])(?:r|right)\d+(?:[\s_./\\(){}\[\]-]|$)", re.IGNORECASE)
_L_NUM_PATTERN = re.compile(r"(?:^|[\s_./\\(){}\[\]-])(?:l|left)\d+(?:[\s_./\\(){}\[\]-]|$)", re.IGNORECASE)

# Leading DAW track numbers ("01_Kick", "02 - Snare", "01Kick") are stripped
# for hint matching only -- the stored raw_name and link_id still see the
# original string. The separator/lookahead requirement is what keeps a bare
# "808" (a real bass instrument name) from being stripped to nothing.
_DAW_PREFIX_PATTERN = re.compile(r"^\s*\d+(?:[\s_\-\.]+|(?=[A-Za-z]))")


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    """Thin wrapper over textmatch.contains_any (substring, case-insensitive)
    -- kept as a named function so existing callers/imports don't break."""
    return _tm_contains_any(text, tokens)


def _contains_word(text: str, tokens: tuple[str, ...]) -> bool:
    """Same as _contains_any, but requires each token to be its own word
    (bounded by start/end-of-string or a separator) rather than matching
    anywhere as a bare substring. BASS_ROLE_HINTS needs this: "bass" is a
    real, common role hint, but it's also the first four letters of "Bassa"
    (Italian for a low vocal register, confirmed in a real session's file
    "Db. Bassa" -- a vocal double, misrouted to role=bass entirely because
    of this). Bass instrument filenames are always their own standalone
    word in practice ("Bass DI.wav", "808.wav"), so this loses nothing.

    Thin wrapper over textmatch.contains_word -- same boundary regex, same
    case-insensitivity, same re.escape of each token."""
    return _tm_contains_word(text, tokens)


def _camel_word_pattern(token: str) -> str:
    """Word-boundary pattern that also treats a camelCase transition and a
    trailing digit as boundaries. Needed for compound take names the real
    sessions use: "FalsettoStr1" must still match "falsetto"/"str" and
    "LowRit" must still match "low"/"rit", while "strong"/"street"/"spirit"/
    "slow" must NOT match "str"/"rit"/"low". A plain word boundary can't do
    both (the token is glued to a letter on one side in every case), so the
    start boundary additionally accepts a lowercase->uppercase transition
    (the token itself capitalized) and the end boundary additionally accepts
    a digit or an uppercase letter."""
    escaped = re.escape(token.lower())
    first_upper = re.escape(token[0].upper())
    # The camelCase transition and the trailing-uppercase boundary must stay
    # case-SENSITIVE even though the token itself is matched with
    # re.IGNORECASE -- otherwise "(?=R)" would also match a lowercase "r"
    # and "[A-Z]" would match any letter, re-introducing the exact
    # "str"->"strong"/"rit"->"spirit" false positives this exists to stop.
    start = rf"(?:^|{_SEP_CLASS}|(?<=[a-z])(?=(?-i:{first_upper})))"
    end = rf"(?={_SEP_CLASS}|$|\d|(?-i:[A-Z]))"
    return start + escaped + end


def _contains_camel_word(text: str, tokens: tuple[str, ...]) -> bool:
    """Word-boundary match with camelCase/digit awareness (see
    _camel_word_pattern). Used for section/register hints, whose tokens
    appear glued to a register word in real take names ("FalsettoStr1",
    "LowRit")."""
    return any(re.search(_camel_word_pattern(token), text, re.IGNORECASE) is not None for token in tokens)


def _first_match(text: str, hint_groups: dict[str, tuple[str, ...]], matcher=_contains_any) -> str | None:
    for name, tokens in hint_groups.items():
        if matcher(text, tokens):
            return name
    return None


def _count_word_matches(text: str, tokens: tuple[str, ...]) -> int:
    """How many of `tokens` appear as standalone words in `text`. Used by the
    V2 confidence model: independent agreeing tokens raise confidence."""
    return sum(1 for token in tokens if _contains_word(text, (token,)))


def _count_any_matches(text: str, tokens: tuple[str, ...]) -> int:
    """How many of `tokens` appear as substrings in `text` (V2 confidence)."""
    return sum(1 for token in tokens if _contains_any(text, (token,)))


def _scored_role(text: str) -> tuple[str, float]:
    """V2 role classification with a graduated confidence in [0, 1].

    Priority order matches the OFF path (bass -> drums -> vocal -> other) so
    a name that already classified correctly keeps its role; only the
    confidence becomes a real score instead of the binary 1.0/0.3.

    Confidence is driven by how many independent agreeing tokens matched and
    how specific they are (a multi-word phrase is stronger evidence than a
    bare 3-letter abbreviation). It is deliberately capped below 1.0 for a
    single weak token, so "Vocal" (one generic token) scores lower than
    "Backing Vocal" (two agreeing tokens)."""
    bass = _count_word_matches(text, BASS_ROLE_HINTS) + _count_word_matches(text, BASS_ROLE_HINTS_V2)
    drums = (
        _count_word_matches(text, DRUM_ROLE_HINTS)
        + _count_any_matches(text, DRUM_SUBSTR_HINTS)
        + _count_word_matches(text, DRUM_WORD_HINTS)
        + _count_word_matches(text, DRUM_SUBROLE_HINTS)
    )
    vocal = (
        _count_any_matches(text, VOCAL_ROLE_HINTS)
        + _count_word_matches(text, VOCAL_WORD_HINTS)
        + _count_word_matches(text, VOCAL_ROLE_HINTS_V2)
    )

    if bass:
        return "bass", _confidence_from_count(bass)
    if drums:
        return "drums", _confidence_from_count(drums)
    if vocal:
        return "vocal", _confidence_from_count(vocal)
    return "other", 0.3


def _confidence_from_count(count: int) -> float:
    """Maps an agreeing-token count to a confidence in [0.55, 0.99].

    One token -> 0.55 (a real but single signal), two -> 0.75, three -> 0.87,
    four+ -> approaching 0.99. Never reaches 1.0: a filename is strong
    evidence, not proof, and the fusion layer reserves the top of the range
    for name+audio agreement."""
    if count <= 0:
        return 0.3
    return float(min(0.99, 0.55 + 0.20 * math.log2(count + 1)))


def _scored_layer(text: str) -> str:
    """V2 layer classification (primary | double). Same priority as the OFF
    path, extended with the V2 double vocabulary."""
    if (
        _contains_any(text, DOUBLE_HINTS)
        or _contains_word(text, DOUBLE_WORD_HINTS)
        or _contains_word(text, DOUBLE_HINTS_V2)
        or _DB_LAYER_PATTERN.search(text)
    ):
        return "double"
    return "primary"


def _voice_type(text: str) -> str | None:
    """V2 voice-type/delivery classification (whisper/scream/rap/...), or
    None when no delivery hint is present. Word-boundary matched so "rap"
    never fires inside "trap" and "mix" never inside "remix"."""
    for name, tokens in VOICE_TYPE_HINTS.items():
        if _contains_word(text, tokens):
            return name
    return None


def _pan_from_name(text: str) -> float:
    if _CENTER_PATTERN.search(text):
        return 0.0
    if _DX_PATTERN.search(text) or _R_PATTERN.search(text) or _R_NUM_PATTERN.search(text):
        return 0.8
    if _SX_PATTERN.search(text) or _L_PATTERN.search(text) or _L_NUM_PATTERN.search(text):
        return -0.8
    return 0.0


def _link_id_from_name(path_like: str) -> str | None:
    """Groups multi-mic/multi-take stems (e.g. "Kick_In.wav" + "Kick_Out.wav",
    "Synth_Pad_L.wav" + "Synth_Pad_R.wav") so mixengine.py can apply
    identical DSP decisions to every member -- summing the same instrument
    processed with different filter phase responses is a common source of
    comb-filtering when stems are otherwise treated as fully independent.
    Only the filename itself is used (not the folder path, which frequently
    contains its own unrelated "in"/"out"-shaped words -- e.g. "Vocal Stems
    Pitch Correction"), and only the LAST matching token is stripped, so a
    name like "Bottom_Snare_Top.wav" groups on "Bottom_Snare" only via its
    trailing token, not an earlier coincidental one. Returns None when no
    grouping token is present -- most stems aren't part of any pair, and
    should be processed exactly as before."""
    basename = path_like.replace("\\", "/").rsplit("/", 1)[-1]
    stem_name = basename.rsplit(".", 1)[0] if "." in basename else basename
    matches = list(_LINK_TOKEN_PATTERN.finditer(stem_name))
    if not matches:
        return None
    last = matches[-1]
    group_key = (stem_name[: last.start()] + stem_name[last.end() :]).strip(" _-./\\")
    if not group_key:
        return None
    return group_key.lower()


@dataclass
class StemDescriptor:
    raw_name: str
    role: str                    # vocal | bass | drums | other
    layer: str = "primary"       # primary | double  (only meaningful when role == vocal)
    pan: float = 0.0             # -1 (hard left/sx) .. +1 (hard right/dx)
    section: str | None = None   # chorus | verse | bridge | ... | None
    register: str | None = None  # falsetto | low | mid | special | None
    role_confidence: float = 1.0  # 1.0 = a role hint matched the name; lower = "other" by default, no real signal
    link_id: str | None = None   # shared key for stems that are mic/take pairs of the same source (see _link_id_from_name)
    # Recognition V2 only (None on the frozen OFF path): the vocal delivery /
    # voice type read from the name (whisper | scream | growl | belt | head |
    # chest | mix | fry | breathy | raspy | spoken | rap), or None.
    voice_type: str | None = None


def parse_stem(path_like: str) -> StemDescriptor:
    text = path_like.replace("\\", "/")
    # Hint matching runs on the name with any leading DAW track number
    # stripped ("01_Kick" -> "Kick"); raw_name/link_id keep the original.
    hint_text = _DAW_PREFIX_PATTERN.sub("", text, count=1)

    if _v2_enabled():
        return _parse_stem_v2(path_like, hint_text)

    if _contains_word(hint_text, BASS_ROLE_HINTS):
        role = "bass"
        role_confidence = 1.0
    elif (
        _contains_word(hint_text, DRUM_ROLE_HINTS)
        or _contains_any(hint_text, DRUM_SUBSTR_HINTS)
        or _contains_word(hint_text, DRUM_WORD_HINTS)
    ):
        role = "drums"
        role_confidence = 1.0
    elif _contains_any(hint_text, VOCAL_ROLE_HINTS) or _contains_word(hint_text, VOCAL_WORD_HINTS):
        role = "vocal"
        role_confidence = 1.0
    else:
        # No naming hint at all -- role defaults to "other" with low
        # confidence, which is exactly the signal the LLM advisory fallback
        # (llm_classifier.py, gated by ENABLE_LLM_ADVISORY) looks for.
        role = "other"
        role_confidence = 0.3

    layer = (
        "double"
        if _contains_any(hint_text, DOUBLE_HINTS)
        or _contains_word(hint_text, DOUBLE_WORD_HINTS)
        or _DB_LAYER_PATTERN.search(hint_text)
        else "primary"
    )
    # Was gated to `layer == "double"` only -- a dx/sx hint in an
    # instrumental stem's name (e.g. "Chitarra_dx.wav") was silently
    # ignored and the stem defaulted to dead center, along with every other
    # "other"-role stem (mixengine.py had no panning logic for them at all).
    # The dx/sx convention is generic, not vocal-specific, so honor it for
    # any stem that has it.
    pan = _pan_from_name(hint_text)

    # Section/register (verse/chorus, falsetto/low/mid...) only mean anything
    # for vocal takes. Gating on role also avoids false positives like "STR"
    # inside "INSTRUMENTAL" being misread as a verse-section hint.
    section = _first_match(hint_text, SECTION_HINTS, _contains_camel_word) if role == "vocal" else None
    register = _first_match(hint_text, REGISTER_HINTS, _contains_camel_word) if role == "vocal" else None

    return StemDescriptor(
        raw_name=path_like,
        role=role,
        layer=layer,
        pan=pan,
        section=section,
        register=register,
        role_confidence=role_confidence,
        link_id=_link_id_from_name(path_like),
    )


def _parse_stem_v2(path_like: str, hint_text: str) -> StemDescriptor:
    """Recognition V2 parse: same filename-first design as parse_stem, but
    with the expanded multilingual lexicon, a graduated role confidence, and
    a voice-type read. Never raises -- any unexpected failure degrades to the
    frozen OFF result rather than aborting a render."""
    try:
        role, role_confidence = _scored_role(hint_text)
        # A delivery/voice-type token ("Whisper", "Scream", "Rap", "Belt"...)
        # is itself strong evidence of a vocal take even when no explicit
        # vocal role word is present -- promote role to vocal and fold the
        # delivery token into the confidence (it is one more agreeing signal).
        voice_type = _voice_type(hint_text)
        if voice_type is not None and role == "other":
            role = "vocal"
            role_confidence = _confidence_from_count(1)
        layer = _scored_layer(hint_text)
        pan = _pan_from_name(hint_text)
        # Section/register only mean anything for vocal takes (same gating as
        # the OFF path -- avoids "STR" inside "INSTRUMENTAL").
        if role == "vocal":
            section = _first_match(hint_text, SECTION_HINTS, _contains_camel_word)
            register = _first_match(hint_text, REGISTER_HINTS, _contains_camel_word)
        else:
            section = None
            register = None
            voice_type = None
        return StemDescriptor(
            raw_name=path_like,
            role=role,
            layer=layer,
            pan=pan,
            section=section,
            register=register,
            role_confidence=role_confidence,
            link_id=_link_id_from_name(path_like),
            voice_type=voice_type,
        )
    except Exception:
        # Graceful ladder: an unexpected failure in the richer path must not
        # take down a render -- fall back to the frozen OFF parse.
        return _parse_stem_off(path_like)


def _parse_stem_off(path_like: str) -> StemDescriptor:
    """The frozen OFF-path parse, callable directly (used as the V2 safety
    fallback without recursing through the flag check)."""
    text = path_like.replace("\\", "/")
    hint_text = _DAW_PREFIX_PATTERN.sub("", text, count=1)
    if _contains_word(hint_text, BASS_ROLE_HINTS):
        role, role_confidence = "bass", 1.0
    elif (
        _contains_word(hint_text, DRUM_ROLE_HINTS)
        or _contains_any(hint_text, DRUM_SUBSTR_HINTS)
        or _contains_word(hint_text, DRUM_WORD_HINTS)
    ):
        role, role_confidence = "drums", 1.0
    elif _contains_any(hint_text, VOCAL_ROLE_HINTS) or _contains_word(hint_text, VOCAL_WORD_HINTS):
        role, role_confidence = "vocal", 1.0
    else:
        role, role_confidence = "other", 0.3
    layer = (
        "double"
        if _contains_any(hint_text, DOUBLE_HINTS)
        or _contains_word(hint_text, DOUBLE_WORD_HINTS)
        or _DB_LAYER_PATTERN.search(hint_text)
        else "primary"
    )
    pan = _pan_from_name(hint_text)
    section = _first_match(hint_text, SECTION_HINTS, _contains_camel_word) if role == "vocal" else None
    register = _first_match(hint_text, REGISTER_HINTS, _contains_camel_word) if role == "vocal" else None
    return StemDescriptor(
        raw_name=path_like, role=role, layer=layer, pan=pan, section=section,
        register=register, role_confidence=role_confidence,
        link_id=_link_id_from_name(path_like),
    )
