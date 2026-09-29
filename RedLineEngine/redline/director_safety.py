"""Every value an LLM suggests (a stem's bus category, or in Director Mode a
DSP parameter tweak) passes through here before it can touch the engine. An
LLM can hallucinate a category that doesn't exist or a gain of +15dB; this
module never trusts that at face value — it validates against a strict
schema and, for anything with a known safe range, clamps into that range
instead of rejecting the whole suggestion outright."""

from __future__ import annotations

from .llm_classifier import BUS_CATEGORIES
from .naming import SECTION_HINTS, _contains_word

# Known DSP parameters an LLM might plausibly suggest (Director Mode), and
# the safe range each is clamped to — these mirror the guardrails already
# used elsewhere in the engine (see DSP_ENGINE_SPECS.md and masterengine.py's
# own +/-12dB gain clamp), so an LLM suggestion can never exceed what a
# human-authored preset would already be limited to.
PARAM_RANGES: dict[str, tuple[float, float]] = {
    "gain_db": (-12.0, 12.0),
    "eq_gain_db": (-6.0, 6.0),
    "compressor_ratio": (1.0, 20.0),
    "compressor_threshold_db": (-40.0, 0.0),
    "reverb_send": (0.0, 1.0),
    "pan": (-1.0, 1.0),
    # Wizard knobs an LLM may nudge from a free-text creative brief
    # (llm_classifier.interpret_creative_brief) -- same ranges the wizard's
    # own sliders already enforce, so a brief can never push these further
    # than a human using the sliders directly already could.
    "aggressiveness": (1.0, 5.0),
    "warmth": (-1.0, 1.0),
    "vocal_prominence": (-1.0, 1.0),
}

def validate_classification(suggestion: dict, allowed_names: set[str] | None = None) -> dict:
    """Drops any entry that isn't {stem_name: valid_category} — used for the
    naming-fallback advisory path. Returns only the entries that survived
    validation; never raises, since a hallucinated category is an expected,
    not exceptional, case for a small local model.

    `allowed_names`, if given, additionally drops any suggestion whose key
    isn't one of the stem names actually asked about -- confirmed necessary
    in practice: the model has been observed echoing back a literal
    "categoria" key instead of the real stem name, which would otherwise
    silently reclassify a stem nobody asked it to."""
    return {
        name: category
        for name, category in suggestion.items()
        if isinstance(name, str)
        and category in BUS_CATEGORIES
        and (allowed_names is None or name in allowed_names)
    }


def clamp_params(suggestion: dict) -> tuple[dict, list[str]]:
    """Clamps every recognized numeric field in `suggestion` into its safe
    range from PARAM_RANGES. Unrecognized fields are dropped rather than
    passed through blind (an LLM inventing a parameter name is exactly the
    hallucination case this exists to catch). Returns (clamped_dict,
    corrections) where corrections is a human-readable log of every value
    that had to be pulled back into range."""
    clamped: dict = {}
    corrections: list[str] = []

    for key, value in suggestion.items():
        if key not in PARAM_RANGES:
            corrections.append(f"'{key}' ignorato (parametro sconosciuto/non sicuro)")
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            corrections.append(f"'{key}' ignorato (valore non numerico: {value!r})")
            continue

        lo, hi = PARAM_RANGES[key]
        clamped_value = max(lo, min(hi, numeric))
        if clamped_value != numeric:
            corrections.append(f"'{key}': {numeric} -> {clamped_value} (fuori range sicuro [{lo}, {hi}])")
        clamped[key] = clamped_value

    return clamped, corrections


EQ_TYPES = ("bell", "high_shelf")
MAX_EQ_ADJUSTMENTS = 4
FREQ_RANGE_HZ = (20.0, 20000.0)

# Confirmed necessary in practice: asked something with nothing to do with
# audio at all ("che tempo fa a Milano?", "boh, fai te", a prompt-injection
# attempt, even literal gibberish), the model doesn't refuse -- it falls
# back to a generic small EQ nudge almost every time instead of recognizing
# "this isn't a real request". Range-clamping and the section-type check
# don't catch this (the fallback nudge is small and section-agnostic, i.e.
# "safe" by every check so far but not actually related to what was
# written). This is the last gate: at least one acoustic-dictionary term
# must appear in the request, or the whole suggestion is rejected.
#
# Also accepts the same color/element metaphor vocabulary Module 1
# (interpret_creative_brief) already treats as real mixing language --
# "il colore del suono in blu elettrico" or "incendia il ritornello" are
# genuine (if metaphorical) requests, not nonsense, and rejecting them here
# while Module 1 accepts the identical words would just be an inconsistency
# between the two features, not an actual safety improvement. A metaphor
# with no entry in _COLOR_TO_SECTION_EQ_HINTS (llm_classifier.py) --
# "suona come un elefante che vola nello spazio" -- still has nothing to
# translate to and is still rejected, just for the correct reason (no
# acoustic *or* metaphorical mapping exists), not merely "no literal term".
_ACOUSTIC_RELEVANCE_KEYWORDS = (
    "cald", "corpo", "pien", "aperto", "aria", "cristallin",
    "presenz", "avanti", "protagonist", "nasale", "inscatolat",
    "eq", "frequenz", "acut", "grav", "brillante", "scur", "basso", "bassi",
    # Color/element metaphors (mirrors llm_classifier._BRIEF_RELEVANCE_KEYWORDS)
    "viola", "oro", "dorat", "ambra", "marrone", "ghiacc", "gelo", "blu",
    "acciaio", "argent", "metallic", "colore",
    "fuoco", "incendi", "brucia", "fiamma", "esplo", "rosso", "nero",
    "eter", "sognante", "nuvola",
)


def _mentions_acoustic_term(user_text: str) -> bool:
    lowered = user_text.lower()
    return any(kw in lowered for kw in _ACOUSTIC_RELEVANCE_KEYWORDS)


def _section_type(name: str) -> str | None:
    """"chorus_1" -> "chorus", "verse_3" -> "verse", "intro" -> "intro"."""
    for section_type in list(SECTION_HINTS.keys()) + ["intro"]:
        if name.startswith(section_type):
            return section_type
    return None


def _mentioned_section_type(user_text: str) -> str | None:
    """Which section type (if any) the user's own text names -- reuses
    naming.py's existing SECTION_HINTS keyword lists (chorus/verse/bridge)
    instead of a second, separately-maintained keyword list.

    Matched with naming._contains_word (word-boundary), not a bare
    substring: SECTION_HINTS' short tokens ("str", "rit") are prefixes of
    unrelated words -- "strumentale" contains "str" and "ritmo" contains
    "rit", so a plain `in` check misread an instrumental/rhythm request as
    naming a verse/chorus section."""
    for section_type, keywords in SECTION_HINTS.items():
        if _contains_word(user_text, keywords):
            return section_type
    return None


def validate_dsp_automation(
    suggestion: dict, structure_map: list[dict], total_duration_sec: float, user_text: str | None = None
) -> dict | None:
    """Validates a Module 2 (NLP-to-DSP) LLM suggestion against the known
    song structure. Returns None if the suggestion is too malformed to act
    on at all (missing target_section, no valid eq_adjustments) -- callers
    must treat that as "make no change" rather than guessing.

    Critically, `time_range` is never taken from the LLM's own JSON --
    it's looked up directly from `structure_map` (or the full song for
    "global"). An LLM inventing a plausible-looking [45.0, 75.0] that
    doesn't actually match any real section boundary is exactly the kind
    of hallucination range-clamping alone can't catch, since the numbers
    themselves are "in range"; this sidesteps the problem entirely by
    trusting the measured structure, not the model's echo of it.

    If `user_text` is given, also cross-checks the section *type* the user
    actually named (chorus/verse/bridge, via naming.py's SECTION_HINTS)
    against the model's chosen target_section -- confirmed necessary in
    practice: asked to fix "the verse", the model picked "chorus_1"
    instead, a wrong-section mistake plain range-clamping can't catch since
    chorus_1 is a perfectly valid, in-range section name. Applying a change
    to the wrong section is worse than doing nothing, so a mismatch here
    rejects the whole suggestion rather than silently "correcting" it."""
    if not isinstance(suggestion, dict):
        return None

    if user_text is not None and not _mentions_acoustic_term(user_text):
        return None  # not a request about audio at all -- reject rather than apply a generic fallback nudge

    target_section = suggestion.get("target_section")
    if target_section == "global":
        time_range = (0.0, float(total_duration_sec))
    elif isinstance(target_section, str):
        match = next((s for s in structure_map if s["name"] == target_section), None)
        if match is None:
            return None  # hallucinated a section name that doesn't exist
        if user_text is not None:
            mentioned = _mentioned_section_type(user_text)
            chosen = _section_type(target_section)
            if mentioned is not None and chosen is not None and mentioned != chosen:
                return None  # e.g. user said "verse", model picked a chorus section
        time_range = (float(match["start"]), float(match["end"]))
    else:
        return None

    raw_updates = suggestion.get("dsp_updates")
    if not isinstance(raw_updates, dict):
        return None

    eq_adjustments = []
    for adj in raw_updates.get("eq_adjustments", []) or []:
        if not isinstance(adj, dict):
            continue
        eq_type = adj.get("type")
        if eq_type not in EQ_TYPES:
            continue
        try:
            freq = float(adj["freq"])
            gain_db = float(adj["gain_db"])
        except (KeyError, TypeError, ValueError):
            continue

        freq = max(FREQ_RANGE_HZ[0], min(FREQ_RANGE_HZ[1], freq))
        lo, hi = PARAM_RANGES["eq_gain_db"]
        gain_db = max(lo, min(hi, gain_db))
        eq_adjustments.append({"type": eq_type, "freq": freq, "gain_db": gain_db})
        if len(eq_adjustments) >= MAX_EQ_ADJUSTMENTS:
            break

    if not eq_adjustments:
        return None  # nothing safe/valid survived -- treat as no-op, not a partial automation

    feedback = suggestion.get("ui_feedback_message")
    if not isinstance(feedback, str):
        feedback = ""

    return {
        "target_section": target_section,
        "time_range": time_range,
        "eq_adjustments": eq_adjustments,
        "ui_feedback_message": feedback[:300],
    }
