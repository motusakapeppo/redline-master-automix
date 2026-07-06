"""Thin bridge between the web UI and the existing engine. Every method here
is exposed to JS via pywebview and just calls straight into redline/*.py —
no engine logic is duplicated, this only adapts inputs/outputs and narration
target (window.evaluate_js instead of print())."""

from __future__ import annotations

import json
import os
import traceback

import numpy as np
import soundfile as sf
import webview

from redline.input_loader import load_auto
from redline.analyze import analyze
from redline.wizard import MixPreferences
from redline.mixengine import render_mix
from redline.masterengine import render_master, render_master_reference


def _sanitize_for_json(data):
    """The engine hands back real numpy scalars everywhere (LUFS, true peak,
    band ratios, etc. from librosa/scipy/pyloudnorm) — json.dumps chokes on
    numpy's own float32/float64/int64 types ("Object of type float32 is not
    JSON serializable"), which crashed every render right after the QC step
    tried to report its (numpy-typed) measurements. Recursively coerces
    numpy scalars/arrays to native Python types before anything is
    JSON-encoded for the webview bridge."""
    if isinstance(data, dict):
        return {k: _sanitize_for_json(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [_sanitize_for_json(v) for v in data]
    if isinstance(data, np.ndarray):
        return _sanitize_for_json(data.tolist())
    if isinstance(data, np.floating):
        return float(data)
    if isinstance(data, np.integer):
        return int(data)
    if isinstance(data, np.bool_):
        return bool(data)
    return data


class Api:
    def __init__(self) -> None:
        self.window: webview.Window | None = None

    def _narrate(self, msg: str) -> None:
        if self.window is not None:
            self.window.evaluate_js(f"onStep({json.dumps(str(msg))})")

    def _emit(self, evt: dict) -> None:
        """Structured, real-valued event (an actual EQ freq/gain, a real
        compressor ratio, a real de-esser band, etc.) — the UI renders the
        corresponding animated module reacting to these exact numbers,
        instead of a generic canned animation loop."""
        if self.window is not None:
            self.window.evaluate_js(f"onEvent({json.dumps(_sanitize_for_json(evt))})")

    def pick_input_path(self) -> str | None:
        result = self.window.create_file_dialog(webview.FOLDER_DIALOG)
        if not result:
            return None
        return result[0]

    def pick_output_dir(self) -> str | None:
        result = self.window.create_file_dialog(webview.FOLDER_DIALOG)
        if not result:
            return None
        return result[0]

    def run_pipeline(self, input_path: str, prefs: dict, out_dir: str) -> dict:
        try:
            os.makedirs(out_dir, exist_ok=True)

            self._narrate("Carico l'audio...")
            stems = load_auto(input_path, work_dir=os.path.join(out_dir, "_demucs"), on_step=self._narrate)
            self._narrate(f"Caricati {len(stems.names())} stem: {', '.join(stems.names())} @ {stems.sample_rate}Hz")

            self._narrate("Analizzo bpm, tonalità, genere, loudness e bilanciamento spettrale...")
            analysis = analyze(stems)
            self._narrate(
                f"BPM {analysis.bpm:.1f}  |  Tonalità {analysis.key_name}  |  Genere {analysis.genre.name}  |  "
                f"{analysis.mix_lufs:.1f} LUFS  |  Crest {analysis.mix_crest:.1f}"
            )

            mix_prefs = MixPreferences(
                aggressiveness=int(prefs.get("aggressiveness", 3)),
                warmth=float(prefs.get("warmth", 0.0)),
                vocal_prominence=float(prefs.get("vocal_prominence", 0.0)),
                genre_override=prefs.get("genre_override") or None,
                do_mastering=bool(prefs.get("do_mastering", True)),
            )

            self._narrate("Avvio il mix...")
            mixed = render_mix(stems, analysis, mix_prefs, on_step=self._narrate, on_event=self._emit)

            mix_path = os.path.join(out_dir, "mix.wav")
            sf.write(mix_path, mixed, stems.sample_rate)
            self._narrate(f"Mix salvato: {mix_path}")

            master_path = None
            if mix_prefs.do_mastering:
                self._narrate("Avvio il mastering...")
                reference = prefs.get("reference") or None
                if reference:
                    master_path = os.path.join(out_dir, "master.wav")
                    render_master_reference(mix_path, reference, master_path, on_step=self._narrate)
                else:
                    platform = prefs.get("platform", "auto")
                    mastered = render_master(mixed, stems.sample_rate, analysis, platform=platform, on_step=self._narrate, on_event=self._emit)
                    master_path = os.path.join(out_dir, "master.wav")
                    sf.write(master_path, mastered, stems.sample_rate)
                self._narrate(f"Master salvato: {master_path}")

            self._narrate("Fatto.")
            return _sanitize_for_json({
                "ok": True,
                "mix_path": mix_path,
                "master_path": master_path,
                "bpm": analysis.bpm,
                "key": analysis.key_name,
                "genre": analysis.genre.name,
                "lufs": analysis.mix_lufs,
            })
        except Exception as exc:
            traceback.print_exc()
            self._narrate(f"Errore: {exc}")
            return {"ok": False, "error": str(exc)}

    def open_folder(self, path: str) -> None:
        os.startfile(path)  # noqa: S606 — Windows-only app, opening a folder the user just produced
