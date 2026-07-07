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
        self._window: webview.Window | None = None
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

        # Post-render re-evaluation cache: the three stages of the last
        # successful render (raw stems summed / mixed / mastered), plus
        # enough context (analysis, sr, platform, out_dir, version counter)
        # to run a fast re-mastering-only pass from user feedback without
        # re-running the expensive mix stage from scratch.
        self._last_dry: np.ndarray | None = None
        self._last_mix: np.ndarray | None = None
        self._last_master: np.ndarray | None = None
        self._last_sr: int | None = None
        self._last_analysis = None
        self._last_platform: str = "auto"
        self._last_out_dir: str | None = None
        self._feedback_version: int = 1

    def _start_js_worker(self) -> None:
        """Daemon thread that drains the JS eval queue. A sentinel None shuts
        it down cleanly. Rate-limits actual evaluate_js calls to 60fps
        (~16.7ms) so the .NET/COM bridge never queues up stale frames.

        IMPORTANT: this used to discard every queued call except the very
        last one whenever the queue had more than one item backed up --
        which, during a real render (dozens of onStep/onEvent calls per
        second, far faster than one evaluate_js round-trip), was nearly
        every cycle. In practice this silently dropped most EQ/compressor/
        masking/etc. events before they ever reached the browser: the EQ
        curve stayed flat, most per-stem stage badges never lit up, because
        the events that would have driven them were thrown away here, not
        because the DSP wasn't running. Fixed by batching every pending call
        into one `;`-joined evaluate_js instead of overwriting -- one round
        trip per drain cycle still (keeping the throttle's benefit), but no
        event is lost. Capped defensively so a pathological backlog can't
        build one unbounded eval string."""
        _JS_THROTTLE_S = 1.0 / 60.0
        _MAX_BATCH = 500

        def _drain() -> None:
            last_js_time = 0.0
            while True:
                js = self._js_queue.get()
                if js is None:
                    return  # sentinel shutdown
                batch = [js]
                # Collect whatever else is already waiting into the same
                # batch instead of discarding it -- every call still gets
                # delivered, just coalesced into fewer evaluate_js round trips.
                while len(batch) < _MAX_BATCH:
                    try:
                        next_js = self._js_queue.get_nowait()
                    except queue.Empty:
                        break
                    if next_js is None:
                        return  # sentinel while draining
                    batch.append(next_js)
                # 60fps throttle: wait out the remainder of the frame instead
                # of dropping the batch we just collected.
                now = time.perf_counter()
                wait = _JS_THROTTLE_S - (now - last_js_time)
                if wait > 0:
                    time.sleep(wait)
                last_js_time = time.perf_counter()
                if self._window is not None:
                    try:
                        self._window.evaluate_js(';\n'.join(batch))
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

    def system_ready(self) -> None:
        """Emit a system_ready event so the UI knows the Python bridge is
        fully initialized and the window has finished loading. Called from
        main.py's _on_loaded callback."""
        self._emit({"type": "system_ready"})

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

    def toggle_director_mode(self, is_manual: bool) -> None:
        """Called by the GUI's AUTO/MANUALE switch. AUTO (default) is the
        common case -- the engine classifies stems and proceeds without
        interrupting the render. MANUAL re-enables the Director Mode
        checkpoint (pipeline pauses for the user to confirm stem
        classification before continuing), for sessions where the auto
        classification needs a human sanity check."""
        config.set_override("ENABLE_DIRECTOR_MODE", is_manual)
        self._narrate(f"Modalità: {'MANUALE (conferma richiesta)' if is_manual else 'AUTOMATICA'}")

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

    def _audition_mix_stem(self, name: str, dry: np.ndarray, wet: np.ndarray, sr: int) -> None:
        """Same before/after audition as _audition above, but per-track
        during the mix stage instead of once on the master bus. Only ever
        called from mixengine.py's render_mix (main thread, after each
        stem's parallel processing result is back) when ENABLE_LIVE_AUDITION
        is on -- never from inside the per-stem thread pool, so concurrent
        stems never contend for the audio device at once."""
        try:
            from redline.audition import driver, extract_smart_chunk

            chunk_dry = extract_smart_chunk(dry, sr)
            chunk_wet = extract_smart_chunk(wet, sr)

            self._narrate(f"Neural Monitor: '{name}' grezzo (dry)...")
            self._js_queue.put("setAuditionState('BEFORE')")
            driver.play_chunk(chunk_dry, sr)

            self._narrate(f"Neural Monitor: '{name}' dopo l'elaborazione (wet)...")
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
        result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        if not result:
            return None
        return result[0]

    def pick_input_file(self) -> str | None:
        result = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=('Audio files', '*.wav;*.mp3;*.flac;*.aiff;*.ogg;*.m4a'),
        )
        if not result:
            return None
        return result[0]

    def pick_output_dir(self) -> str | None:
        result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
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

            aggressiveness = float(prefs.get("aggressiveness", 3))
            warmth = float(prefs.get("warmth", 0.0))
            vocal_prominence = float(prefs.get("vocal_prominence", 0.0))

            creative_brief = (prefs.get("creative_brief") or "").strip()
            if creative_brief:
                from redline.llm_classifier import interpret_creative_brief, is_available
                from redline.director_safety import clamp_params

                if is_available():
                    self._narrate(f"Interpreto la richiesta: \"{creative_brief}\"...")
                    raw_adjustments = interpret_creative_brief(creative_brief)
                    adjustments, corrections = clamp_params(raw_adjustments)
                    if adjustments:
                        aggressiveness = adjustments.get("aggressiveness", aggressiveness)
                        warmth = adjustments.get("warmth", warmth)
                        vocal_prominence = adjustments.get("vocal_prominence", vocal_prominence)
                        self._narrate(
                            "Richiesta applicata: " + ", ".join(f"{k}={v}" for k, v in adjustments.items())
                        )
                    if corrections:
                        self._narrate("Nota: " + "; ".join(corrections))
                else:
                    self._narrate("Richiesta libera ignorata: modello LLM locale non disponibile.")

            mix_prefs = MixPreferences(
                aggressiveness=int(round(aggressiveness)),
                warmth=warmth,
                vocal_prominence=vocal_prominence,
                genre_override=prefs.get("genre_override") or None,
                do_mastering=bool(prefs.get("do_mastering", True)),
            )

            self._narrate("Avvio il mix...")
            mixed = render_mix(
                stems, analysis, mix_prefs, on_step=self._narrate, on_event=self._emit,
                director_gate=self.director_gate,
                on_stem_audition=self._audition_mix_stem if config.is_enabled("ENABLE_LIVE_AUDITION") else None,
            )

            mix_path = os.path.join(out_dir, "mix.wav")
            sf.write(mix_path, mixed, stems.sample_rate)
            self._narrate(f"Mix salvato: {mix_path}")

            # Cache for the post-render "NO MIX / CON MIX / CON MASTERING"
            # in-app audition and the feedback re-mastering pass below.
            # Raw stems are just summed dry (no panning/leveling/EQ) -- the
            # simplest honest definition of "before" to compare against.
            dry_sum = np.zeros_like(mixed)
            for track in stems.tracks.values():
                dry_sum += track
            self._last_dry = dry_sum
            self._last_mix = mixed
            self._last_master = None
            self._last_sr = stems.sample_rate
            self._last_analysis = analysis
            self._last_out_dir = out_dir
            self._feedback_version = 1

            master_path = None
            if mix_prefs.do_mastering:
                self._narrate("Avvio il mastering...")
                reference = prefs.get("reference") or None
                if reference:
                    master_path = os.path.join(out_dir, "master.wav")
                    render_master_reference(mix_path, reference, master_path, on_step=self._narrate)
                else:
                    platform = prefs.get("platform", "auto")
                    self._last_platform = platform
                    mastered = render_master(
                        mixed, stems.sample_rate, analysis, platform=platform,
                        on_step=self._narrate, on_event=self._emit,
                        on_audition=self._audition if config.is_enabled("ENABLE_LIVE_AUDITION") else None,
                    )
                    master_path = os.path.join(out_dir, "master.wav")
                    sf.write(master_path, mastered, stems.sample_rate)
                    self._last_master = mastered
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

    def audition_stage(self, stage: str) -> dict:
        """Post-render re-evaluation: play a chunk of one of the three
        cached stages (dry stems / mixed / mastered) through real speakers
        so the user can A/B them in-app instead of only in a file browser.
        Independent of the live "Neural Monitor" toggle -- this is an
        explicit, one-off listen request, not the automatic before/after
        during a render."""
        buffers = {"dry": self._last_dry, "mix": self._last_mix, "master": self._last_master}
        buf = buffers.get(stage)
        if buf is None or self._last_sr is None:
            return {"ok": False, "error": "Nessun render disponibile per questo stadio."}
        try:
            from redline.audition import driver, extract_smart_chunk

            chunk = extract_smart_chunk(buf, self._last_sr)
            self._narrate(f"Ascolto: {stage}...")
            driver.play_chunk(chunk, self._last_sr)
            return {"ok": True}
        except Exception as exc:
            traceback.print_exc()
            return {"ok": False, "error": str(exc)}

    def submit_feedback(self, text: str) -> dict:
        """Fast re-evaluation pass: re-runs ONLY the mastering stage (cheap)
        against the already-cached mix (the expensive stage), nudged by a
        few keyword-driven adjustments parsed from free-text feedback, and
        writes a new versioned master file. Does not re-run the mix itself
        -- that's the whole point of being faster than starting over."""
        if self._last_mix is None or self._last_sr is None or self._last_analysis is None:
            return {"ok": False, "error": "Nessun mix disponibile da ricalibrare."}
        if self._last_out_dir is None:
            return {"ok": False, "error": "Cartella di output non disponibile."}

        try:
            from pedalboard import Pedalboard, Gain, HighShelfFilter, LowShelfFilter

            lower = (text or "").lower()

            def any_kw(*words: str) -> bool:
                return any(w in lower for w in words)

            self._narrate(f"Ricalibro in base al feedback: \"{text}\"...")

            mastered = render_master(
                self._last_mix, self._last_sr, self._last_analysis,
                platform=self._last_platform,
                on_step=self._narrate, on_event=self._emit,
                on_audition=None,
            )

            # Lightweight, honest post-adjustment layer -- these do NOT
            # re-run the full mastering chain's internal decisions, they
            # nudge the already-mastered signal based on the feedback's
            # plain-language intent. Clamped modestly so repeated feedback
            # can't runaway the gain/tone over successive versions.
            fx: list = []
            if any_kw("più caldo", "piu caldo", "warmer", "caldo"):
                fx.append(LowShelfFilter(cutoff_frequency_hz=200.0, gain_db=1.5))
                fx.append(HighShelfFilter(cutoff_frequency_hz=8000.0, gain_db=-1.0))
            if any_kw("più brillante", "piu brillante", "brighter", "più aria", "piu aria"):
                fx.append(HighShelfFilter(cutoff_frequency_hz=8000.0, gain_db=1.5))
            if any_kw("più forte", "piu forte", "più alto", "piu alto", "louder", "più volume", "piu volume"):
                fx.append(Gain(gain_db=1.5))
            if any_kw("più piano", "piu piano", "meno forte", "quieter", "più basso", "piu basso"):
                fx.append(Gain(gain_db=-1.5))

            if fx:
                board = Pedalboard(fx)
                mastered = board(mastered.T, self._last_sr).T
                # Safety clamp: the nudges above are additive gain/tone
                # tweaks, not a full remaster with its own limiter pass, so
                # clip defensively instead of trusting headroom survived.
                peak = float(np.max(np.abs(mastered)))
                if peak > 0.99:
                    mastered = mastered * (0.99 / peak)

            self._feedback_version += 1
            master_path = os.path.join(self._last_out_dir, f"master_v{self._feedback_version}.wav")
            sf.write(master_path, mastered, self._last_sr)
            self._last_master = mastered
            self._narrate(f"Nuova versione salvata: {master_path}")
            return _sanitize_for_json({"ok": True, "master_path": master_path, "version": self._feedback_version})
        except Exception as exc:
            traceback.print_exc()
            self._narrate(f"Errore nella ricalibrazione: {exc}")
            return {"ok": False, "error": str(exc)}
