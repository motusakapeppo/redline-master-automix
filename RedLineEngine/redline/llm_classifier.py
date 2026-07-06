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
        return {}


# Wizard knobs the LLM is allowed to nudge based on a free-text creative
# brief. Deliberately just these three (already user-facing sliders in the
# wizard) -- not raw DSP parameters -- so a bad interpretation is at worst
# "too warm" or "too aggressive", never a broken signal chain.
BRIEF_ADJUSTABLE_KEYS = ("aggressiveness", "warmth", "vocal_prominence")


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
        "- vocal_prominence: numero -1.0 a 1.0 (negativo=voce indietro, positivo=voce protagonista)\n"
        "Includi SOLO i parametri realmente implicati dalla richiesta, ometti gli altri. "
        "Non esagerare mai: piccoli aggiustamenti, mai valori estremi.\n\n"
        f'Richiesta dell\'utente: "{brief_text.strip()}"\n\n'
        "Rispondi SOLO con un oggetto JSON valido, ad esempio "
        '{"warmth": 0.4, "vocal_prominence": 0.3}, nient\'altro.'
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
        return {k: v for k, v in parsed.items() if k in BRIEF_ADJUSTABLE_KEYS}
    except Exception:
        return {}
