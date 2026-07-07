"""Per-instrument mixing recipes for "other"-role stems (anything that isn't
vocal/bass/drums: strings, guitars, keys, brass, synths...).

Before this module existed, every one of these stems got the exact same
generic treatment (one flat 60Hz highpass + one generic compressor setting),
differing only by the crest/flux-based foreground/midground/background depth
classification in depth.py. A solo violin and a synth pad were processed
identically apart from that. This is the "everything piled into one mass"
problem in instrument terms: real mixing gives a violin, an acoustic guitar,
a Rhodes piano, and a synth pad each their own tonal treatment (mud cut,
presence/character frequency, typical dynamics behavior) *in addition to*
front-back depth staging — the two axes are orthogonal, not substitutes for
each other.

Detection is filename-hint-first (naming.py already proved this works well
for role/section/register — real sessions name their files descriptively),
falling back to a coarse spectral heuristic (crest factor + high-frequency
energy share) only when the name gives no clue at all. This deliberately
does NOT attempt fine-grained ML instrument recognition (e.g. distinguishing
a violin from a viola from a synth string patch by ear) — that's a much
harder problem than this engine needs to solve; even a coarse "sustained/
bowed-string-like" vs "plucked/percussive-melodic" vs "bright synth" bucket
is a large improvement over one identical treatment for all of them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .vocalstack import EqCut
from .analysis.loudness import crest_factor, spectral_band_energies

STRINGS = "strings"
GUITAR_ACOUSTIC = "guitar_acoustic"
GUITAR_ELECTRIC = "guitar_electric"
KEYS = "keys"
BRASS = "brass"
SYNTH_PAD = "synth_pad"
SYNTH_LEAD = "synth_lead"
GENERIC = "generic"  # fallback -- the old one-size-fits-all treatment, kept as a safe default

_NAME_HINTS: dict[str, tuple[str, ...]] = {
    STRINGS: ("string", "strings", "violin", "viola", "cello", "archi", "violino", "orchestra", "orchestral"),
    GUITAR_ACOUSTIC: ("acoustic gtr", "acoustic guitar", "chitarra acustica", "ac gtr", "acgtr"),
    GUITAR_ELECTRIC: (
        "electric gtr", "electric guitar", "chitarra elettrica", "elgtr", "e gtr",
        "distortion", "overdrive", "dist gtr",
    ),
    KEYS: ("piano", "keys", "tastiera", "rhodes", "wurli", "organ", "organo"),
    BRASS: (
        "sax", "tromba", "trumpet", "flauto", "flute", "horn", "brass", "fiati",
        "clarinet", "clarinetto", "trombone", "tuba",
    ),
    SYNTH_PAD: ("pad", "synth pad", "ambient", "texture", "drone", "atmosphere"),
    SYNTH_LEAD: ("lead synth", "synth lead", "arp", "pluck", "synth"),
    # Bare "guitar"/"gtr"/"chitarra" with no acoustic/electric qualifier defaults
    # to electric (the more common case in pop/rock stem packs) via the
    # fallback pass below, not listed here to keep acoustic/electric detection
    # unambiguous when the file *does* specify.
}
_BARE_GUITAR_HINTS = ("guitar", "gtr", "chitarra")


@dataclass
class InstrumentRecipe:
    hpf_hz: float
    comp_ratio: float
    comp_threshold_db: float
    comp_attack_ms: float
    comp_release_ms: float
    extra_eq: list[EqCut] = field(default_factory=list)
    saturation_drive: float = 0.0
    comp_makeup_db: float = 3.0
    # Multiplies whatever reverb send depth.py's foreground/midground/
    # background staging already decided -- some instruments (strings,
    # pads) sit better wetter than the generic depth defaults, others
    # (plucky synth leads meant to stay articulate) sit better drier.
    reverb_send_bias: float = 1.0


RECIPES: dict[str, InstrumentRecipe] = {
    GENERIC: InstrumentRecipe(
        hpf_hz=60.0,
        comp_ratio=2.0,
        comp_threshold_db=-20.0,
        comp_attack_ms=15.0,
        comp_release_ms=180.0,
        comp_makeup_db=4.0,
    ),
    # Strings: gentle compression with a slow attack preserves the bow's own
    # natural swell instead of squashing it flat; the only real corrective
    # cut is the harsh bow-noise/scratchiness band around 2.5-4kHz that
    # every string section has some of. Reverb-friendly -- strings are
    # traditionally recorded/placed with more room than close-mic'd stems.
    STRINGS: InstrumentRecipe(
        hpf_hz=150.0,
        comp_ratio=2.2,
        comp_threshold_db=-20.0,
        comp_attack_ms=20.0,
        comp_release_ms=220.0,
        comp_makeup_db=3.0,
        extra_eq=[
            EqCut(freq=3200.0, gain_db=-2.0, q=1.3, kind="peak"),  # bow scratch/harshness
            EqCut(freq=10000.0, gain_db=1.5, q=0.7, kind="high_shelf"),  # air/shimmer
        ],
        reverb_send_bias=1.3,
    ),
    GUITAR_ACOUSTIC: InstrumentRecipe(
        hpf_hz=90.0,
        comp_ratio=3.5,
        comp_threshold_db=-18.0,
        comp_attack_ms=10.0,
        comp_release_ms=140.0,
        comp_makeup_db=3.5,
        extra_eq=[
            EqCut(freq=250.0, gain_db=-2.5, q=1.2, kind="peak"),  # boominess/boxiness
            EqCut(freq=3000.0, gain_db=1.5, q=1.0, kind="peak"),  # pick attack/presence
            EqCut(freq=9000.0, gain_db=1.0, q=0.7, kind="high_shelf"),  # air
        ],
    ),
    # Electric guitar: HPF sits higher than acoustic (distortion/overdrive
    # generates a lot of low-order harmonic mud that acoustic doesn't), a
    # honk cut around 500Hz, presence push so it cuts through without more
    # level, and a touch of saturation (subtle grit on top of whatever
    # amp/pedal distortion the source already has, not a substitute for it).
    GUITAR_ELECTRIC: InstrumentRecipe(
        hpf_hz=110.0,
        comp_ratio=2.5,
        comp_threshold_db=-18.0,
        comp_attack_ms=12.0,
        comp_release_ms=130.0,
        comp_makeup_db=3.0,
        extra_eq=[
            EqCut(freq=500.0, gain_db=-2.0, q=1.0, kind="peak"),  # honk
            EqCut(freq=3500.0, gain_db=2.0, q=1.0, kind="peak"),  # cut-through presence
        ],
        saturation_drive=0.3,
    ),
    # Keys/piano: pianos are famously dynamic (a hard-hit chord and a quiet
    # passage can be 30dB+ apart), so a medium attack lets transients through
    # while still controlling the average level. The 3kHz dip mirrors the
    # same "yield to the vocal's presence band" logic already applied to the
    # music bus as a whole, but as a per-stem head start before that bus
    # processing even runs.
    KEYS: InstrumentRecipe(
        hpf_hz=50.0,
        comp_ratio=3.0,
        comp_threshold_db=-18.0,
        comp_attack_ms=15.0,
        comp_release_ms=160.0,
        comp_makeup_db=3.5,
        extra_eq=[
            EqCut(freq=300.0, gain_db=-2.0, q=1.1, kind="peak"),  # low-mid buildup
            EqCut(freq=3000.0, gain_db=-1.5, q=1.0, kind="peak"),  # yield to vocal presence
            EqCut(freq=10000.0, gain_db=1.0, q=0.7, kind="high_shelf"),
        ],
    ),
    # Brass/winds: honk lives lower than string harshness (~500-800Hz for
    # sax/trumpet body resonance), presence around 4kHz gives the "bite"
    # that reads as close/live. Faster attack than strings -- brass hits are
    # meant to punch, not swell.
    BRASS: InstrumentRecipe(
        hpf_hz=150.0,
        comp_ratio=3.5,
        comp_threshold_db=-16.0,
        comp_attack_ms=8.0,
        comp_release_ms=110.0,
        comp_makeup_db=3.0,
        extra_eq=[
            EqCut(freq=600.0, gain_db=-2.0, q=1.2, kind="peak"),  # honk
            EqCut(freq=4000.0, gain_db=1.5, q=1.0, kind="peak"),  # bite/presence
        ],
    ),
    # Synth pad: sustained/background texture by design -- rolled-off top
    # end reads as "further back" the same way depth.py's own BACKGROUND
    # treatment does, slow/gentle compression (no transients to catch),
    # and a wetter reverb send since pads are meant to blur together with
    # the room rather than stay articulate.
    SYNTH_PAD: InstrumentRecipe(
        hpf_hz=120.0,
        comp_ratio=2.0,
        comp_threshold_db=-22.0,
        comp_attack_ms=30.0,
        comp_release_ms=300.0,
        comp_makeup_db=2.5,
        extra_eq=[
            EqCut(freq=6000.0, gain_db=-2.0, q=0.7, kind="high_shelf"),
        ],
        reverb_send_bias=1.4,
    ),
    # Synth lead/pluck: the opposite instinct from a pad -- fast attack to
    # keep the pluck's transient snap, presence push to cut through a dense
    # arrangement, drier reverb so the rhythmic definition doesn't blur.
    SYNTH_LEAD: InstrumentRecipe(
        hpf_hz=90.0,
        comp_ratio=3.0,
        comp_threshold_db=-18.0,
        comp_attack_ms=6.0,
        comp_release_ms=100.0,
        comp_makeup_db=3.0,
        extra_eq=[
            EqCut(freq=3000.0, gain_db=2.0, q=1.0, kind="peak"),
            EqCut(freq=9000.0, gain_db=1.0, q=0.7, kind="high_shelf"),
        ],
        reverb_send_bias=0.8,
    ),
}


def _name_hint(name: str) -> str | None:
    lowered = name.lower()
    for instrument, hints in _NAME_HINTS.items():
        if any(hint in lowered for hint in hints):
            return instrument
    if any(hint in lowered for hint in _BARE_GUITAR_HINTS):
        # "acoustic"/"acustic" can appear as its own token separated by an
        # underscore or space (e.g. "Guitar_Acoustic.wav") rather than only
        # as part of the exact phrase "acoustic guitar" already checked
        # above -- checked here, not folded into GUITAR_ACOUSTIC's own hint
        # list, so a file that says only "acoustic" with no guitar/gtr/
        # chitarra token at all still falls through to strings/generic
        # instead of being misread as a guitar.
        if any(tok in lowered for tok in ("acoustic", "acustic", "acustica")):
            return GUITAR_ACOUSTIC
        return GUITAR_ELECTRIC
    return None


def _spectral_fallback(audio: np.ndarray, sr: int) -> str:
    """Coarse acoustic-only fallback for when the filename gives no hint at
    all. Deliberately conservative: only commits to a specific bucket when
    the signal clearly reads as one extreme or the other, defaulting to
    GENERIC (the old safe flat treatment) for anything ambiguous rather than
    guessing a specific instrument identity audio alone can't reliably give."""
    crest = crest_factor(audio)
    bands = spectral_band_energies(audio, sr)
    bright_ratio = bands["high_mid"] + bands["air"]

    if crest < 4.0 and bright_ratio < 0.20:
        # Low crest (sustained, no sharp transients) + energy concentrated
        # low/mid rather than bright -- reads as a sustained pad-like bed.
        return SYNTH_PAD
    if crest > 7.0 and bright_ratio > 0.30:
        # High crest (sharp plucked/percussive transients) + bright energy
        # -- reads as a plucked/lead-like element.
        return SYNTH_LEAD
    return GENERIC


def classify_instrument(name: str, audio: np.ndarray, sr: int) -> str:
    hinted = _name_hint(name)
    if hinted is not None:
        return hinted
    return _spectral_fallback(audio, sr)
