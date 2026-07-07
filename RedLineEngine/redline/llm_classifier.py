"""Optional local LLM classifier — a small, offline, permissively-licensed
(Apache 2.0) model bundled in models/, used only as an advisory cross-check
for stems the naming-based heuristic (naming.py) can't confidently place.
The naming+pitch heuristics already handle the common real-world case well
(validated against a real 24-file session); this exists for the harder
case: stems named without any convention at all (e.g. "track_07.wav") where
there's no text signal for naming.py to read at all.

Deliberately advisory, not authoritative: this suggests a possible
reclassification (surfaced to the user via on_step/on_event) rather than
silently overriding the DSP path a stem gets — a small local model's guess
isn't something to trust blindly for a decision this consequential, and
100% offline operation (no cloud API key, no per-request cost) was an
explicit requirement.
"""

from __future__ import annotations

import json
import os
import re

from redline.logging_setup import get_logger

logger = get_logger(__name__)

MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "qwen2.5-1.5b-instruct-q4_0.gguf"
)

BUS_CATEGORIES = ("Drum Bus", "Bass Bus", "Music Bus", "Main Vox", "Backing Vox")

_model = None
_load_failed = False


def _get_model():
    global _model, _load_failed
    if _model is not None or _load_failed:
        return _model
    if not os.path.exists(MODEL_PATH):
        _load_failed = True
        return None
    try:
        from llama_cpp import Llama

        _model = Llama(model_path=MODEL_PATH, n_ctx=2048, n_threads=os.cpu_count() or 4, verbose=False)
    except Exception:
        logger.warning("Failed to load LLM model — advisory classifier unavailable", exc_info=True)
        _load_failed = True
        _model = None
    return _model


def is_available() -> bool:
    return _get_model() is not None


def classify_ambiguous_stems(stem_infos: list[dict], on_token=None) -> dict[str, str]:
    """stem_infos: list of {"name": str, "spectral_hint": str, "transient_hint": str}.
    Returns {name: bus_category} for whichever stems the model could confidently
    place. Empty dict if the model isn't available or its output doesn't parse
    as valid JSON — callers must keep their existing heuristic result in that
    case and never block on this.

    `on_token`, if given, is called with each generated text fragment as it
    streams from the model — this is purely for the UI's "watch it think"
    console (Fase 5); the full text is still assembled and parsed the same
    way whether or not a callback is passed, so streaming is cosmetic only,
    never a change to what gets classified."""
    model = _get_model()
    if model is None or not stem_infos:
        return {}

    listing = "\n".join(
        f"- \"{s['name']}\": spettro={s.get('spectral_hint', '?')}, transiente={s.get('transient_hint', '?')}"
        for s in stem_infos
    )
    prompt = (
        "Sei un ingegnere del suono. Classifica ogni traccia audio elencata in una di queste categorie ESATTE: "
        + ", ".join(BUS_CATEGORIES)
        + ".\nTracce:\n" + listing
        + "\n\nRispondi SOLO con un oggetto JSON valido nella forma {\"nome_traccia\": \"categoria\"}, nient'altro."
    )

    try:
        if on_token is not None:
            text = ""
            stream = model.create_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=400,
                temperature=0.1,
                stream=True,
            )
            for chunk in stream:
                delta = chunk["choices"][0].get("delta", {})
                fragment = delta.get("content")
                if fragment:
                    text += fragment
                    on_token(fragment)
        else:
            result = model.create_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=400,
                temperature=0.1,
            )
            text = result["choices"][0]["message"]["content"]

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {}
        parsed = json.loads(match.group(0))
        return {name: category for name, category in parsed.items() if category in BUS_CATEGORIES}
    except Exception:
        logger.warning("LLM stem classification failed — returning empty", exc_info=True)
        return {}


# Wizard knobs the LLM is allowed to nudge based on a free-text creative
# brief. Deliberately just these three (already user-facing sliders in the
# wizard) -- not raw DSP parameters -- so a bad interpretation is at worst
# "too warm" or "too aggressive", never a broken signal chain.
BRIEF_ADJUSTABLE_KEYS = ("aggressiveness", "warmth", "vocal_prominence")

# Even with few-shot examples in the prompt, a 1.5B model reliably invents
# "courtesy" adjustments the user never asked for (confirmed in practice:
# "vorrei un suono più caldo" alone came back with an unrequested
# vocal_prominence nudge too). Range-clamping alone can't catch this --
# it's a real, in-range value, just not one anyone asked for. This keyword
# gate is the actual fix: a suggested key is only kept if the brief text
# itself mentions something relevant to it, checked independently of
# whatever the model claims it was responding to.
_BRIEF_RELEVANCE_KEYWORDS = {
    "warmth": (
        "cald", "freddo", "fredda", "brillante", "vinil", "morbid", "vintage", "analog", "scuro", "scura",
        # Synesthetic/color vocabulary producers actually use ("more purple",
        # "golden", "icy") -- these are real, if metaphorical, mixing
        # requests, not nonsense. See _COLOR_TO_KNOB_HINTS below for the
        # reasoning behind each mapping.
        "viola", "oro", "dorat", "ambra", "marrone", "ghiacc", "gelo", "blu", "acciaio", "argent", "metallic",
    ),
    "vocal_prominence": ("voce", "vocal", "cantante", "protagonist", "indietro", "avanti", "presenza", "canto"),
    "aggressiveness": (
        "aggressiv", "compress", "delicat", "gentile", "duro", "dura", "radio", "forte", "spinto", "spinta", "punch",
        "fuoco", "incendi", "brucia", "fiamma", "esplo", "rosso", "nero", "potente", "muro", "martell", "pugno",
        "morbid", "soffice", "leggero", "eter", "sognante", "nuvola",
    ),
}

# A reasoned (not literal) mapping from color/element metaphors real
# producers use to the warmth/aggressiveness axis they most often imply --
# included directly in the prompt as extra few-shot context so the model
# translates "make it more purple" or "set it on fire" into an actual
# adjustment instead of treating a metaphor as nonsense and inventing
# nothing (or inventing something unrelated). This is inherently a
# judgment call, not a standard -- documented in the README together with
# what was actually tested against the real model.
_COLOR_TO_KNOB_HINTS = """\
- "fuoco" / "incendia" / "brucia" / "fiamma" / "esplosivo": aggressiveness molto alta, energia e distorsione
- "viola": warmth moderatamente positiva (ricco, misterioso, non troppo brillante)
- "oro" / "dorato" / "ambra": warmth positiva (vintage, analogico, ricco)
- "blu" / "ghiaccio" / "gelo" / "acciaio": warmth negativa (freddo, brillante, metallico)
- "rosso" / "nero" / "potente": aggressiveness alta (pesante, energico)
- "eterei" / "sognante" / "nuvola" / "soffice": aggressiveness bassa (delicato, spazioso)"""


def interpret_creative_brief(brief_text: str, on_token=None) -> dict:
    """Translates a free-text, non-technical creative brief (e.g. "voglio
    che suoni più caldo e la voce più indietro") into adjustments on the
    wizard's existing aggressiveness/warmth/vocal_prominence knobs. Empty
    dict if the model isn't available, the brief is blank, or the model's
    output doesn't parse -- callers must fall back to the wizard's own
    slider values in that case, never block or guess on this. The caller
    (mixengine/api.py) still runs every value through
    director_safety.clamp_params before it can reach MixPreferences, so an
    over-eager interpretation ("make it sound like a monster") can nudge
    within the existing safe ranges but can never exceed them."""
    model = _get_model()
    if model is None or not brief_text or not brief_text.strip():
        return {}

    prompt = (
        "Sei un mix engineer. Un utente non tecnico ha scritto una richiesta "
        "in linguaggio naturale per il suo mix. Traducila in una piccola "
        "regolazione di al massimo questi 3 parametri:\n"
        "- aggressiveness: intero 1-5 (1=delicato, 5=molto compresso/aggressivo)\n"
        "- warmth: numero -1.0 a 1.0 (negativo=freddo/brillante, positivo=caldo)\n"
        "- vocal_prominence: numero -1.0 a 1.0 (negativo=voce PIU' INDIETRO/meno protagonista, "
        "positivo=voce PIU' AVANTI/protagonista)\n\n"
        "L'utente potrebbe usare metafore di colori o elementi invece di termini tecnici -- "
        "traducile secondo questa guida:\n"
        f"{_COLOR_TO_KNOB_HINTS}\n\n"
        "REGOLE FERREE:\n"
        "1. Includi SOLO i parametri esplicitamente e chiaramente richiesti. Se la richiesta "
        "non menziona affatto un aspetto, NON includerlo -- non indovinare, non aggiungere "
        "parametri 'di cortesia'.\n"
        "2. Se la richiesta dice che va bene così, che non c'è nulla da cambiare, o è troppo vaga "
        "per implicare un parametro specifico, rispondi con un oggetto vuoto: {}\n"
        "3. Controlla due volte il segno di vocal_prominence: 'più indietro' o 'meno protagonista' "
        "è SEMPRE un numero NEGATIVO, mai positivo.\n"
        "4. Piccoli aggiustamenti, mai valori estremi.\n\n"
        "Esempi:\n"
        'Richiesta: "va tutto bene così, nessuna modifica particolare"\n'
        "Risposta: {}\n\n"
        'Richiesta: "la voce deve stare più indietro nel mix"\n'
        'Risposta: {"vocal_prominence": -0.4}\n\n'
        'Richiesta: "vorrei un suono più caldo"\n'
        'Risposta: {"warmth": 0.5}\n\n'
        'Richiesta: "rendilo eterei e sognante"\n'
        'Risposta: {"aggressiveness": 1.5}\n\n'
        'Richiesta: "incendia il brano"\n'
        'Risposta: {"aggressiveness": 4.5}\n\n'
        f'Richiesta dell\'utente: "{brief_text.strip()}"\n'
        "Risposta (SOLO l'oggetto JSON, nient'altro):"
    )

    try:
        if on_token is not None:
            text = ""
            stream = model.create_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.2,
                stream=True,
            )
            for chunk in stream:
                delta = chunk["choices"][0].get("delta", {})
                fragment = delta.get("content")
                if fragment:
                    text += fragment
                    on_token(fragment)
        else:
            result = model.create_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.2,
            )
            text = result["choices"][0]["message"]["content"]

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {}
        parsed = json.loads(match.group(0))

        lowered_brief = brief_text.lower()
        return {
            k: v
            for k, v in parsed.items()
            if k in BRIEF_ADJUSTABLE_KEYS
            and any(kw in lowered_brief for kw in _BRIEF_RELEVANCE_KEYWORDS[k])
        }
    except Exception:
        logger.warning("LLM creative brief interpretation failed — returning empty", exc_info=True)
        return {}


# The acoustic dictionary the Module 2 prompt is built from -- kept as data
# (not embedded free-form in the prompt string) so it's the one place to
# extend if more translations are needed later.
#
# Includes the same color/element metaphor vocabulary as
# _COLOR_TO_KNOB_HINTS above (Module 1), translated to EQ moves instead of
# warmth/aggressiveness knobs -- a section-scoped "rendi il ritornello più
# dorato" deserves the same metaphor handling a whole-song creative brief
# already gets, not a flat rejection just because it landed in the other
# feature. A metaphor genuinely absent from this list (e.g. "come un
# elefante che vola nello spazio") still has nothing to map to an EQ move
# and is correctly rejected -- this dictionary is deliberately not a
# catch-all for arbitrary imagery, only for vocabulary confirmed to have a
# real, reasoned acoustic translation.
_ACOUSTIC_DICTIONARY = """\
- "Caldo" / "Corpo" / "Pieno": aumento (gain_db positivo) in banda 200-500Hz (type: "bell", freq: 250-400)
- "Aperto" / "Aria" / "Cristallino": high-shelf positivo sopra i 10kHz (type: "high_shelf", freq: 10000-12000)
- "Presenza" / "Avanti": aumento in banda 2-5kHz (type: "bell", freq: 3000)
- "Nasale" / "Inscatolato": taglio (gain_db negativo) intorno a 800-1000Hz (type: "bell", freq: 900)
- "Oro" / "Dorato" / "Ambra" / "Viola": aumento caldo in banda 200-500Hz (type: "bell", freq: 250-400), come "Caldo"
- "Blu" / "Ghiaccio" / "Gelo" / "Acciaio": taglio high-shelf sopra i 10kHz (type: "high_shelf", freq: 10000-12000, gain_db negativo), il contrario di "Aperto"
- "Fuoco" / "Incendia" / "Brucia" / "Fiamma" / "Rosso": aumento deciso in banda 2-5kHz (type: "bell", freq: 3000), come "Presenza" ma più marcato
- "Eterei" / "Sognante" / "Nuvola": high-shelf positivo delicato sopra i 10kHz (type: "high_shelf", freq: 10000-12000, gain_db piccolo)"""


def interpret_dsp_request(user_text: str, structure_map: list[dict], on_token=None) -> dict | None:
    """Module 2 (NLP-to-DSP): translates a free-text request that names a
    specific song section (e.g. "nel ritornello vorrei più aria e corpo")
    into a section-scoped EQ adjustment. `structure_map` is the output of
    redline.structure.analyze_structure() -- the model is only ever given
    the section names/boundaries that were actually measured, and is
    explicitly told to only use those.

    Returns the model's raw parsed JSON (untouched) or None if unavailable/
    unparseable. Callers MUST still run this through
    director_safety.validate_dsp_automation() before acting on it -- this
    function only talks to the model, it does not itself decide whether a
    section name or a gain value is safe to use."""
    model = _get_model()
    if model is None or not user_text or not user_text.strip():
        return None

    sections_listing = "\n".join(
        f'- "{s["name"]}": da {s["start"]}s a {s["end"]}s' for s in structure_map
    )

    prompt = (
        "RUOLO: Sei l'Assistente DSP del RedLine Engine. Il tuo compito è tradurre "
        "una richiesta in linguaggio naturale in un JSON di configurazione tecnica.\n\n"
        "IL TUO DIZIONARIO ACUSTICO (regole di traduzione):\n"
        f"{_ACOUSTIC_DICTIONARY}\n\n"
        "STRUTTURA MISURATA DEL BRANO (usa SOLO questi nomi di sezione, mai inventarne altri):\n"
        f"{sections_listing}\n"
        '- "global": l\'intero brano\n\n'
        "REGOLE DI ESECUZIONE:\n"
        "1. Identifica se l'utente sta parlando di una sezione specifica elencata sopra, oppure "
        "dell'intero brano (global).\n"
        "2. Se la richiesta non nomina o non implica chiaramente nessuna sezione specifica, usa \"global\".\n"
        "3. Mappa le sue parole al dizionario acustico. Includi SOLO gli aggiustamenti EQ realmente "
        "impliciti nella richiesta, massimo 2.\n"
        "4. Rispondi ESCLUSIVAMENTE con un oggetto JSON valido in questo schema esatto, nessun testo extra:\n"
        '{"target_section": "chorus_1", "dsp_updates": {"eq_adjustments": '
        '[{"type": "bell", "freq": 250, "gain_db": 2.0}]}, "ui_feedback_message": "breve conferma in italiano"}\n\n'
        f'Richiesta dell\'utente: "{user_text.strip()}"\n'
        "Risposta (SOLO l'oggetto JSON):"
    )

    try:
        if on_token is not None:
            text = ""
            stream = model.create_chat_completion(
                messages=[{"role": "user", "content": prompt}], max_tokens=300, temperature=0.2, stream=True,
            )
            for chunk in stream:
                fragment = chunk["choices"][0].get("delta", {}).get("content")
                if fragment:
                    text += fragment
                    on_token(fragment)
        else:
            result = model.create_chat_completion(
                messages=[{"role": "user", "content": prompt}], max_tokens=300, temperature=0.2,
            )
            text = result["choices"][0]["message"]["content"]

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        return json.loads(match.group(0))
    except Exception:
        logger.warning("LLM DSP request interpretation failed — returning None", exc_info=True)
        return None
