"""Every value an LLM suggests (a stem's bus category, or in Director Mode a
DSP parameter tweak) passes through here before it can touch the engine. An
LLM can hallucinate a category that doesn't exist or a gain of +15dB; this
module never trusts that at face value — it validates against a strict
schema and, for anything with a known safe range, clamps into that range
instead of rejecting the whole suggestion outright."""

from __future__ import annotations

from .llm_classifier import BUS_CATEGORIES

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
}

def validate_classification(suggestion: dict) -> dict:
    """Drops any entry that isn't {stem_name: valid_category} — used for the
    naming-fallback advisory path. Returns only the entries that survived
    validation; never raises, since a hallucinated category is an expected,
    not exceptional, case for a small local model."""
    return {
        name: category
        for name, category in suggestion.items()
        if isinstance(name, str) and category in BUS_CATEGORIES
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
