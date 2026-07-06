"""Thin bridge between the web UI and the existing engine. Every method here
is exposed to JS via pywebview and just calls straight into redline/*.py —
no engine logic is duplicated, this only adapts inputs/outputs and narration
target (window.evaluate_js instead of print())."""

from __future__ import annotations

import json
import os
import queue
import threading
import time
import traceback

import numpy as np
import soundfile as sf
import webview

from redline import config
from redline.director import DirectorGate
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
        # One gate per Api instance is fine -- only one render_pipeline call
        # runs at a time from this UI, so there's never a second checkpoint
        # racing the first for the same gate.
        self.director_gate = DirectorGate()

        # Async JS eval queue: the DSP pipeline can fire dozens of
        # onStep/onEvent calls per second during a render, and pywebview's
        # .NET/COM bridge serializes each evaluate_js call synchronously.
        # A background thread drains the queue so the pipeline never blocks
        # on UI updates.
        self._js_queue: queue.Queue[str | None] = queue.Queue()
        self._js_worker: threading.Thread | None = None
        self._start_js_worker()

    def _start_js_worker(self) -> None:
        """Daemon thread that drains the JS eval queue. A sentinel None shuts
        it down cleanly. Drops stale entries when the queue grows beyond 60
        items (roughly 1 second of 60fps frames) — the UI only needs the
        latest state, not every intermediate value. Also rate-limits actual
        evaluate_js calls to 60fps (~16.7ms) so the .NET/COM bridge never
        queues up stale frames."""
        _JS_THROTTLE_S = 1.0 / 60.0

        def _drain() -> None:
            last_js_time = 0.0
            while True:
                js = self._js_queue.get()
                if js is None:
                    return  # sentinel shutdown
                # Drain stale entries: if the queue has piled up, skip all
                # but the most recent one to keep the UI responsive.
                while not self._js_queue.empty():
                    try:
                        next_js = self._js_queue.get_nowait()
                        if next_js is None:
                            return  # sentinel while draining
                        js = next_js
                    except queue.Empty:
                        break
                # 60fps throttle: skip if we just sent a frame
                now = time.perf_counter()
                if now - last_js_time < _JS_THROTTLE_S:
                    continue
                last_js_time = now
                if self.window is not None:
                    try:
                        self.window.evaluate_js(js)
                    except Exception:
                        pass  # window may be closing — swallow silently

        self._js_worker = threading.Thread(target=_drain, daemon=True, name="js-eval-worker")
        self._js_worker.start()

    def _stop_js_worker(self) -> None:
        """Signal the worker to shut down (called implicitly when the Api
        instance is discarded)."""
        if self._js_worker is not None and self._js_worker.is_alive():
            self._js_queue.put(None)
            self._js_worker = None

    def _narrate(self, msg: str) -> None:
        self._js_queue.put(f"onStep({json.dumps(str(msg))})")

    def _emit(self, evt: dict) -> None:
        """Structured, real-valued event (an actual EQ freq/gain, a real
        compressor ratio, a real de-esser band, etc.) — the UI renders the
        corresponding animated module reacting to these exact numbers,
        instead of a generic canned animation loop."""
        self._js_queue.put(f"onEvent({json.dumps(_sanitize_for_json(evt))})")

    def toggle_neural_monitor(self, is_enabled: bool) -> None:
        """Called by the GUI's Neural Monitor switch -- flips the flag for
        this running process only (no .flags.json edit, no restart)."""
        config.set_override("ENABLE_LIVE_AUDITION", is_enabled)
        self._narrate(f"Neural Monitor: {'attivo' if is_enabled else 'disattivo'}")

    def _audition(self, dry: np.ndarray, wet: np.ndarray, sr: int) -> None:
        """Plays a loud/dense before-and-after chunk of the master bus glue
        compression through real speakers, narrating + reflecting avatar
        state around each half. Only ever called from masterengine.py when
        ENABLE_LIVE_AUDITION is on -- any audio-hardware or driver failure
        here must never take down the actual render, hence the broad catch."""
        try:
            from redline.audition import driver, extract_smart_chunk

            chunk_dry = extract_smart_chunk(dry, sr)
            chunk_wet = extract_smart_chunk(wet, sr)

            self._narrate("Neural Monitor: ascolto il segnale grezzo (dry)...")
            self._js_queue.put("setAuditionState('BEFORE')")
            driver.play_chunk(chunk_dry, sr)

            self._narrate("Neural Monitor: ascolto la glue compression applicata (wet)...")
            self._js_queue.put("setAuditionState('AFTER')")
            driver.play_chunk(chunk_wet, sr)

            self._js_queue.put("setAuditionState('IDLE')")
        except Exception as exc:
            traceback.print_exc()
            self._narrate(f"Neural Monitor: errore driver audio ({exc})")

    def approve_director_checkpoint(self) -> None:
        """Called by the GUI's "ENGAGE"/approve button -- unblocks whichever
        render_mix() checkpoint is currently paused waiting for it. Safe to
        call even if nothing is currently waiting (just a no-op set())."""
        self.director_gate.approve()

    def pick_input_path(self) -> str | None:
        result = self.window.create_file_dialog(webview.FOLDER_DIALOG)
        if not result:
            return None
        return result[0]

    def pick_input_file(self) -> str | None:
        result = self.window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=('Audio files', '*.wav;*.mp3;*.flac;*.aiff;*.ogg;*.m4a'),
        )
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
            mixed = render_mix(
                stems, analysis, mix_prefs, on_step=self._narrate, on_event=self._emit,
                director_gate=self.director_gate,
            )

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
                    mastered = render_master(
                        mixed, stems.sample_rate, analysis, platform=platform,
                        on_step=self._narrate, on_event=self._emit,
                        on_audition=self._audition if config.is_enabled("ENABLE_LIVE_AUDITION") else None,
                    )
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
