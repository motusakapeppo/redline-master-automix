"""Thin bridge between the web UI and the existing engine. Every method here
is exposed to JS via pywebview and just calls straight into redline/*.py —
no engine logic is duplicated, this only adapts inputs/outputs and narration
target (window.evaluate_js instead of print())."""

from __future__ import annotations

import copy
import json
import logging
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
from redline.analyze import analyze, apply_genre_override
from redline.presets import PresetManager
from redline.session_history import SessionHistory
from redline.wizard import MixPreferences
from redline.mixengine import render_mix
from redline.masterengine import render_master, render_master_reference
from redline.dsp_utils import finalize_for_export
from redline.processors import available_processors, describe_processor
from redline.plugins import (
    is_plugin_hosting_available,
    load_external_plugin,
    describe_plugin,
)


def _downsample_peaks(audio: np.ndarray, points: int) -> list[list[float]]:
    """[min, max] pair per chunk, mono-summed -- a cheap, honest waveform
    envelope for canvas rendering without shipping raw sample data to JS."""
    mono = audio.mean(axis=1) if audio.ndim == 2 else audio
    n = mono.shape[0]
    if n == 0:
        return []
    chunk = max(1, n // max(1, points))
    peaks = []
    for i in range(0, n, chunk):
        seg = mono[i:i + chunk]
        if seg.size == 0:
            continue
        peaks.append([round(float(np.min(seg)), 4), round(float(np.max(seg)), 4)])
    return peaks


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


_MIX_HISTORY_CAP = 8

# The 7 neutral-by-default mix parameters added in the "universalization" pass.
# They must survive load_preset/save_preset/_build_mix_prefs, otherwise a
# built-in preset that sets one (e.g. Lo-Fi's saturation_amount) would silently
# lose it the moment it passes through the GUI bridge.
_EXTRA_MIX_FIELDS = (
    "mono_compatibility_target",
    "bass_mono_below_hz",
    "reference_lufs_target",
    "saturation_amount",
    "deess_amount",
    "compression_amount",
    "vocal_reverb_amount",
)


def _extra_mix_kwargs(prefs: dict) -> dict:
    """Extracts the 7 extra mix fields from a raw prefs dict, defaulting each
    to 0.0 (neutral) so an older JSON/preset lacking them stays valid."""
    return {name: float(prefs.get(name, 0.0)) for name in _EXTRA_MIX_FIELDS}


def _wrap_js_call(js: str) -> str:
    """Guard a single queued JS call in its own try/catch.

    ``_drain`` joins every pending call into one ``;``-separated
    ``evaluate_js`` string. Without a per-call guard, one throwing call
    aborts the rest of the joined script -- and the outer Python
    ``except Exception: pass`` swallows the error, so every later event in
    that batch is silently lost. Wrapping each call individually means a
    failure in one can no longer take down its neighbours; the error is
    still surfaced to the browser console instead of vanishing."""
    return f"try {{ {js} }} catch (e) {{ console.error('RedLine event error', e); }}"


class Api:
    def __init__(self) -> None:
        self._window: webview.Window | None = None
        # Set by main.py right after construction -- the local folder the
        # bundled bottle HTTP server already serves at http://127.0.0.1:<port>/,
        # so preview WAVs written under `<web_dir>/_preview/` become playable
        # by a real <audio> element via a plain relative URL, no extra server
        # needed.
        self._web_dir: str | None = None
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
        # The genre detect_genre() actually measured, kept separately from
        # _last_analysis.genre (which may have been replaced by a user
        # override) so reprocess_mix can re-resolve a *different* override
        # against the true measured genre instead of compounding overrides.
        self._last_measured_genre = None
        self._last_platform: str = "auto"
        # Wave 2 (E2): the MixPreferences the last mix was rendered with, so
        # the mastering stage (which runs later, from a separate call) can
        # honour the user's LUFS/mono/bass-mono overrides. None until a mix
        # has been rendered -> render_master falls back to today's behaviour.
        self._last_mix_prefs: MixPreferences | None = None
        self._last_out_dir: str | None = None
        self._feedback_version: int = 1
        # Needed to re-run just the mix stage (DAW "Rielabora il mix") or
        # resume straight to mastering (DAW "Procedi al mastering") without
        # repeating demucs separation + analysis, the two genuinely
        # expensive steps neither of those actions needs to redo.
        self._last_stems = None
        self._last_mix_path: str | None = None

        # Undo/redo for the mix-review DAW ("Rielabora il mix" reprocessing):
        # caches prior mix buffers in memory instead of re-running render_mix
        # (which can take seconds to minutes) -- undo/redo becomes an O(1)
        # buffer swap, not a DSP re-render. Capped at _MIX_HISTORY_CAP
        # entries since each is a full audio buffer (memory, not time, is
        # the real constraint here).
        self._mix_undo_stack: list[dict] = []
        self._mix_redo_stack: list[dict] = []

        # Cooperative cancellation: cancel_run() sets this Event; the pipeline
        # checks it at cheap stage boundaries (before load/analyze/mix/master).
        # Native DSP calls are NOT interrupted mid-flight -- a running
        # render_mix/render_master finishes its current call before the next
        # boundary check can observe the flag. This is a deliberate limitation:
        # there is no safe way to abort a native pedalboard/librosa call.
        self._cancel_event = threading.Event()

        # Additive GUI state for live plugin/processor inspection. Kept on
        # underscore-private attributes so pywebview never exposes them as
        # callable/JSON surface -- only the public methods below touch them.
        self._character_spec: dict = {}
        self._plugin_path: str = ""

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
                        self._window.evaluate_js(';\n'.join(_wrap_js_call(call) for call in batch))
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

    def _beep(self, kind: str = "tick") -> None:
        """Status ping for the Neural Monitor during phases that have no real
        audio to play yet (Demucs separation, BPM/key/loudness analysis,
        reference-track mastering, QC/correction passes) -- a short
        Web-Audio blip on the JS side, not real track audio, so the monitor
        is never dead silent while something is actually running. Gated the
        same way `_audition`/`_audition_mix_stem` are: only when the user
        has the Neural Monitor switch on."""
        if config.is_enabled("ENABLE_LIVE_AUDITION"):
            self._js_queue.put(f"playMonitorBeep({json.dumps(kind)})")

    def _with_heartbeat(self, fn, interval: float = 1.5, kind: str = "tick"):
        """Runs a single blocking call (Demucs separation, full-track
        analysis, ...) on the current thread while a background thread fires
        `_beep` every `interval` seconds -- these calls have no internal
        progress hooks to wire real audition into, so a periodic beep is the
        only way the Neural Monitor can stay audibly "alive" for their
        duration instead of going silent."""
        stop = threading.Event()

        def _tick() -> None:
            while not stop.wait(interval):
                self._beep(kind)

        beeper = threading.Thread(target=_tick, daemon=True)
        beeper.start()
        try:
            return fn()
        finally:
            stop.set()
            beeper.join(timeout=0.1)

    def toggle_neural_monitor(self, is_enabled: bool) -> None:
        """Called by the GUI's Neural Monitor switch -- flips the flag for
        this running process only (no .flags.json edit, no restart)."""
        config.set_override("ENABLE_LIVE_AUDITION", is_enabled)
        self._narrate(f"Neural Monitor: {'attivo' if is_enabled else 'disattivo'}")

    # ------------------------------------------------------------------
    # Live plugin / processor inspection (additive, fail-safe)
    # ------------------------------------------------------------------

    def list_builtin_processors(self) -> dict:
        """Metadata for every built-in character processor, for the GUI's
        processor picker. Fail-safe: any registry error degrades to
        ``{"ok": False, "error": ...}`` instead of raising into the bridge."""
        try:
            return {
                "ok": True,
                "processors": [describe_processor(n) for n in available_processors()],
            }
        except Exception as exc:
            logging.getLogger(__name__).error("list_builtin_processors fallito: %s", exc)
            return {"ok": False, "error": str(exc)}

    def probe_plugin(self, plugin_path: str = "") -> dict:
        """Read-only probe of a user-supplied plugin path.

        Loads + describes the plugin via the fail-safe ``redline.plugins``
        helpers and returns ``{"ok": True, "info": {...}}``. It NEVER loads
        anything into the render path and NEVER raises: an empty/missing path,
        an unavailable plugin host, or a plugin that describes to ``None`` all
        return ``{"ok": False, "error": ...}``. (A native plugin crash is out
        of process in future; for now this is read-only and guarded.)"""
        try:
            if not plugin_path or not isinstance(plugin_path, str):
                return {"ok": False, "error": "Percorso plugin non specificato."}
            if not os.path.exists(plugin_path):
                return {"ok": False, "error": "File plugin non trovato."}
            if not is_plugin_hosting_available():
                return {"ok": False, "error": "Hosting plugin non disponibile."}
            plugin = load_external_plugin(plugin_path)
            if plugin is None:
                return {"ok": False, "error": "Impossibile caricare il plugin."}
            info = describe_plugin(plugin)
            if info is None:
                return {"ok": False, "error": "Il plugin non espone parametri descrivibili."}
            return {"ok": True, "info": _sanitize_for_json(info)}
        except Exception as exc:
            logging.getLogger(__name__).error("probe_plugin(%r) fallito: %s", plugin_path, exc)
            return {"ok": False, "error": str(exc)}

    def get_character_spec(self) -> dict:
        """Return the current per-stem character spec ({} when unset)."""
        return {"ok": True, "spec": copy.deepcopy(self._character_spec)}

    def set_character_spec(self, spec: dict) -> dict:
        """Validate + store a per-stem character spec.

        Only known processor names (from ``available_processors()``) are
        accepted; numeric params are clamped to each processor's declared
        min/max; unknown stems and malformed entries are ignored. Returns the
        normalized spec so the GUI can reflect exactly what was stored."""
        try:
            if not isinstance(spec, dict):
                return {"ok": False, "error": "Spec non valida."}
            known = set(available_processors())
            normalized: dict = {}
            for stem, entry in spec.items():
                if not isinstance(entry, dict):
                    continue
                proc = entry.get("processor")
                if proc not in known:
                    continue
                meta = describe_processor(proc) or {}
                bounds = {p["name"]: p for p in meta.get("params", [])}
                raw_params = entry.get("params") or {}
                params: dict = {}
                if isinstance(raw_params, dict):
                    for pname, pval in raw_params.items():
                        bound = bounds.get(pname)
                        if bound is None:
                            continue
                        try:
                            num = float(pval)
                        except (TypeError, ValueError):
                            continue
                        num = max(float(bound["min"]), min(float(bound["max"]), num))
                        params[pname] = num
                normalized[str(stem)] = {"processor": proc, "params": params}
            self._character_spec = normalized
            return {"ok": True, "spec": copy.deepcopy(normalized)}
        except Exception as exc:
            logging.getLogger(__name__).error("set_character_spec fallito: %s", exc)
            return {"ok": False, "error": str(exc)}

    def get_plugin_path(self) -> dict:
        """Return the currently configured external plugin path ("" if unset)."""
        return {"ok": True, "path": self._plugin_path}

    def set_plugin_path(self, path: str) -> dict:
        """Store the external plugin path. No validation beyond isinstance str
        -- a non-string is normalized to "" rather than rejected."""
        self._plugin_path = path if isinstance(path, str) else ""
        return {"ok": True, "path": self._plugin_path}

    def cancel_run(self) -> dict:
        """Request cooperative cancellation of the running pipeline. The
        pipeline observes this at its next stage boundary; a native DSP call
        already in flight is not interrupted."""
        self._cancel_event.set()
        return {"ok": True, "cancelling": True}

    def _cancelled(self) -> bool:
        """True if a cancel was requested. Cheap, never raises."""
        try:
            return self._cancel_event.is_set()
        except Exception:
            return False

    def _check_cancelled(self) -> dict | None:
        """Stage-boundary guard: returns the cancelled result dict (and
        narrates) when a cancel is pending, else ``None`` so the caller
        continues. Inserted only at cheap boundaries -- never mid-DSP."""
        if self._cancelled():
            self._narrate("Operazione annullata.")
            return {"ok": False, "cancelled": True}
        return None

    # ------------------------------------------------------------------
    # Preset API
    # ------------------------------------------------------------------

    def list_presets(self) -> list[str]:
        """Return all available preset names (built-in + user)."""
        try:
            return PresetManager.list()
        except Exception as exc:
            log = logging.getLogger(__name__)
            log.error("list_presets fallito: %s", exc)
            return []

    def load_preset(self, name: str) -> dict:
        """Load a preset by name and return its values as a serializable dict.

        Returns an ``{"ok": False, "error": ...}`` dict on failure so the
        JS side always gets something JSON-safe.
        """
        try:
            prefs = PresetManager.load(name)
            result = {
                "ok": True,
                "name": name,
                "aggressiveness": prefs.aggressiveness,
                "warmth": prefs.warmth,
                "vocal_prominence": prefs.vocal_prominence,
                "genre_override": prefs.genre_override,
                "do_mastering": prefs.do_mastering,
                "platform": prefs.platform,
                "stereo_width": prefs.stereo_width,
                "transient_attack": prefs.transient_attack,
                "transient_sustain": prefs.transient_sustain,
            }
            for field in _EXTRA_MIX_FIELDS:
                result[field] = getattr(prefs, field)
            return result
        except KeyError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            logging.getLogger(__name__).error("load_preset(%r) fallito: %s", name, exc)
            return {"ok": False, "error": str(exc)}

    def save_preset(self, name: str, prefs: dict) -> dict:
        """Save current slider values as a named user preset.

        Returns ``{"ok": True}`` or ``{"ok": False, "error": ...}``.
        """
        try:
            mp = MixPreferences(
                aggressiveness=int(prefs.get("aggressiveness", 3)),
                warmth=float(prefs.get("warmth", 0.0)),
                vocal_prominence=float(prefs.get("vocal_prominence", 0.0)),
                genre_override=prefs.get("genre_override") or None,
                do_mastering=bool(prefs.get("do_mastering", True)),
                stereo_width=float(prefs.get("stereo_width", 0.0)),
                transient_attack=float(prefs.get("transient_attack", 0.0)),
                transient_sustain=float(prefs.get("transient_sustain", 0.0)),
                **_extra_mix_kwargs(prefs),
            )
            PresetManager.save(mp, name)
            return {"ok": True}
        except (ValueError, OSError) as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            logging.getLogger(__name__).error("save_preset(%r) fallito: %s", name, exc)
            return {"ok": False, "error": str(exc)}

    def delete_preset(self, name: str) -> dict:
        """Delete a user preset by name.

        Returns ``{"ok": True}`` or ``{"ok": False, "error": ...}``.
        """
        try:
            PresetManager.delete(name)
            return {"ok": True}
        except (ValueError, KeyError) as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            logging.getLogger(__name__).error("delete_preset(%r) fallito: %s", name, exc)
            return {"ok": False, "error": str(exc)}

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

    def approve_director_checkpoint(self, corrections: dict | None = None) -> None:
        """Called by the GUI's "ENGAGE" button -- unblocks the
        "stem_classification" Director Mode checkpoint. `corrections` is
        {stem_name: {"role": ..., "layer": ..., "register": ...}} for any
        stem the user overrode via the dropdowns; render_mix ignores/
        validates anything not recognized, so an empty or partial dict is
        always safe -- same contract as answer_instrument_questions below."""
        self.director_gate.answer(corrections or {})

    def answer_instrument_questions(self, answers: dict) -> None:
        """Called by the GUI's instrument-question form -- unblocks the
        "instrument_questions" Director Mode checkpoint with the user's
        chosen category per undetermined stem. `answers` is
        {stem_name: category}; render_mix ignores anything not in its own
        undetermined list, so an empty or partial dict is always safe."""
        self.director_gate.answer(answers)

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

    def _build_mix_prefs(self, prefs: dict) -> MixPreferences:
        """Shared by run_pipeline and reprocess_mix -- turns the raw prefs
        dict (sliders + optional free-text creative brief) into a validated
        MixPreferences, applying the LLM's brief interpretation on top of
        the slider values when a brief is given."""
        aggressiveness = float(prefs.get("aggressiveness", 3))
        warmth = float(prefs.get("warmth", 0.0))
        vocal_prominence = float(prefs.get("vocal_prominence", 0.0))
        stereo_width = float(prefs.get("stereo_width", 0.0))
        transient_attack = float(prefs.get("transient_attack", 0.0))
        transient_sustain = float(prefs.get("transient_sustain", 0.0))

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
                    self._narrate("Richiesta applicata: " + ", ".join(f"{k}={v}" for k, v in adjustments.items()))
                if corrections:
                    self._narrate("Nota: " + "; ".join(corrections))
            else:
                self._narrate("Richiesta libera ignorata: modello LLM locale non disponibile.")

        return MixPreferences(
            aggressiveness=int(round(aggressiveness)),
            warmth=warmth,
            vocal_prominence=vocal_prominence,
            genre_override=prefs.get("genre_override") or None,
            do_mastering=bool(prefs.get("do_mastering", True)),
            platform=str(prefs.get("platform", "auto")),
            stereo_width=stereo_width,
            transient_attack=transient_attack,
            transient_sustain=transient_sustain,
            **_extra_mix_kwargs(prefs),
        )

    def _do_mastering(self, mixed: np.ndarray, stems, analysis, out_dir: str, prefs: dict) -> str | None:
        """Shared by run_pipeline and continue_to_mastering."""
        self._narrate("Avvio il mastering...")
        mix_path = self._last_mix_path or os.path.join(out_dir, "mix.wav")
        reference = prefs.get("reference") or None
        if reference:
            master_path = os.path.join(out_dir, "master.wav")
            render_master_reference(mix_path, reference, master_path, on_step=self._narrate, on_beep=self._beep)
        else:
            platform = prefs.get("platform", "auto")
            self._last_platform = platform
            # Wave 2 (E2): reuse the MixPreferences the mix was rendered with
            # (set by run_pipeline/reprocess_mix) so the user's LUFS/mono/
            # bass-mono overrides reach the mastering stage too. Falls back to
            # building from the raw dict if no mix prefs are cached yet.
            mix_prefs = self._last_mix_prefs or self._build_mix_prefs(prefs)
            mastered = render_master(
                mixed, stems.sample_rate, analysis, platform=platform,
                on_step=self._narrate, on_event=self._emit,
                on_audition=self._audition if config.is_enabled("ENABLE_LIVE_AUDITION") else None,
                on_beep=self._beep,
                prefs=mix_prefs,
            )
            master_path = os.path.join(out_dir, "master.wav")
            sf.write(master_path, finalize_for_export(mastered), stems.sample_rate, subtype="PCM_24")
            self._last_master = mastered
        self._narrate(f"Master salvato: {master_path}")
        return master_path

    def run_pipeline(self, input_path: str, prefs: dict, out_dir: str) -> dict:
        try:
            # Fresh run: drop any stale cancel from a previous run, then check
            # at each cheap stage boundary below (never mid-DSP).
            self._cancel_event.clear()
            os.makedirs(out_dir, exist_ok=True)

            cancelled = self._check_cancelled()
            if cancelled is not None:
                return cancelled

            self._narrate("Carico l'audio...")
            stems = self._with_heartbeat(
                lambda: load_auto(input_path, work_dir=os.path.join(out_dir, "_demucs"), on_step=self._narrate),
                kind="separating",
            )
            self._narrate(f"Caricati {len(stems.names())} stem: {', '.join(stems.names())} @ {stems.sample_rate}Hz")

            cancelled = self._check_cancelled()
            if cancelled is not None:
                return cancelled

            self._narrate("Analizzo bpm, tonalità, genere, loudness e bilanciamento spettrale...")
            analysis = self._with_heartbeat(lambda: analyze(stems), kind="analyzing")
            self._narrate(
                f"BPM {analysis.bpm:.1f}  |  Tonalità {analysis.key_name}  |  Genere {analysis.genre.name}  |  "
                f"{analysis.mix_lufs:.1f} LUFS  |  Crest {analysis.mix_crest:.1f}"
            )

            mix_prefs = self._build_mix_prefs(prefs)

            # A user/preset genre selection replaces the measured genre before
            # any render consumes the analysis -- mixengine's bus EQ,
            # masterengine's LUFS target, fxsends and qc all read
            # analysis.genre, so this single swap makes them all follow it.
            self._last_measured_genre = analysis.genre
            apply_genre_override(analysis, mix_prefs.genre_override)
            if mix_prefs.genre_override:
                self._narrate(f"Genere impostato dall'utente: {analysis.genre.name}")

            cancelled = self._check_cancelled()
            if cancelled is not None:
                return cancelled

            self._narrate("Avvio il mix...")
            mixed = render_mix(
                stems, analysis, mix_prefs, on_step=self._narrate, on_event=self._emit,
                director_gate=self.director_gate,
                on_stem_audition=self._audition_mix_stem if config.is_enabled("ENABLE_LIVE_AUDITION") else None,
                character_spec=self._character_spec or None,
                plugin_path=self._plugin_path or None,
            )

            mix_path = os.path.join(out_dir, "mix.wav")
            sf.write(mix_path, finalize_for_export(mixed), stems.sample_rate, subtype="PCM_24")
            self._narrate(f"Mix salvato: {mix_path}")

            # Cache for the post-render "NO MIX / CON MIX / CON MASTERING"
            # in-app audition, the feedback re-mastering pass, and the DAW
            # review screens (mix reprocessing needs stems+analysis without
            # repeating demucs/analysis; mastering resume needs mixed+stems).
            dry_sum = np.zeros_like(mixed)
            for track in stems.tracks.values():
                dry_sum += track
            self._last_dry = dry_sum
            self._last_mix = mixed
            self._last_master = None
            self._last_sr = stems.sample_rate
            self._last_analysis = analysis
            self._last_mix_prefs = mix_prefs
            self._last_out_dir = out_dir
            self._last_mix_path = mix_path
            self._last_stems = stems
            self._feedback_version = 1
            self._mix_undo_stack.clear()
            self._mix_redo_stack.clear()

            # DAW workflow choice: if the user asked to stop and review the
            # mix before deciding on mastering, return here -- the frontend
            # shows the mix DAW screen instead of the final result screen,
            # and continue_to_mastering()/reprocess_mix() pick up from the
            # cached state above whenever the user is ready.
            if not mix_prefs.do_mastering or bool(prefs.get("stop_after_mix", False)):
                self._narrate("Mix pronto. In attesa di revisione." if bool(prefs.get("stop_after_mix", False)) else "Fatto (solo mix).")
                SessionHistory.add({
                    "input_path": input_path, "output_dir": out_dir, "stage": "mix",
                    "mix_path": mix_path, "master_path": None,
                    "bpm": analysis.bpm, "key": analysis.key_name,
                    "genre": analysis.genre.name, "lufs": analysis.mix_lufs,
                })
                return _sanitize_for_json({
                    "ok": True,
                    "stage": "mix",
                    "mix_path": mix_path,
                    "master_path": None,
                    "bpm": analysis.bpm,
                    "key": analysis.key_name,
                    "genre": analysis.genre.name,
                    "lufs": analysis.mix_lufs,
                })

            cancelled = self._check_cancelled()
            if cancelled is not None:
                return cancelled

            master_path = self._do_mastering(mixed, stems, analysis, out_dir, prefs)

            self._narrate("Fatto.")
            SessionHistory.add({
                "input_path": input_path, "output_dir": out_dir, "stage": "master",
                "mix_path": mix_path, "master_path": master_path,
                "bpm": analysis.bpm, "key": analysis.key_name,
                "genre": analysis.genre.name, "lufs": analysis.mix_lufs,
            })
            return _sanitize_for_json({
                "ok": True,
                "stage": "master",
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

    def get_waveform_peaks(self, points: int = 600) -> dict:
        """Downsampled min/max waveform envelope for every cached stem
        (the raw dry take, not yet DSP-processed) plus the mixed bus, so
        the DAW screen can render real per-track waveforms on a shared
        timeline -- letting the user actually see relative timing/alignment
        at a glance, not just a plugin parameter list with no audio shown
        at all. Raw arrays are never sent to JS (a multi-minute stereo
        stem is tens of MB) -- only a few hundred min/max pairs per track."""
        if self._last_stems is None:
            return {"ok": False, "error": "Nessuno stem in cache."}
        try:
            tracks = {name: _downsample_peaks(audio, points) for name, audio in self._last_stems.tracks.items()}
            if self._last_mix is not None:
                tracks["__MIX__"] = _downsample_peaks(self._last_mix, points)
            duration_sec = float(self._last_mix.shape[0]) / self._last_sr if self._last_mix is not None and self._last_sr else None
            return _sanitize_for_json({
                "ok": True,
                "sr": self._last_sr,
                "duration_sec": duration_sec,
                "tracks": tracks,
            })
        except Exception as exc:
            traceback.print_exc()
            return {"ok": False, "error": str(exc)}

    def continue_to_mastering(self, prefs: dict) -> dict:
        """DAW "Procedi al mastering" button: resumes from the cached mix
        (no re-run of demucs/analysis/mix) and runs only the mastering
        stage, exactly like run_pipeline would have if stop_after_mix
        hadn't been set."""
        if self._last_mix is None or self._last_stems is None or self._last_analysis is None or self._last_out_dir is None:
            return {"ok": False, "error": "Nessun mix in cache da masterizzare."}
        try:
            self._cancel_event.clear()
            cancelled = self._check_cancelled()
            if cancelled is not None:
                return cancelled
            master_path = self._do_mastering(self._last_mix, self._last_stems, self._last_analysis, self._last_out_dir, prefs)
            self._narrate("Fatto.")
            return _sanitize_for_json({
                "ok": True,
                "stage": "master",
                "mix_path": self._last_mix_path,
                "master_path": master_path,
                "bpm": self._last_analysis.bpm,
                "key": self._last_analysis.key_name,
                "genre": self._last_analysis.genre.name,
                "lufs": self._last_analysis.mix_lufs,
            })
        except Exception as exc:
            traceback.print_exc()
            self._narrate(f"Errore: {exc}")
            return {"ok": False, "error": str(exc)}

    def reprocess_mix(self, prefs: dict) -> dict:
        """DAW "Rielabora il mix" button: re-runs only render_mix against
        the already-loaded/analyzed stems (skips demucs separation and
        analysis, the two expensive steps) with new preferences -- either
        edited slider values or a fresh free-text prompt describing what to
        change. Updates the same cache run_pipeline populates, so audition/
        continue_to_mastering keep working against the new result."""
        if self._last_stems is None or self._last_analysis is None or self._last_out_dir is None:
            return {"ok": False, "error": "Nessuno stem in cache da rielaborare."}
        try:
            self._cancel_event.clear()
            cancelled = self._check_cancelled()
            if cancelled is not None:
                return cancelled
            stems = self._last_stems
            out_dir = self._last_out_dir

            # Re-resolve the genre from the *measured* profile (not the
            # possibly-already-overridden cached one) so switching to a
            # different override -- or back to none -- doesn't compound.
            analysis = copy.copy(self._last_analysis)
            analysis.genre = self._last_measured_genre or self._last_analysis.genre

            if self._last_mix is not None:
                self._mix_undo_stack.append({"mixed": self._last_mix, "mix_path": self._last_mix_path})
                if len(self._mix_undo_stack) > _MIX_HISTORY_CAP:
                    self._mix_undo_stack.pop(0)
                self._mix_redo_stack.clear()

            mix_prefs = self._build_mix_prefs(prefs)
            apply_genre_override(analysis, mix_prefs.genre_override)
            if mix_prefs.genre_override:
                self._narrate(f"Genere impostato dall'utente: {analysis.genre.name}")
            self._narrate("Rielaborazione del mix...")
            mixed = render_mix(
                stems, analysis, mix_prefs, on_step=self._narrate, on_event=self._emit,
                director_gate=self.director_gate,
                on_stem_audition=self._audition_mix_stem if config.is_enabled("ENABLE_LIVE_AUDITION") else None,
                character_spec=self._character_spec or None,
                plugin_path=self._plugin_path or None,
            )

            mix_path = os.path.join(out_dir, "mix.wav")
            sf.write(mix_path, finalize_for_export(mixed), stems.sample_rate, subtype="PCM_24")
            self._narrate(f"Mix aggiornato: {mix_path}")

            dry_sum = np.zeros_like(mixed)
            for track in stems.tracks.values():
                dry_sum += track
            self._last_dry = dry_sum
            self._last_mix = mixed
            self._last_master = None
            self._last_mix_path = mix_path
            # Keep the cache in sync so continue_to_mastering/submit_feedback
            # master against the genre this reprocess actually used.
            self._last_analysis = analysis
            self._last_mix_prefs = mix_prefs

            self._narrate("Fatto.")
            return _sanitize_for_json({
                "ok": True,
                "stage": "mix",
                "mix_path": mix_path,
                "master_path": None,
                "bpm": analysis.bpm,
                "key": analysis.key_name,
                "genre": analysis.genre.name,
                "lufs": analysis.mix_lufs,
            })
        except Exception as exc:
            traceback.print_exc()
            self._narrate(f"Errore: {exc}")
            return {"ok": False, "error": str(exc)}

    def list_sessions(self) -> list[dict]:
        """Return past render sessions (most recent first) for the Cronologia
        screen. Never raises -- a history read failure just shows an empty
        list, it must not block the rest of the UI."""
        try:
            return SessionHistory.list()
        except Exception as exc:
            logging.getLogger(__name__).error("list_sessions fallito: %s", exc)
            return []

    def open_session_folder(self, session_id: str) -> dict:
        """Cronologia "apri cartella" button: opens the output folder of a
        past session by id."""
        entry = SessionHistory.get(session_id)
        if not entry or not entry.get("output_dir"):
            return {"ok": False, "error": "Sessione non trovata."}
        try:
            os.startfile(entry["output_dir"])  # noqa: S606
            return {"ok": True}
        except OSError as exc:
            return {"ok": False, "error": str(exc)}

    def undo_mix(self) -> dict:
        """Undo the last "Rielabora il mix": pops the previous mix buffer
        from memory and swaps it back in -- no DSP re-render, just restoring
        an already-computed buffer, so this is near-instant regardless of
        how expensive the original render_mix pass was."""
        if not self._mix_undo_stack or self._last_mix_path is None:
            return {"ok": False, "error": "Niente da annullare."}
        try:
            self._mix_redo_stack.append({"mixed": self._last_mix, "mix_path": self._last_mix_path})
            prev = self._mix_undo_stack.pop()
            self._last_mix = prev["mixed"]
            self._last_mix_path = prev["mix_path"]
            sf.write(self._last_mix_path, finalize_for_export(self._last_mix), self._last_sr, subtype="PCM_24")
            self._narrate("Annullato: torno alla versione precedente del mix.")
            return {"ok": True}
        except Exception as exc:
            traceback.print_exc()
            return {"ok": False, "error": str(exc)}

    def redo_mix(self) -> dict:
        """Redo a previously undone mix reprocessing -- same O(1) buffer
        swap as undo_mix, just from the other stack."""
        if not self._mix_redo_stack or self._last_mix_path is None:
            return {"ok": False, "error": "Niente da ripetere."}
        try:
            self._mix_undo_stack.append({"mixed": self._last_mix, "mix_path": self._last_mix_path})
            nxt = self._mix_redo_stack.pop()
            self._last_mix = nxt["mixed"]
            self._last_mix_path = nxt["mix_path"]
            sf.write(self._last_mix_path, finalize_for_export(self._last_mix), self._last_sr, subtype="PCM_24")
            self._narrate("Ripristinata la versione successiva del mix.")
            return {"ok": True}
        except Exception as exc:
            traceback.print_exc()
            return {"ok": False, "error": str(exc)}

    def open_folder(self, path: str) -> None:
        os.startfile(path)  # noqa: S606 — Windows-only app, opening a folder the user just produced

    def export_final(self, stage: str = "auto") -> dict:
        """One-click export: writes the finished render (master if one was
        produced, otherwise the mix) to a user-chosen path via a native save
        dialog, skipping the "go find it in the output folder" step. Reuses
        whichever buffer run_pipeline/reprocess_mix/submit_feedback already
        cached in memory -- no re-render, no format conversion beyond what
        soundfile infers from the chosen extension (wav/flac/ogg)."""
        buf = self._last_master if (stage == "auto" and self._last_master is not None) else None
        if buf is None:
            buf = {"master": self._last_master, "mix": self._last_mix}.get(stage, self._last_master)
        if buf is None:
            buf = self._last_mix
        if buf is None or self._last_sr is None:
            return {"ok": False, "error": "Nessun render disponibile da esportare."}

        default_name = "master.wav" if buf is self._last_master else "mix.wav"
        result = self._window.create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename=default_name,
            file_types=('WAV (*.wav)', 'FLAC (*.flac)', 'OGG (*.ogg)'),
        )
        if not result:
            return {"ok": False, "error": "Esportazione annullata."}
        dest = result if isinstance(result, str) else result[0]

        try:
            sf.write(dest, finalize_for_export(buf), self._last_sr, subtype="PCM_24")
            self._narrate(f"Esportato: {dest}")
            return {"ok": True, "path": dest}
        except Exception as exc:
            traceback.print_exc()
            return {"ok": False, "error": str(exc)}

    def get_preview_urls(self, loudness_match: bool = False) -> dict:
        """Writes the cached no-mix/mix/master buffers out as real WAV files
        under `<web_dir>/_preview/`, which the bundled bottle HTTP server
        already serves at http://127.0.0.1:<port>/ (see main.py) -- so the
        frontend can point a genuine <audio> element at them for full-track,
        seekable playback with real transport controls, instead of the old
        `audition_stage`/`audition_blend` approach of playing a fixed 2s
        "loudest window" snippet through native speakers via sd.play with no
        scrubbing at all.

        If ``loudness_match=True``, every available stage is normalized to
        -16 LUFS before being written, so switching NO MIX/MIX/MASTERING is
        a fair comparison at equal perceived loudness instead of the
        (usually much louder) mastered version just sounding "better"."""
        if not self._web_dir or self._last_sr is None:
            return {"ok": False, "error": "Nessun render disponibile per l'anteprima."}
        try:
            preview_dir = os.path.join(self._web_dir, "_preview")
            os.makedirs(preview_dir, exist_ok=True)

            sources = {"no_mix": self._last_dry, "mix": self._last_mix, "master": self._last_master}
            if loudness_match:
                from redline.dsp_utils import loudness_match as lm
                sources = {name: (lm(buf, target_lufs=-16.0) if buf is not None else None) for name, buf in sources.items()}

            cache_bust = int(time.time())
            urls: dict[str, str] = {}
            for name, buf in sources.items():
                if buf is None:
                    continue
                sf.write(os.path.join(preview_dir, f"{name}.wav"), finalize_for_export(buf), self._last_sr, subtype="PCM_24")
                urls[name] = f"_preview/{name}.wav?v={cache_bust}"

            duration_sec = float(self._last_mix.shape[0]) / self._last_sr if self._last_mix is not None else None
            return {"ok": True, "urls": urls, "duration_sec": duration_sec}
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
                on_audition=None, on_beep=self._beep,
                prefs=self._last_mix_prefs,
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
            sf.write(master_path, finalize_for_export(mastered), self._last_sr, subtype="PCM_24")
            self._last_master = mastered
            self._narrate(f"Nuova versione salvata: {master_path}")
            return _sanitize_for_json({"ok": True, "master_path": master_path, "version": self._feedback_version})
        except Exception as exc:
            traceback.print_exc()
            self._narrate(f"Errore nella ricalibrazione: {exc}")
            return {"ok": False, "error": str(exc)}
