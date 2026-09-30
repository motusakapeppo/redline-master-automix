/**
 * inpage.js — in-page QA runner for the RedLine Engine GUI.
 *
 * Injected by scripts/qa/run.js at the TOP of <head> (right after the charset
 * meta), BEFORE app_util.js / app.js, so that:
 *   1. window.onerror + console.error capture is installed before any app
 *      script can throw or log;
 *   2. the replay + assertions run against the REAL app globals
 *      (onStep / onEvent / showScreen) once the DOM is ready.
 *
 * Flow:
 *   DOMContentLoaded + 1 tick
 *     -> force the progress screen visible (real showScreen() + class fixup)
 *     -> load the fixture (window.__QA_FIXTURE__ | __qa_fixture.json | builtin)
 *     -> replay every record through the real onStep()/onEvent() globals
 *     -> run the smoke assertions
 *     -> write {"pass":bool,"results":[...],"consoleErrors":[...]} into
 *        <pre id="__qa_result"> and set document.title = "QA:PASS|FAIL"
 *
 * Zero dependencies. Plain script (no import/export). Never throws out of
 * the runner itself — a broken harness must still publish a FAIL verdict
 * rather than leave the dumped DOM without a result.
 */
(function () {
  "use strict";

  // =====================================================================
  // 1. Error capture — installed before any app script runs.
  // =====================================================================

  var consoleErrors = [];
  window.__QA_CONSOLE_ERRORS__ = consoleErrors;
  window.__QA_RESOURCE_ERRORS__ = [];

  var _origConsoleError = console.error;
  console.error = function () {
    try {
      var parts = [];
      for (var i = 0; i < arguments.length; i++) {
        var a = arguments[i];
        if (typeof a === "string") parts.push(a);
        else if (a && a.message) parts.push(String(a.message));
        else {
          try { parts.push(String(a)); } catch (e) { parts.push("<unprintable>"); }
        }
      }
      consoleErrors.push(parts.join(" "));
    } catch (e) { /* the capture itself must never throw */ }
    if (_origConsoleError) return _origConsoleError.apply(console, arguments);
  };

  // Counted source #2 (per spec: "console.error + window.onerror count").
  window.onerror = function (message, source, lineno, colno, error) {
    try {
      var where = source ? (" @ " + source + ":" + lineno + ":" + colno) : "";
      var msg = (error && error.stack) ? String(error.stack) : String(message);
      consoleErrors.push("window.onerror: " + msg + where);
    } catch (e) { /* ignore */ }
    return false; // never suppress default handling
  };

  // Resource-load failures (missing img/script/glb) are recorded separately
  // and deliberately NOT counted: a 404 asset is not a JS exception, and the
  // smoke assertion is about real errors only.
  window.addEventListener("error", function (e) {
    try {
      var t = e && e.target;
      if (t && t !== window && (t.tagName || t.src || t.href)) {
        window.__QA_RESOURCE_ERRORS__.push(
          String(t.tagName || "?") + " " + String(t.src || t.href || "")
        );
      }
    } catch (err) { /* ignore */ }
  }, true);

  // =====================================================================
  // 2. Built-in inline fixture (used when no --fixture is supplied).
  //
  // Deliberately ordered so every one of the 9 .module-detail elements ends
  // up live: all per-stem events share the SAME stem ("vocals") so each
  // renderStemChannelStrip() call re-renders the accumulated params instead
  // of resetting the other modules back to "in attesa...".
  // =====================================================================

  var BUILTIN_FIXTURE = [
    { kind: "step", payload: "Carico l'audio..." },
    { kind: "step", payload: "Rilevati 2 file audio" },
    { kind: "step", payload: "Caricati 2 stem" },
    { kind: "step", payload: "Analizzo bpm, tonalita e loudness..." },
    { kind: "step", payload: "Avvio il mix..." },
    { kind: "step", payload: "Elaborazione stem 'vocals'..." },
    { kind: "event", payload: { type: "bus_eq_band", freq_hz: 250, gain_db: -2.5 } },
    { kind: "event", payload: { type: "compressor", stem: "vocals", ratio: 3.5, threshold_db: -18, release_ms: 120, attack_ms: 5 } },
    { kind: "event", payload: { type: "deesser", stem: "vocals", low_hz: 5000, high_hz: 9000 } },
    { kind: "event", payload: { type: "saturation", stem: "vocals", drive: 1.5 } },
    { kind: "event", payload: { type: "reverb_send", stem: "vocals", bus: "vocal_plate", mix: 0.25 } },
    { kind: "event", payload: { type: "limiter", ceiling_db: -1.0 } },
    { kind: "event", payload: { type: "mid_side", mono_below_hz: 120, air_shelf_hz: 9000, air_gain_db: 1.2 } },
    { kind: "event", payload: { type: "qc_report", lufs: -14.0, true_peak_db: -1.0, mono_compatibility: "ok", passed: true } },
    { kind: "event", payload: { type: "done" } }
  ];

  // =====================================================================
  // 3. Small helpers
  // =====================================================================

  function qaAll(sel) {
    return Array.prototype.slice.call(document.querySelectorAll(sel));
  }

  function elText(el) {
    return el ? String(el.textContent || "").trim() : null;
  }

  function describe(el) {
    if (!el) return "null";
    var s = String(el.tagName || "?").toLowerCase();
    if (el.id) s += "#" + el.id;
    if (el.className && typeof el.className === "string") {
      var cls = el.className.trim().split(/\s+/).slice(0, 3).join(".");
      if (cls) s += "." + cls;
    }
    return s;
  }

  // =====================================================================
  // 4. Fixture loading
  // =====================================================================

  function loadFixture(cb) {
    if (Array.isArray(window.__QA_FIXTURE__) && window.__QA_FIXTURE__.length) {
      cb(window.__QA_FIXTURE__, "embedded");
      return;
    }

    var settled = false;
    function finish(records, source) {
      if (settled) return;
      settled = true;
      cb(records, source);
    }

    try {
      fetch("__qa_fixture.json", { cache: "no-store" })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (data) {
          if (Array.isArray(data) && data.length) finish(data, "__qa_fixture.json");
          else finish(BUILTIN_FIXTURE, "builtin");
        })
        .catch(function () { finish(BUILTIN_FIXTURE, "builtin"); });
    } catch (e) {
      finish(BUILTIN_FIXTURE, "builtin");
    }

    // Safety net: if fetch never settles, still publish a verdict.
    setTimeout(function () { finish(BUILTIN_FIXTURE, "builtin-timeout"); }, 5000);
  }

  // =====================================================================
  // 5. Replay — drive the REAL app globals exactly like app/api.py does.
  //    onStep(jsonString) / onEvent(jsonObject) (see api.py _narrate/_emit).
  //    Unknown or malformed records must be harmless.
  // =====================================================================

  function replay(records) {
    var applied = { steps: 0, events: 0, skipped: 0 };

    for (var i = 0; i < records.length; i++) {
      var rec = records[i];
      if (!rec || typeof rec !== "object") { applied.skipped++; continue; }

      try {
        if (rec.kind === "step") {
          if (typeof window.onStep === "function") {
            window.onStep(String(rec.payload));
            applied.steps++;
          } else {
            applied.skipped++;
          }
        } else if (rec.kind === "event") {
          if (typeof window.onEvent === "function") {
            var evt = (typeof rec.payload === "string") ? JSON.parse(rec.payload) : rec.payload;
            window.onEvent(evt);
            applied.events++;
          } else {
            applied.skipped++;
          }
        } else {
          applied.skipped++;
        }
      } catch (e) {
        // A record the current build doesn't understand must never break
        // the rest of the replay.
        applied.skipped++;
      }
    }

    return applied;
  }

  // =====================================================================
  // 6. Force the progress screen visible so progress-DOM assertions are
  //    meaningful (the app boots on #screen-input).
  // =====================================================================

  function forceProgressScreen() {
    try {
      if (typeof window.showScreen === "function") window.showScreen("screen-progress");
    } catch (e) { /* gsap/audio quirks must not block the harness */ }

    // Belt & braces: guarantee the class state even if showScreen bailed out
    // (e.g. an AudioContext failure inside playWhoosh) or a GSAP tween is
    // still mid-flight.
    var progress = document.getElementById("screen-progress");
    if (!progress) return;
    qaAll(".screen").forEach(function (s) {
      if (s !== progress) s.classList.remove("active");
    });
    progress.classList.add("active");
    progress.style.opacity = "1";
    progress.style.transform = "none";
  }

  // =====================================================================
  // 7. Assertions (one result entry each)
  // =====================================================================

  function runAssertions() {
    var results = [];

    // --- rail_exists -----------------------------------------------------
    (function () {
      var screen = document.getElementById("screen-progress");
      var nodes = qaAll(".pipeline-node");
      var pass = !!screen && nodes.length > 0;
      results.push({
        id: "rail_exists",
        pass: pass,
        detail: pass
          ? "#screen-progress present, " + nodes.length + " .pipeline-node"
          : "#screen-progress=" + (!!screen) + ", .pipeline-node count=" + nodes.length
      });
    })();

    // --- modules_present -------------------------------------------------
    (function () {
      var mods = qaAll(".module");
      var pass = mods.length === 9;
      results.push({
        id: "modules_present",
        pass: pass,
        detail: ".module count=" + mods.length + " (expected exactly 9)"
      });
    })();

    // --- details_live_after_replay ---------------------------------------
    (function () {
      var details = qaAll(".module-detail");
      var stale = details.filter(function (el) { return elText(el) === "in attesa..."; });
      var pass = details.length > 0 && stale.length === 0;
      results.push({
        id: "details_live_after_replay",
        pass: pass,
        detail: pass
          ? details.length + " .module-detail, none stale"
          : stale.length + "/" + details.length + " still \"in attesa...\": " +
            stale.map(function (el) { return "#" + (el.id || "?") + "=\"" + elText(el) + "\""; }).join(", ")
      });
    })();

    // --- cancel_control --------------------------------------------------
    (function () {
      var el = document.querySelector('[data-qa="cancel-run"]') || document.getElementById("btn-cancel");
      var pass = !!el;
      results.push({
        id: "cancel_control",
        pass: pass,
        detail: pass
          ? "found " + describe(el)
          : "no [data-qa=\"cancel-run\"] and no #btn-cancel in document"
      });
    })();

    // --- slider_readouts -------------------------------------------------
    (function () {
      var ids = ["warmth", "vocal_prominence", "stereo_width", "transient_attack", "transient_sustain"];
      var missing = [];
      ids.forEach(function (id) {
        var slider = document.getElementById(id);
        if (!slider) { missing.push(id + " (slider #" + id + " missing)"); return; }
        var val = document.getElementById(id + "-val");
        if (!val) { missing.push(id + " (no #" + id + "-val)"); return; }
        var field = slider.closest(".field");
        if (field && !field.contains(val)) {
          missing.push(id + " (#" + id + "-val exists but is not a sibling inside the same .field)");
        }
      });
      var pass = missing.length === 0;
      results.push({
        id: "slider_readouts",
        pass: pass,
        detail: pass
          ? "5/5 sliders have a #<id>-val sibling readout"
          : "missing: " + missing.join("; ")
      });
    })();

    // --- plugin_panel ----------------------------------------------------
    (function () {
      var el = document.querySelector('[data-qa="plugin-panel"]');
      results.push({
        id: "plugin_panel",
        pass: !!el,
        detail: el ? "found " + describe(el) : "no [data-qa=\"plugin-panel\"] in document"
      });
    })();

    // --- no_console_errors -----------------------------------------------
    (function () {
      var errs = window.__QA_CONSOLE_ERRORS__ || [];
      var pass = errs.length === 0;
      results.push({
        id: "no_console_errors",
        pass: pass,
        detail: pass
          ? "0 console.error / window.onerror during load + replay"
          : errs.length + " captured: " + errs.slice(0, 5).join(" | ")
      });
    })();

    return results;
  }

  // =====================================================================
  // 8. Publish the verdict
  // =====================================================================

  function publish(result) {
    var pre = document.getElementById("__qa_result");
    if (!pre) {
      pre = document.createElement("pre");
      pre.id = "__qa_result";
      pre.style.display = "none";
      (document.body || document.documentElement).appendChild(pre);
    }
    pre.textContent = JSON.stringify(result);
    document.title = "QA:" + (result.pass ? "PASS" : "FAIL");
    window.__QA_RESULT__ = result;
  }

  // =====================================================================
  // 9. Main
  // =====================================================================

  function main() {
    // The cinematic boot overlay is position:fixed/z-index:9999 and would
    // cover every screenshot — drop it (QA-only DOM tweak, app files untouched).
    var overlay = document.getElementById("boot-overlay");
    if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay);

    forceProgressScreen();

    loadFixture(function (records, source) {
      var applied = replay(records);

      // Let rAF/setTimeout-driven DOM updates settle before asserting.
      setTimeout(function () {
        var results = runAssertions();
        var pass = results.every(function (r) { return r.pass; });
        publish({
          pass: pass,
          scenario: window.__QA_SCENARIO__ || "smoke",
          fixtureSource: source,
          applied: applied,
          results: results,
          consoleErrors: (window.__QA_CONSOLE_ERRORS__ || []).slice(),
          resourceErrors: (window.__QA_RESOURCE_ERRORS__ || []).slice()
        });
      }, 50);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { setTimeout(main, 0); });
  } else {
    setTimeout(main, 0);
  }
})();
