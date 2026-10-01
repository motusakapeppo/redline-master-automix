"""Sub-bus routing for vocal doubles/stacks, by register.

A wall of doubles (harmonies, octaves, falsettos) turns into mush unless each
register gets a genuinely different treatment before they're summed — this
is the "matrioska" routing: each double is classified by its own measured
pitch relative to the lead (not just trusted from its file name, which might
just say "doppia_1", "doppia_2"), routed into one of four register sub-buses,
processed with that register's specific recipe, then the sub-buses are
combined into one Backing Vocals bus with a final light glue pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import config
from .textmatch import contains_word

LOW = "low"
UNISON = "unison"
HIGH = "high"
FALSETTO = "falsetto"

# Ratio of a double's fundamental to the lead's fundamental. Approximate —
# real singing isn't a pure ratio, but this is a reasonable, cheap proxy for
# "roughly an octave down" / "same note" / "harmonizing above" / "very high
# and thin" without needing a full harmonic-richness analyzer.
_LOW_MAX_RATIO = 0.75
_UNISON_MAX_RATIO = 1.15
_HIGH_MAX_RATIO = 1.8

# A genuine falsetto/high take concentrates real energy up high. If the pitch
# ratio *says* falsetto but the actual high-frequency energy ratio is below
# this, the "high" f0 is almost certainly a pitch octave error (a
# sub-harmonic read as the fundamental, or vice versa) — so we don't trust it
# and down-rank the classification. This is the spectral cross-check that
# catches octave errors pYIN doesn't.
_FALSETTO_MIN_HF_RATIO = 0.06
_HIGH_MIN_HF_RATIO = 0.03


def classify_register(double_f0: float, lead_f0: float, hf_ratio: float | None = None) -> str:
    """Classify a double's register from its pitch relative to the lead.

    `hf_ratio` (fraction of the take's energy above ~3.5kHz, from
    pitch.high_frequency_ratio) is an optional spectral sanity check: a
    high/falsetto classification is only trusted if there's actually HF
    energy to back it up, guarding against pitch octave errors."""
    if lead_f0 <= 1.0 or double_f0 <= 1.0:
        return UNISON
    ratio = double_f0 / lead_f0

    if ratio < _LOW_MAX_RATIO:
        return LOW
    if ratio > _HIGH_MAX_RATIO:
        # Only believe "falsetto" if the spectrum agrees; otherwise the high
        # f0 is a likely octave error — treat it as a normal-range take.
        if hf_ratio is None or hf_ratio >= _FALSETTO_MIN_HF_RATIO:
            return FALSETTO
        return HIGH if (hf_ratio >= _HIGH_MIN_HF_RATIO) else UNISON
    if ratio > _UNISON_MAX_RATIO:
        if hf_ratio is None or hf_ratio >= _HIGH_MIN_HF_RATIO:
            return HIGH
        return UNISON
    return UNISON


def _v2_enabled() -> bool:
    """True when ENABLE_RECOGNITION_V2 is on. Wrapped so a config failure can
    never break register classification -- degrades to the frozen path."""
    try:
        return config.is_enabled("ENABLE_RECOGNITION_V2")
    except Exception:
        return False


def classify_register_scored(
    double_f0: float, lead_f0: float, hf_ratio: float | None = None
) -> tuple[str, float]:
    """Recognition V2 register classification returning (register, confidence).

    Same relative low/unison/high/falsetto model as classify_register (the
    musically-correct one for this engine -- no invented baritone/tenor
    taxonomy), but with a graduated confidence in [0, 1]:

    - confidence rises the further the pitch ratio sits from a decision
      boundary (a ratio of 0.50 is a much more certain "low" than 0.727);
    - when hf_ratio is supplied and agrees with a high/falsetto call, the
      confidence is boosted; when it contradicts (a likely octave error) the
      classification is down-ranked exactly as the OFF path does, and the
      confidence is lowered accordingly.

    Never raises -- silence / degenerate input returns (UNISON, low conf)."""
    try:
        if lead_f0 <= 1.0 or double_f0 <= 1.0:
            return UNISON, 0.3
        ratio = double_f0 / lead_f0

        if ratio < _LOW_MAX_RATIO:
            # Distance below the low boundary, normalized by the boundary.
            margin = (_LOW_MAX_RATIO - ratio) / _LOW_MAX_RATIO
            return LOW, float(min(0.95, 0.55 + 0.40 * margin))

        if ratio > _HIGH_MAX_RATIO:
            if hf_ratio is None or hf_ratio >= _FALSETTO_MIN_HF_RATIO:
                # Genuine falsetto: confidence scales with the HF evidence.
                hf = 0.5 if hf_ratio is None else min(1.0, hf_ratio / 0.20)
                return FALSETTO, float(min(0.95, 0.6 + 0.35 * hf))
            # Octave-error guard: the pitch says falsetto but the spectrum
            # disagrees -- down-rank exactly like the OFF path.
            if hf_ratio >= _HIGH_MIN_HF_RATIO:
                return HIGH, 0.4
            return UNISON, 0.3

        if ratio > _UNISON_MAX_RATIO:
            if hf_ratio is None or hf_ratio >= _HIGH_MIN_HF_RATIO:
                # Distance above the unison boundary, normalized.
                margin = (ratio - _UNISON_MAX_RATIO) / (_HIGH_MAX_RATIO - _UNISON_MAX_RATIO)
                return HIGH, float(min(0.9, 0.55 + 0.35 * margin))
            return UNISON, 0.35

        # Unison: confidence rises the closer the ratio is to 1.0.
        margin = 1.0 - abs(ratio - 1.0)
        return UNISON, float(min(0.95, 0.55 + 0.40 * max(0.0, margin)))
    except Exception:
        return UNISON, 0.3


# Voice-type / delivery vocabulary (Recognition V2). Word-boundary matched so
# "rap" never fires inside "trap", "mix" never inside "remix", "head" never
# inside "headroom", "chest" never inside "orchestra".
_VOICE_TYPE_HINTS: dict[str, tuple[str, ...]] = {
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


def classify_voice_type(name: str) -> tuple[str | None, float]:
    """Recognition V2 voice-type/delivery classification from a stem name.

    Returns (voice_type, confidence) where voice_type is one of whisper |
    scream | growl | belt | head | chest | mix | fry | breathy | raspy |
    spoken | rap, or None when no delivery hint is present. Word-boundary
    matched throughout, so "Trap"/"Remix"/"Headroom"/"Orchestra" never fire.
    Never raises. OFF (default) returns (None, 0.0) -- voice type is a V2-only
    concept, so the frozen path is untouched."""
    if not _v2_enabled():
        return None, 0.0
    try:
        for voice_type, tokens in _VOICE_TYPE_HINTS.items():
            if contains_word(name, tokens):
                return voice_type, 0.7
        return None, 0.0
    except Exception:
        return None, 0.0


@dataclass
class EqCut:
    freq: float
    gain_db: float
    q: float = 1.0
    kind: str = "peak"  # peak | low_shelf | high_shelf | highpass | lowpass


@dataclass
class RegisterRecipe:
    pan_magnitude: float
    comp_ratio: float
    comp_threshold_db: float
    comp_attack_ms: float
    comp_release_ms: float
    deess_threshold_db: float
    deess_max_reduction_db: float
    extra_eq: list[EqCut] = field(default_factory=list)
    saturation_drive: float = 0.0  # 0 = none
    reverb_send: float = 0.0  # 0 = none


RECIPES: dict[str, RegisterRecipe] = {
    # Low octaves/baritone doubles: weight and support under the lead, not
    # width — kept narrower, high-passed above the true bass, cut hard above
    # 4-5kHz (no air/consonant detail needed), compressed flat and constant.
    LOW: RegisterRecipe(
        pan_magnitude=0.75,
        comp_ratio=8.0,
        comp_threshold_db=-24.0,
        comp_attack_ms=15.0,
        comp_release_ms=150.0,
        deess_threshold_db=-28.0,
        deess_max_reduction_db=8.0,
        extra_eq=[
            EqCut(freq=120.0, gain_db=0.0, kind="highpass"),
            EqCut(freq=4500.0, gain_db=-4.0, q=0.7, kind="high_shelf"),
        ],
    ),
    # Same-pitch doubles: pushed fully hard L/R so they don't fight the
    # center, heavy anti-mud cut, a scoop right where the lead needs to
    # breathe, and a much more aggressive de-esser — several unaligned
    # "S"s at once is a notorious amateur-mix tell. Also lowpassed at 5.5kHz
    # (reference mixes push backing vocals back with an HPF+LPF "window"
    # around the lead's own band, not just a highpass) -- without this the
    # unison doubles kept full top-end and fought the lead's own presence/
    # air instead of reading as clearly "behind" it.
    UNISON: RegisterRecipe(
        pan_magnitude=1.0,
        comp_ratio=3.0,
        comp_threshold_db=-20.0,
        comp_attack_ms=8.0,
        comp_release_ms=120.0,
        deess_threshold_db=-34.0,
        deess_max_reduction_db=14.0,
        extra_eq=[
            EqCut(freq=200.0, gain_db=0.0, kind="highpass"),
            EqCut(freq=275.0, gain_db=-3.5, q=1.2, kind="peak"),
            EqCut(freq=1500.0, gain_db=-2.5, q=1.3, kind="peak"),
            EqCut(freq=5500.0, gain_db=0.0, kind="lowpass"),
        ],
    ),
    # High harmonies (thirds/fifths above): no body needed, just air and
    # sparkle — high-passed hard, a bit of saturation to help them cut
    # through without needing more level.
    HIGH: RegisterRecipe(
        pan_magnitude=0.95,
        comp_ratio=2.5,
        comp_threshold_db=-20.0,
        comp_attack_ms=8.0,
        comp_release_ms=120.0,
        deess_threshold_db=-30.0,
        deess_max_reduction_db=10.0,
        extra_eq=[
            EqCut(freq=350.0, gain_db=0.0, kind="highpass"),
            EqCut(freq=6000.0, gain_db=2.0, q=0.7, kind="high_shelf"),
        ],
        saturation_drive=1.4,
    ),
    # Falsettos: the "magic touch" — meant to feel diffuse/distant rather
    # than like individual singers, so a chunk of them gets sent to a long
    # reverb instead of just sitting dry in the stack.
    FALSETTO: RegisterRecipe(
        pan_magnitude=0.95,
        comp_ratio=2.2,
        comp_threshold_db=-22.0,
        comp_attack_ms=10.0,
        comp_release_ms=140.0,
        deess_threshold_db=-30.0,
        deess_max_reduction_db=10.0,
        extra_eq=[
            EqCut(freq=350.0, gain_db=0.0, kind="highpass"),
            EqCut(freq=7000.0, gain_db=1.5, q=0.7, kind="high_shelf"),
        ],
        saturation_drive=0.8,
        reverb_send=0.35,
    ),
}
