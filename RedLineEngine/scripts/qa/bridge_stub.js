/**
 * bridge_stub.js — offline stand-in for the pywebview Python bridge.
 *
 * Loaded as a plain (non-module) script at the TOP of <body>, before
 * app_util.js/app.js, by scripts/qa/run.js. It defines `window.pywebview`
 * with a stub for every public Api method the frontend actually calls
 * (see app/web/app.js's `window.pywebview.api.*` call sites), each returning
 * a resolved promise with plausible, JSON-safe data — so the real UI code
 * paths run end-to-end with zero Python, zero network, zero npm deps.
 *
 * Also sets `window.__QA__ = true` so the in-page runner (and any future
 * app-side code) can tell it is running under the QA harness.
 *
 * MUST NOT: touch the network, require anything, or throw at load time.
 */
(function () {
  "use strict";

  window.__QA__ = true;

  // --- Plausible canned data ------------------------------------------------

  var PRESETS = ["Neutro", "Caldo vinile", "Voce avanti"];

  var PRESET_VALUES = {
    ok: true,
    aggressiveness: 3,
    warmth: 0.2,
    vocal_prominence: 0.3,
    genre_override: "",
    do_mastering: true,
    platform: "auto",
    stereo_width: 0.3,
    transient_attack: 1.0,
    transient_sustain: 0.5,
  };

  var SESSIONS = [
    {
      id: "qa-session-1",
      timestamp: 1750000000,
      stage: "master",
      genre: "Pop / Rock",
      bpm: 120.0,
      key: "A minor",
      lufs: -14.0,
      output_dir: "C:/qa/out/session-1",
    },
  ];

  // 600 min/max pairs per track, deterministic (no Math.random) so the
  // fixture replay + screenshots are byte-stable run to run.
  function makePeaks(seed) {
    var peaks = [];
    for (var i = 0; i < 600; i++) {
      var t = i / 600;
      var env = Math.abs(Math.sin((t + seed) * Math.PI * 6)) * 0.8 + 0.1;
      peaks.push([-env, env]);
    }
    return peaks;
  }

  var WAVEFORM = {
    ok: true,
    sr: 44100,
    duration_sec: 12.0,
    tracks: {
      __MIX__: makePeaks(0.0),
      vocals: makePeaks(0.13),
      instrumental: makePeaks(0.27),
      drums: makePeaks(0.41),
      bass: makePeaks(0.55),
    },
  };

  var PREVIEW_URLS = {
    ok: true,
    urls: {
      no_mix: "_preview/no_mix.wav",
      mix: "_preview/mix.wav",
      master: "_preview/master.wav",
    },
    duration_sec: 12.0,
  };

  var RUN_RESULT = {
    ok: true,
    stage: "master",
    mix_path: "C:/qa/out/mix.wav",
    master_path: "C:/qa/out/master.wav",
    bpm: 120.0,
    key: "A minor",
    genre: "Pop / Rock",
    lufs: -14.0,
  };

  // Built-in character processors for the live selector (mirrors the shape
  // of api.list_builtin_processors: {ok, processors:[{name,label,params}]}).
  var BUILTIN_PROCESSORS = {
    ok: true,
    processors: [
      {
        name: "distortion",
        label: "Distortion",
        params: [{ name: "drive_db", label: "Drive", default: 6.0, min: 0, max: 24, step: 0.5, unit: "dB" }],
      },
      {
        name: "chorus",
        label: "Chorus",
        params: [{ name: "rate_hz", label: "Rate", default: 1.0, min: 0.1, max: 5, step: 0.1, unit: "Hz" }],
      },
    ],
  };

  // --- Stub Api -------------------------------------------------------------

  var api = {
    // Presets
    list_presets: function () { return Promise.resolve(PRESETS.slice()); },
    load_preset: function (name) { return Promise.resolve(Object.assign({ name: name }, PRESET_VALUES)); },
    save_preset: function () { return Promise.resolve({ ok: true }); },
    delete_preset: function () { return Promise.resolve({ ok: true }); },

    // Sessions / history
    list_sessions: function () { return Promise.resolve(SESSIONS.slice()); },
    open_session_folder: function () { return Promise.resolve({ ok: true }); },

    // File pickers — return a plausible path so chooseInput()/startRun()
    // paths can be exercised without a native dialog.
    pick_input_path: function () { return Promise.resolve("C:/qa/input"); },
    pick_input_file: function () { return Promise.resolve("C:/qa/input/mix.wav"); },
    pick_output_dir: function () { return Promise.resolve("C:/qa/out"); },

    // Pipeline
    run_pipeline: function () { return Promise.resolve(Object.assign({}, RUN_RESULT)); },
    reprocess_mix: function () { return Promise.resolve(Object.assign({}, RUN_RESULT, { stage: "mix", master_path: null })); },
    continue_to_mastering: function () { return Promise.resolve(Object.assign({}, RUN_RESULT)); },
    submit_feedback: function () { return Promise.resolve({ ok: true, version: 2, master_path: "C:/qa/out/master_v2.wav" }); },
    undo_mix: function () { return Promise.resolve({ ok: true }); },
    redo_mix: function () { return Promise.resolve({ ok: true }); },

    // Waveform / preview
    get_waveform_peaks: function () { return Promise.resolve(WAVEFORM); },
    get_preview_urls: function () { return Promise.resolve(PREVIEW_URLS); },

    // Export / shell
    export_final: function () { return Promise.resolve({ ok: true, path: "C:/qa/out/export.wav" }); },
    open_folder: function () { return Promise.resolve(null); },

    // Director Mode / instrument questions (the pipeline is "paused" on these
    // in the real app; the stub just acknowledges).
    approve_director_checkpoint: function () { return Promise.resolve(null); },
    answer_instrument_questions: function () { return Promise.resolve(null); },

    // Neural Monitor
    toggle_neural_monitor: function () { return Promise.resolve(null); },

    // Live processor selector (additive; the real bridge may not expose the
    // two enable_* methods yet -- app.js calls them defensively).
    list_builtin_processors: function () { return Promise.resolve(BUILTIN_PROCESSORS); },
    set_character_spec: function () { return Promise.resolve({ ok: true, spec: {} }); },
    enable_processor_variants: function () { return Promise.resolve({ ok: true }); },
    enable_plugin_hosting: function () { return Promise.resolve({ ok: true }); },
    probe_plugin: function (path) {
      return Promise.resolve(path
        ? { ok: true, info: { name: "QA Test Plugin", parameters: [
            { name: "gain", label: "Gain", raw_value: 0.0 },
            { name: "mix", label: "Mix", raw_value: 1.0 },
          ] } }
        : { ok: false, error: "percorso vuoto" });
    },
    set_plugin_path: function (path) { return Promise.resolve({ ok: true, path: path || "" }); },
    get_plugin_path: function () { return Promise.resolve({ ok: true, path: "" }); },

    // System
    system_ready: function () { return Promise.resolve(null); },
  };

  window.pywebview = {
    api: api,
    // pywebview fires this event once the bridge is ready; the real app
    // doesn't listen for it (it polls window.pywebview directly), but
    // dispatching it keeps the stub faithful for any future listener.
    _qaStub: true,
  };

  // Fire the ready event on the next tick, like the real bridge does.
  setTimeout(function () {
    try {
      window.dispatchEvent(new Event("pywebviewready"));
    } catch (e) { /* older engines: ignore */ }
  }, 0);
})();
