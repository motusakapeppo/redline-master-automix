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
from .textmatch import contains_any, contains_word

STRINGS = "strings"
GUITAR_ACOUSTIC = "guitar_acoustic"
GUITAR_ELECTRIC = "guitar_electric"
KEYS = "keys"
ORGAN = "organ"
BRASS = "brass"
WOODWINDS = "woodwinds"
PERCUSSION = "percussion"
CHOIR = "choir"
SYNTH_PAD = "synth_pad"
SYNTH_LEAD = "synth_lead"
BELL = "bell"
PLUCK = "pluck"
VOCAL_CHOP = "vocal_chop"
FX = "fx"
ACCORDION = "accordion"
HARPSICHORD = "harpsichord"
FOLK_PLUCK = "folk_pluck"
WORLD_STRINGS = "world_strings"
WORLD_WINDS = "world_winds"
GENERIC = "generic"  # fallback -- the old one-size-fits-all treatment, kept as a safe default

# Naming library: filename-hint-first classification, deliberately wide and
# bilingual (EN/IT), covering genre slang, common sample-library/preset
# naming conventions (Spitfire/EastWest/Kontakt, Serum/Vital/Massive), DAW
# default track names, and producer abbreviations -- researched against real
# producer naming conventions across orchestral, band, EDM/trap, and Italian
# production contexts, not guessed. Tokens known to collide with another
# category's tokens (bare "hit", "chop", "solo", "chorus", "riff") are
# deliberately left out or scoped to a longer, unambiguous phrase -- a
# generic single-word match across many unrelated file types is worse than
# missing an occasional hit, since it would silently misclassify something
# else entirely.
_NAME_HINTS: dict[str, tuple[str, ...]] = {
    STRINGS: (
        # "str"/"strs" deliberately excluded -- both are substrings of
        # common unrelated words ("instrument", "destroy", "extra-...")
        # and would misfire far more often than they'd correctly help.
        "string", "strings", "violin", "vln", "violino",
        "viola", "vla", "cello", "celli", "violoncello", "double bass", "doublebass",
        "contrabbasso", "contrabass", "archi", "arco", "pizzicato", "pizz", "spiccato",
        "tremolo strings", "sordino", "con sordino", "fiddle", "ensemble archi",
        "sezione archi", "quartet", "quartetto", "string quartet", "chamber strings",
        "orchestra", "orchestral", "sinfonia", "tutti strings",
        # sample-library patch names (Spitfire/EastWest/Kontakt/Orchestral Tools)
        "spitfire strings", "bbc so", "bbcso", "albion", "hollywood strings",
        # Bare "lass" (LA Scoring Strings abbreviation) deliberately
        # excluded -- substring of "glass"/"class", extremely common in
        # synth-pad/texture preset names ("Glass Pad").
        "cinematic strings", "cinestrings", "cinesamples", "berlin strings",
        "metropolis ark", "sable", "mural",
        # Checked before PLUCK below so "harp"/"arpa" don't fall through and
        # get misread by PLUCK's "arp" hint (a plain substring match, and
        # "harp" contains "arp") -- an orchestral harp's plucked-but-resonant
        # tone is a closer match to strings/bell territory than a synth pluck.
        "harp", "arpa",
    ),
    GUITAR_ACOUSTIC: (
        "acoustic gtr", "acoustic guitar", "chitarra acustica", "acustica", "ac gtr", "acgtr",
        "nylon", "classical guitar", "chitarra classica", "12 string", "12-string", "twelve string",
        "steel string", "dreadnought", "folk guitar", "fingerpick", "fingerstyle",
    ),
    GUITAR_ELECTRIC: (
        "electric gtr", "electric guitar", "chitarra elettrica", "elettrica", "elgtr", "e gtr", "egtr",
        "distortion", "overdrive", "dist gtr", "power chord", "powerchord", "clean gtr", "muted gtr",
        # Bare "tele"/"strat" deliberately excluded -- "tele" is a substring
        # of "telephone (fx)" and "strat" of "strategy", both plausible in
        # unrelated FX/preset names; the full "telecaster"/"stratocaster"
        # brand names are unambiguous on their own.
        "lead gtr", "rhythm gtr", "riff gtr", "guitar riff", "palm mute", "telecaster",
        "stratocaster", "les paul", "humbucker", "chitarra ritmica", "chitarra solista",
        "lead guitar",
    ),
    KEYS: (
        "piano", "pno", "keys", "kbd", "tastiera", "tastiere", "pianoforte",
        "rhodes", "wurli", "wurlitzer", "fender rhodes",
        "electric piano", "epiano", "e-piano", "e piano",
        "clav", "clavinet", "clavi", "pianet", "toy piano",
        "grand piano", "upright piano", "felt piano", "una corda", "piano a coda",
        "synth keys", "stage piano", "cp70", "cp-70", "dx ep", "dx rhodes", "fm piano",
    ),
    # Split from KEYS -- a Hammond/organ patch wants a very different EQ
    # (present midrange, no piano-style low-mid dip since bass pedals can
    # carry real low end) and a much slower, gentler compressor than a
    # percussive piano attack needs.
    ORGAN: (
        "organ", "organo", "hammond", "b3", "b-3", "leslie", "drawbar",
        "church organ", "pipe organ", "farfisa", "vox organ", "vox continental",
        "combo organ", "gospel organ", "organo a canne", "organo da chiesa",
        # Sustained reed-organ family (harmonium/pump/reed organ) shares the
        # organ's sustained, mid-present, slow-swell tonal character.
        "harmonium", "pump organ", "reed organ", "armonium",
    ),
    BRASS: (
        "tromba", "trumpet", "tpt", "trpt", "horn", "horns", "french horn", "fr horn",
        # Bare "corno" deliberately excluded -- ambiguous with "corno inglese"
        # (English horn, a WOODWIND despite the name); "corno francese" is
        # specific enough to stay unambiguous.
        "corno francese", "brass", "ottoni", "ottone", "sezione ottoni",
        "trombone", "tuba", "cornet", "flicorno", "flugelhorn", "flugel", "euphonium",
        "fanfare", "fanfara", "brass stab", "brass hit", "cinebrass", "hollywood brass",
    ),
    # Split from BRASS -- flutes/clarinets/oboes/sax are breathy and airy
    # (sax is acoustically a reed woodwind despite the brass-adjacent metal
    # body and colloquial "horn section" grouping) where trumpet/trombone are
    # honk-and-bite; lumping them together meant a flute got a trumpet's
    # bite-EQ and fast attack, which reads as harsh/unnatural.
    # WORLD_WINDS (below) sits before WOODWINDS so its specific "pan flute"/
    # "irish flute" phrases win over WOODWINDS' bare "flute" substring hint.
    WORLD_WINDS: (
        "duduk", "shakuhachi", "bansuri", "ney", "ocarina", "tin whistle", "low whistle",
        "irish flute", "pan flute", "panflute", "quena", "zampoña", "bagpipes",
        "cornamusa", "zampogna", "uilleann", "gaita", "hulusi", "bawu", "suona",
        "dizi", "xiao",
    ),
    WOODWINDS: (
        "flauto", "flute", "flt", "piccolo", "picc", "ottavino", "alto flute", "bass flute",
        # "clar" deliberately excluded -- substring of "clarity"/"declare",
        # common in FX/reverb preset names; "clarinet"/"clarinetto" alone
        # are unambiguous.
        "clarinet", "clarinetto", "bass clarinet", "oboe", "english horn", "corno inglese",
        "bassoon", "fagotto", "contrabassoon", "recorder", "flauto dolce",
        "sax", "saxophone", "sassofono", "alto sax", "tenor sax", "soprano sax", "bari sax",
        # Bare "ance" (Italian "reeds") deliberately excluded -- substring of
        # "dance"/"trance", both extremely common in genre/patch names.
        "fiati legni", "legni", "legno", "woodwind", "woodwinds",
    ),
    # Bells/chimes/mallet percussion (found in a real session's stems: "Bell
    # 1", "Bell reverb", "Church bell") -- own bucket, not lumped with
    # STRINGS' bowed-swell treatment: a bell's attack is sharp and metallic,
    # not a slow bow swell, and deserves its own shimmer/decay-tuned recipe.
    BELL: (
        "bell", "bells", "campana", "campane", "campanelli", "chime", "chimes",
        "carillon", "glockenspiel", "glock", "celesta", "celeste",
        "marimba", "vibraphone", "vibrafono", "vibes",
        "xylophone", "xylo", "xilofono", "kalimba", "mbira", "thumb piano",
        "music box", "tubular bells", "hand bells", "sleigh bells", "crotales",
        "bell tree", "wind chimes", "steel drum", "steelpan", "handpan", "toy piano bell",
    ),
    # Hand/auxiliary percussion (shaker, tambourine, conga...) -- distinct
    # from a drum-kit "drums" role stem (naming.py already routes anything
    # with "perc"/"drum"/"kick" etc. to role=drums before this module ever
    # sees it); these hints only match auxiliary percussion that naming.py's
    # own role hints don't already catch. Includes genre-specific hand
    # percussion (reggaeton/latin/afrobeat) real sessions actually use.
    PERCUSSION: (
        "shaker", "egg shaker", "tambourine", "tamburello", "tamb",
        "conga", "congas", "bongo", "bongos", "cajon", "cajón", "djembe", "darbuka", "doumbek",
        "cabasa", "guiro", "güiro", "claves", "clave", "woodblock", "wood block",
        "cowbell", "campanaccio", "agogo", "agogò", "triangle", "triangolo",
        "castanet", "castagnette", "castanets", "nacchere", "vibraslap", "ratchet",
        "tabla", "dholak", "dhol", "udu", "frame drum", "bodhran", "surdo",
        "timbale", "timbales", "tumba", "shekere",
        "cuica", "pandeiro", "tamborim", "repique", "berimbau", "sabar", "talking drum",
        "percussioni", "perc",
    ),
    # Sampled choir/vocal-ensemble texture used as an instrumental layer,
    # not an actual lead/double vocal take (naming.py's VOCAL_ROLE_HINTS
    # doesn't match "choir"/"coro", so this correctly still reaches "other").
    # "chorus" deliberately excluded -- collides with the song-section word.
    CHOIR: (
        "choir", "choirs", "coro", "cori", "aahs", "oohs", "ooh", "mmh", "humming",
        "vox pad", "voxpad", "vocal pad", "voice pad", "vocal texture", "vocal drone",
        "angel choir", "angelic choir", "gregorian", "chant", "church choir", "gospel choir",
        "childrens choir", "boys choir", "vocal ensemble", "ensemble vocale", "wordless choir",
        "voci femminili", "voci maschili", "pad vocale", "coro gospel", "coro angelico",
    ),
    # Chopped/rearranged vocal samples used as a rhythmic/melodic instrument
    # (EDM/pop production staple) -- distinct from CHOIR (a sustained pad-like
    # texture): chops are short, plucky, rhythmically active, and should stay
    # articulate/dry rather than blur into a wash of reverb.
    VOCAL_CHOP: (
        "vox chop", "vocal chop", "vocalchop", "voxchop", "chopped vocal", "chopped vox",
        "vox stab", "vocal stab", "vox stutter", "vocal stutter", "vox loop",
        "vocal sample", "vox sample", "vocal one shot", "vox oneshot", "topline chop",
        "hook vox", "tropical vox", "voce campionata", "campione vocale", "chop vocale",
    ),
    SYNTH_PAD: (
        "pad", "pads", "synth pad", "warm pad", "soft pad", "lush pad", "ambient pad",
        "atmos", "atmosphere", "ambience", "ambient", "drone", "texture", "wash", "swell",
        "string pad", "analog pad", "poly pad", "evolving pad", "dark pad", "bright pad",
        "soundscape", "synth bed", "sustain synth", "air pad", "omnisphere",
        # Italian "tappeto" (literally "carpet") is the standard word for a
        # sustained pad/bed -- a real, high-value token, not a literal cut/rug.
        "tappeto", "tappeto sonoro", "ambiente sonoro",
    ),
    SYNTH_LEAD: (
        "lead synth", "synth lead", "synth leads", "topline synth", "top line synth",
        "hook synth", "main synth", "melody synth", "supersaw", "super saw", "hypersaw",
        "square lead", "saw lead", "acid lead", "tb303", "tb-303", "trance lead",
        "hardstyle lead", "festival lead", "detune lead", "unison lead", "mono lead",
        "poly lead", "solo synth", "synth solo", "riff synth", "linea melodica",
        # Bare "lead" (word-matched) -- a stem named just "Lead" is a synth
        # lead line. "lead guitar" is protected above in GUITAR_ELECTRIC.
        "lead",
        # Monophonic expressive lead -- a theremin is a single continuous
        # pitch like a sustained synth lead, not a pad or a pluck.
        "theremin",
    ),
    # Short, plucky, fast-decaying synth elements (arps, plucks, stabs) --
    # split from SYNTH_LEAD: a sustained lead line wants to hold its note and
    # cut through, a pluck/arp is rhythmic ear-candy that should stay tight,
    # dry, and out of the way between its own transients.
    PLUCK: (
        "arp", "arps", "arpeggio", "arpeggiator", "arpeggiated", "pluck", "plucks",
        "synth stab", "chord stab", "house stab", "mallet synth", "plucked synth",
        "poly pluck", "edm pluck", "future bass pluck", "koto", "shamisen", "sitar",
        "guzheng", "blip", "sequenza",
    ),
    # Non-tonal ear-candy (risers, sweeps, impacts, downlifters, whooshes) --
    # common in EDM/pop transitions. These aren't really "instruments" in the
    # tonal-balance sense; they're brief, wideband, and should be left mostly
    # untouched dynamically (no correcting an already-designed sound effect)
    # while still getting basic mud control.
    FX: (
        "riser", "rise fx", "uplifter", "upsweep", "sweep fx", "downlifter", "downsweep",
        "impact hit", "impact fx", "sub drop", "drop fx", "whoosh", "woosh", "swoosh",
        "transition fx", "trans fx", "buildup fx", "noise sweep", "white noise fx",
        "reverse cymbal", "reverse crash", "backspin", "braam", "braaam", "bwaa",
        "boomer fx", "sub boom", "downer fx", "glitch fx", "zap", "laser fx", "siren fx",
        # "air horn"/"airhorn" deliberately excluded -- would collide with
        # BRASS's "horn"/"horns" (checked earlier in this dict) since a bare
        # "horn" token is common and legitimate for a real brass stem.
        "spinback", "tape stop", "filter sweep fx", "cinematic hit",
        "effetto", "effetti", "transizione", "salita", "discesa", "impatto", "spazzata",
    ),
    # Free-reed family (accordion/harmonica/melodica/bandoneon) -- sustained,
    # mid-present, gentle-fast compressor, moderate reverb. Distinct from
    # ORGAN (which covers the sustained reed-organ/harmonium side): accordion/
    # harmonica sit more forward and melodic than a held organ bed.
    ACCORDION: (
        "accordion", "fisarmonica", "harmonica", "armonica", "melodica",
        "bandoneon", "bandoneón", "concertina", "musette", "garmon",
    ),
    # Plucked-bright keyboard string (harpsichord/clavichord/spinet) --
    # plucky attack, thin low end, fast compressor, dry. Deliberately NOT
    # lumped with KEYS (piano) whose sustained felt/hammer tone wants a
    # different low-mid treatment, nor with STRINGS (bowed swell).
    HARPSICHORD: (
        "harpsichord", "clavicembalo", "cembalo", "clavichord", "spinet",
        "virginal", "clavecin",
    ),
    # Bright plucked folk strings (banjo/mandolin/ukulele/dobro/dulcimer) --
    # fast attack, presence ~3kHz, light reverb. Distinct from GUITAR_ACOUSTIC
    # (which targets the fuller-bodied steel/nylon guitar) and from PLUCK
    # (synth arps/plucks): these are acoustic, present, and twangy.
    FOLK_PLUCK: (
        "banjo", "mandolin", "mandolino", "ukulele", "uke", "lap steel", "pedal steel",
        "dobro", "resonator guitar", "dulcimer", "cavaquinho", "autoharp", "zither",
        "hammered dulcimer",
    ),
    # Bowed/plucked world strings (erhu/oud/bouzouki/balalaika/kora...) --
    # gentle compression, some reverb. NOTE: koto/guzheng/sitar/shamisen stay
    # in PLUCK (existing behavior, don't break test_instrumentstack); only
    # genuinely-new tokens are listed here.
    WORLD_STRINGS: (
        "erhu", "oud", "bouzouki", "balalaika", "kora", "ngoni", "sarangi", "sarod",
        "pipa", "santoor", "morin khuur", "kamancheh", "rebab", "veena",
    ),
    # Bare "guitar"/"gtr"/"chitarra" with no acoustic/electric qualifier defaults
    # to electric (the more common case in pop/rock stem packs) via the
    # fallback pass below, not listed here to keep acoustic/electric detection
    # unambiguous when the file *does* specify.
}
_BARE_GUITAR_HINTS = ("guitar", "gtr", "git", "guit", "chitarra")

# Short tokens that false-positive as substrings inside unrelated longer
# words ("organic" contains "organ", "sharp" contains "harp", "merchant"
# contains "chant", "umbrella" contains "bell", "padding" contains "pad",
# "monkeys" contains "keys", "warp" contains "arp"). These must match only on
# word boundaries (textmatch.contains_word), while every other hint in
# _NAME_HINTS keeps the forgiving substring semantics (contains_any). A hint
# token listed here is matched as a standalone word, never as a substring.
_WORD_HINTS: frozenset[str] = frozenset({
    "organ", "harp", "bell", "pad", "keys", "arp", "arps", "chant", "coro", "cori",
    "mmh", "ooh", "aahs", "wash", "drone", "swell", "clav", "clavi",
    "b3", "oud", "ney", "uke", "lead",
})


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
    # while still controlling the average level. No static "yield to vocal"
    # cut here (there used to be one at 3kHz) -- that's now handled entirely
    # by the bus-level dynamic mechanisms (spectral duck + music-bus M/S dip
    # + masking-cut passes in mixengine.py), which only attenuate this band
    # while the vocal is actually singing. A per-instrument *static* cut on
    # top of those was a redundant, always-on tax on the piano's presence
    # even during instrumental-only passages -- confirmed as a real
    # contributor to "everything except drums sounds buried".
    KEYS: InstrumentRecipe(
        hpf_hz=50.0,
        comp_ratio=3.0,
        comp_threshold_db=-18.0,
        comp_attack_ms=15.0,
        comp_release_ms=160.0,
        comp_makeup_db=3.5,
        extra_eq=[
            EqCut(freq=300.0, gain_db=-2.0, q=1.1, kind="peak"),  # low-mid buildup
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
    # Woodwinds: split from BRASS -- a flute/clarinet/oboe's breathy, airy
    # tone has none of a trumpet's honk-and-bite, so the same EQ made a
    # flute sound harsh/unnaturally aggressive. Gentler compression (woodwind
    # dynamics are more about breath control than brass's hard-hit punch),
    # a lighter mud cut, and an air-shelf lift instead of a presence bite.
    WOODWINDS: InstrumentRecipe(
        hpf_hz=200.0,
        comp_ratio=2.2,
        comp_threshold_db=-18.0,
        comp_attack_ms=15.0,
        comp_release_ms=160.0,
        comp_makeup_db=2.5,
        extra_eq=[
            EqCut(freq=400.0, gain_db=-1.2, q=1.0, kind="peak"),  # breath/body mud
            EqCut(freq=8000.0, gain_db=1.5, q=0.7, kind="high_shelf"),  # air/breathiness
        ],
        reverb_send_bias=1.15,
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
    # Organ: midrange presence carries the character (drawbar harmonics
    # live around 1-3kHz), gentle low-mid dip instead of piano's mud cut
    # since organ bass pedals can legitimately own real low end. Slow,
    # gentle compression -- organ swells are meant to breathe, not pump.
    ORGAN: InstrumentRecipe(
        hpf_hz=60.0,
        comp_ratio=2.2,
        comp_threshold_db=-20.0,
        comp_attack_ms=25.0,
        comp_release_ms=220.0,
        comp_makeup_db=3.0,
        extra_eq=[
            EqCut(freq=300.0, gain_db=-1.0, q=1.0, kind="peak"),
            EqCut(freq=1800.0, gain_db=1.5, q=1.0, kind="peak"),
        ],
    ),
    # Hand/auxiliary percussion: bright and fully transient by nature (no
    # low end to speak of), so no HPF-driven thinning is needed -- just a
    # fast, light compressor to even out hits and a presence lift so shakers/
    # tambourines cut through a dense arrangement without extra level.
    PERCUSSION: InstrumentRecipe(
        hpf_hz=200.0,
        comp_ratio=2.5,
        comp_threshold_db=-16.0,
        comp_attack_ms=3.0,
        comp_release_ms=90.0,
        comp_makeup_db=2.0,
        extra_eq=[
            EqCut(freq=6000.0, gain_db=1.5, q=0.8, kind="high_shelf"),
        ],
        reverb_send_bias=0.9,
    ),
    # Choir/vocal-ensemble texture: treated like a diffuse pad rather than
    # a real lead/backing vocal (it isn't one) -- rolled-off top for
    # distance, gentle compression, wetter reverb so it blurs into the room.
    # No static presence-band cut here either (see KEYS above for why) --
    # the bus-level dynamic duck/dip/masking already yields to the real lead
    # vocal only while it's actually singing.
    CHOIR: InstrumentRecipe(
        hpf_hz=150.0,
        comp_ratio=2.0,
        comp_threshold_db=-20.0,
        comp_attack_ms=25.0,
        comp_release_ms=250.0,
        comp_makeup_db=2.5,
        extra_eq=[
            EqCut(freq=7000.0, gain_db=-1.5, q=0.7, kind="high_shelf"),
        ],
        reverb_send_bias=1.3,
    ),
    # Bells/chimes/mallet percussion: sharp metallic attack with a long,
    # airy decay -- the opposite envelope shape from STRINGS' bow swell, so
    # it gets its own recipe (fast attack to preserve the strike, a shimmer
    # shelf for the decay tail) instead of being forced into the strings
    # treatment it used to share.
    BELL: InstrumentRecipe(
        hpf_hz=180.0,
        comp_ratio=2.0,
        comp_threshold_db=-20.0,
        comp_attack_ms=2.0,
        comp_release_ms=200.0,
        comp_makeup_db=2.5,
        extra_eq=[
            EqCut(freq=500.0, gain_db=-1.5, q=1.0, kind="peak"),  # clangy low-mid
            EqCut(freq=8000.0, gain_db=2.0, q=0.7, kind="high_shelf"),  # shimmer
        ],
        reverb_send_bias=1.2,
    ),
    # Arps/plucks/stabs: rhythmic ear-candy, not a sustained lead line --
    # fast attack and fast release keep every note articulate and distinct
    # instead of smearing into the next one, drier reverb so the rhythm
    # stays legible in a dense arrangement.
    PLUCK: InstrumentRecipe(
        hpf_hz=100.0,
        comp_ratio=2.5,
        comp_threshold_db=-18.0,
        comp_attack_ms=2.0,
        comp_release_ms=60.0,
        comp_makeup_db=2.5,
        extra_eq=[
            EqCut(freq=4000.0, gain_db=1.5, q=1.0, kind="peak"),  # click/definition
        ],
        reverb_send_bias=0.75,
    ),
    # Vocal chops: short, rhythmically-active vocal samples used as an
    # instrument, not a real backing vocal -- kept tight, dry and forward
    # (the opposite treatment from CHOIR) so the chops read as a percussive/
    # melodic element instead of blurring into a vocal-pad wash.
    VOCAL_CHOP: InstrumentRecipe(
        hpf_hz=150.0,
        comp_ratio=3.0,
        comp_threshold_db=-18.0,
        comp_attack_ms=3.0,
        comp_release_ms=90.0,
        comp_makeup_db=2.5,
        extra_eq=[
            EqCut(freq=9000.0, gain_db=1.5, q=0.7, kind="high_shelf"),
        ],
        reverb_send_bias=0.85,
    ),
    # FX (risers, sweeps, impacts): already-designed sound effects, not
    # tonal instruments to correct -- minimal, gentle dynamics (just enough
    # to keep an impact from clipping) and no presence/mud EQ shaping, since
    # "fixing" a riser's tonal balance usually just makes it sound wrong.
    FX: InstrumentRecipe(
        hpf_hz=40.0,
        comp_ratio=1.5,
        comp_threshold_db=-12.0,
        comp_attack_ms=10.0,
        comp_release_ms=150.0,
        comp_makeup_db=1.0,
        reverb_send_bias=0.7,
    ),
    # Free-reed family (accordion/harmonica/melodica/bandoneon): sustained,
    # mid-present, gentle-fast compressor, moderate reverb. A light low-mid
    # dip tames the reed body boxiness, and a midrange presence lift keeps
    # the reed character articulate without the hard bite of brass.
    ACCORDION: InstrumentRecipe(
        hpf_hz=120.0,
        comp_ratio=2.2,
        comp_threshold_db=-18.0,
        comp_attack_ms=12.0,
        comp_release_ms=160.0,
        comp_makeup_db=2.5,
        extra_eq=[
            EqCut(freq=350.0, gain_db=-1.5, q=1.0, kind="peak"),  # reed body boxiness
            EqCut(freq=2000.0, gain_db=1.5, q=1.0, kind="peak"),  # reed presence
        ],
        reverb_send_bias=1.1,
    ),
    # Harpsichord/clavichord/spinet: plucky-bright attack, thin low end, fast
    # compressor, dry. The pluck is short and articulate -- fast attack/early
    # release keep every note distinct; a low-mid cut removes the boxy body a
    # plucked keyboard string doesn't have.
    HARPSICHORD: InstrumentRecipe(
        hpf_hz=180.0,
        comp_ratio=2.5,
        comp_threshold_db=-18.0,
        comp_attack_ms=3.0,
        comp_release_ms=80.0,
        comp_makeup_db=2.5,
        extra_eq=[
            EqCut(freq=400.0, gain_db=-2.0, q=1.0, kind="peak"),  # thin low end
            EqCut(freq=4000.0, gain_db=1.5, q=1.0, kind="peak"),  # pluck definition
        ],
        reverb_send_bias=0.7,
    ),
    # Bright plucked folk strings (banjo/mandolin/ukulele/dobro/dulcimer):
    # fast attack, presence ~3kHz, light reverb. Twangy and present -- a
    # 3kHz lift brings out the pick attack, and a light reverb keeps it
    # from sounding dry without blurring the pluck articulation.
    FOLK_PLUCK: InstrumentRecipe(
        hpf_hz=110.0,
        comp_ratio=2.8,
        comp_threshold_db=-18.0,
        comp_attack_ms=4.0,
        comp_release_ms=100.0,
        comp_makeup_db=2.5,
        extra_eq=[
            EqCut(freq=3000.0, gain_db=1.5, q=1.0, kind="peak"),  # pick attack/presence
            EqCut(freq=9000.0, gain_db=1.0, q=0.7, kind="high_shelf"),  # air
        ],
        reverb_send_bias=0.95,
    ),
    # Bowed/plucked world strings (erhu/oud/bouzouki/balalaika/kora...):
    # gentle compression, some reverb. Similar to STRINGS but with a gentler
    # scratch-cut and a touch more room, since these instruments are
    # traditionally recorded/mixed with a natural ambient bloom.
    WORLD_STRINGS: InstrumentRecipe(
        hpf_hz=140.0,
        comp_ratio=2.0,
        comp_threshold_db=-20.0,
        comp_attack_ms=18.0,
        comp_release_ms=220.0,
        comp_makeup_db=2.5,
        extra_eq=[
            EqCut(freq=3200.0, gain_db=-1.5, q=1.2, kind="peak"),  # scratch/harshness
            EqCut(freq=9000.0, gain_db=1.0, q=0.7, kind="high_shelf"),  # air
        ],
        reverb_send_bias=1.25,
    ),
    # World winds (duduk/shakuhachi/bansuri/bagpipes...): breathy-airy like
    # WOODWINDS but distinct -- light compression (breath control, not punch)
    # and an air shelf; slightly gentler mud cut than the Western woodwind
    # recipe, since many of these carry a darker, reedy body that a hard cut
    # would thin unnaturally.
    WORLD_WINDS: InstrumentRecipe(
        hpf_hz=180.0,
        comp_ratio=2.0,
        comp_threshold_db=-18.0,
        comp_attack_ms=15.0,
        comp_release_ms=170.0,
        comp_makeup_db=2.5,
        extra_eq=[
            EqCut(freq=450.0, gain_db=-1.0, q=1.0, kind="peak"),  # breath/body mud
            EqCut(freq=7500.0, gain_db=1.5, q=0.7, kind="high_shelf"),  # air/breathiness
        ],
        reverb_send_bias=1.2,
    ),
}


def _name_hint(name: str) -> str | None:
    # Word-boundary matching for the short/dangerous tokens (see _WORD_HINTS)
    # so they don't fire inside unrelated longer words; substring matching
    # for everything else (unambiguous multi-char phrases are safe).
    for instrument, hints in _NAME_HINTS.items():
        word_hints = tuple(h for h in hints if h in _WORD_HINTS)
        substr_hints = tuple(h for h in hints if h not in _WORD_HINTS)
        if word_hints and contains_word(name, word_hints):
            return instrument
        if substr_hints and contains_any(name, substr_hints):
            return instrument
    if contains_any(name, _BARE_GUITAR_HINTS):
        # "acoustic"/"acustic" can appear as its own token separated by an
        # underscore or space (e.g. "Guitar_Acoustic.wav") rather than only
        # as part of the exact phrase "acoustic guitar" already checked
        # above -- checked here, not folded into GUITAR_ACOUSTIC's own hint
        # list, so a file that says only "acoustic" with no guitar/gtr/
        # chitarra token at all still falls through to strings/generic
        # instead of being misread as a guitar.
        if contains_any(name, ("acoustic", "acustic", "acustica")):
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


# --- Genre-aware nudges: the same instrument category shouldn't sound
# identical in a lush Acoustic/Classical session and a tight, sidechain-
# driven EDM one. Rather than a full per-genre recipe table (a large
# combinatorial surface for a fairly subtle effect), this returns a small
# (makeup_db_delta, reverb_multiplier) nudge applied on top of the
# instrument's own recipe in mixengine.py -- additive/multiplicative, never
# replacing the base recipe's own tuning.
_BRIGHT_SYNTH_KINDS = frozenset({SYNTH_LEAD, SYNTH_PAD, PLUCK, VOCAL_CHOP, FX})
_WARM_ACOUSTIC_KINDS = frozenset({
    STRINGS, BRASS, WOODWINDS, KEYS, ORGAN, BELL, GUITAR_ACOUSTIC, CHOIR,
    ACCORDION, HARPSICHORD, FOLK_PLUCK, WORLD_STRINGS, WORLD_WINDS,
})


def genre_bias(instrument_kind: str, genre_name: str) -> tuple[float, float]:
    """Returns (makeup_db_delta, reverb_multiplier) for `instrument_kind`
    given the track's detected/selected genre. Defaults to (0.0, 1.0) --
    no change -- for any genre/instrument combination not called out below,
    so this can only ever nudge, never override, the base recipe."""
    g = genre_name or ""
    if "EDM" in g or "Urban" in g or "Hip-Hop" in g:
        # Tight, punchy, sidechain-driven genres: synths get a touch more
        # forward and drier (less blur competing with the sidechain pump),
        # acoustic/orchestral elements (when present at all) sit back a
        # little drier too rather than swimming in room reverb.
        if instrument_kind in _BRIGHT_SYNTH_KINDS:
            return (0.5, 0.85)
        if instrument_kind in _WARM_ACOUSTIC_KINDS:
            return (0.0, 0.9)
    if "Acoustic" in g or "Classical" in g or "Jazz" in g:
        # Roomier, more natural genres: real instruments get a little more
        # space and warmth, bright synths (when present, e.g. a Jazz/Vintage
        # electric piano patch) pull back slightly rather than dominating.
        if instrument_kind in _WARM_ACOUSTIC_KINDS:
            return (0.3, 1.2)
        if instrument_kind in _BRIGHT_SYNTH_KINDS:
            return (-0.3, 0.9)
    return (0.0, 1.0)
