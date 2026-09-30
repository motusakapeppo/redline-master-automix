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
 *        (or only the first window.__QA_UPTO__ records for phase shots)
 *     -> run the smoke assertions (full replay) or the phase assertion set
 *        (truncated replay)
 *     -> write {"pass":bool,"results":[...],"consoleErrors":[...]} into
 *        <pre id="__qa_result"> and set document.title = "QA:PASS|FAIL"
 *
 * Scenarios (window.__QA_SCENARIO__):
 *   smoke (default) — fixture replay + 7 assertions (ids unchanged).
 *   edge            — no replay; exercises double-submit single-flight,
 *                     cancel path, intentional empty states and slider
 *                     readouts (5 assertions).
 *
 * Phase shots (window.__QA_UPTO__ / window.__QA_PHASE__):
 *   A truncated replay (upto < fixture length) swaps the two assertions that
 *   need the full event stream (details_live_after_replay, plugin_panel) for
 *   phase_progress + phase_dom_state, so early/mid cuts still publish a
 *   meaningful 7-assertion verdict:
 *     early (upto=4)   — load+analyze steps only; no stem rows yet, plugin
 *                        panel still in its intentional empty state.
 *     mid   (upto=8)   — mix phase started; 'vocals' stem row exists, EQ +
 *                        compressor live, plugin panel still empty.
 *     done  (upto=all) — full replay, full smoke assertion set.
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
  // 1b. Bridge instrumentation — wrap the stub WITHOUT editing it.
  //
  // bridge_stub.js is loaded before this script (see __qa_boot.js), so
  // window.pywebview.api already exists here. We:
  //   - count every api method call in window.__QA_CALLS__ (per-method +
  //     total), so the edge scenario can assert single-flight behavior;
  //   - add a cancel_run stub when the bridge lacks one (the real bridge
  //     gained cancel_run in the same overhaul; the stub predates it), so
  //     the cancel path can be exercised end-to-end.
  // The wrapper is transparent: same return value, same `this`.
  // =====================================================================

  window.__QA_CALLS__ = { total: 0, byMethod: {} };

  function instrumentBridge() {
    var api = window.pywebview && window.pywebview.api;
    if (!api) return;

    if (typeof api.cancel_run !== "function") {
      api.cancel_run = function () { return Promise.resolve({ ok: true, cancelled: true }); };
    }

    Object.keys(api).forEach(function (name) {
      var orig = api[name];
      if (typeof orig !== "function") return;
      api[name] = function () {
        window.__QA_CALLS__.total++;
        window.__QA_CALLS__.byMethod[name] = (window.__QA_CALLS__.byMethod[name] || 0) + 1;
        return orig.apply(this, arguments);
      };
    });
  }

  instrumentBridge();

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
    // Live plugin/processor panel: a built-in character processor applied to
    // a stem, then an external plugin hosted at the seam -- both must render
    // real labels/values into [data-qa="plugin-panel"].
    { kind: "event", payload: { type: "character_processor", stem: "vocals", processor: "distortion", params: { drive_db: 6.0, tone: 0.4 } } },
    { kind: "event", payload: { type: "plugin_hosted", name: "QA Test Plugin", parameters: [{ name: "gain", label: "Gain", raw_value: "3.5 dB" }, { name: "mix", label: "Mix", raw_value: "100%" }] } },
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
  //
  //    `upto` (window.__QA_UPTO__) truncates the replay to the first N
  //    records for phase-progress screenshots; null/undefined = all.
  // =====================================================================

  function replay(records, upto) {
    var applied = { steps: 0, events: 0, skipped: 0, replayed: 0, total: records.length };
    var limit = (typeof upto === "number" && isFinite(upto) && upto >= 0)
      ? Math.min(upto, records.length)
      : records.length;

    for (var i = 0; i < limit; i++) {
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

    applied.replayed = limit;
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
  //
  //    Shared helpers push into a caller-owned results array so the smoke,
  //    phase and edge sets can reuse them without duplicating logic.
  // =====================================================================

  function assertRailExists(results) {
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
  }

  function assertModulesPresent(results) {
    var mods = qaAll(".module");
    var pass = mods.length === 9;
    results.push({
      id: "modules_present",
      pass: pass,
      detail: ".module count=" + mods.length + " (expected exactly 9)"
    });
  }

  function assertCancelControl(results) {
    var el = document.querySelector('[data-qa="cancel-run"]') || document.getElementById("btn-cancel");
    var pass = !!el;
    results.push({
      id: "cancel_control",
      pass: pass,
      detail: pass
        ? "found " + describe(el)
        : "no [data-qa=\"cancel-run\"] and no #btn-cancel in document"
    });
  }

  function assertSliderReadouts(results) {
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
  }

  function assertNoConsoleErrors(results) {
    var errs = window.__QA_CONSOLE_ERRORS__ || [];
    var pass = errs.length === 0;
    results.push({
      id: "no_console_errors",
      pass: pass,
      detail: pass
        ? "0 console.error / window.onerror during load + replay"
        : errs.length + " captured: " + errs.slice(0, 5).join(" | ")
    });
  }

  // --- smoke set: the original 7 assertions, ids unchanged ---------------

  function runSmokeAssertions() {
    var results = [];

    assertRailExists(results);
    assertModulesPresent(results);

    // --- details_live_after_replay ---------------------------------------
    (function () {
      var details = qaAll(".module-detail");
      // "Live" means: not the legacy idle string, not the new richer idle
      // label, and not empty -- i.e. a real value from the replayed events.
      var stale = details.filter(function (el) {
        var t = elText(el);
        return !t || t === "in attesa..." || /^in attesa di dati/i.test(t);
      });
      var pass = details.length > 0 && stale.length === 0;
      results.push({
        id: "details_live_after_replay",
        pass: pass,
        detail: pass
          ? details.length + " .module-detail, none stale"
          : stale.length + "/" + details.length + " still idle/empty: " +
            stale.map(function (el) { return "#" + (el.id || "?") + "=\"" + elText(el) + "\""; }).join(", ")
      });
    })();

    assertCancelControl(results);
    assertSliderReadouts(results);

    // --- plugin_panel ----------------------------------------------------
    (function () {
      var el = document.querySelector('[data-qa="plugin-panel"]');
      var body = document.getElementById("plugin-panel-body");
      var text = body ? String(body.textContent || "").trim() : "";
      // The panel must exist AND show live content after the replay (the
      // fixture fires character_processor + plugin_hosted): the empty state
      // text must be gone and the real plugin name must be visible.
      var live = !!el && text.length > 0 && text.indexOf("QA Test Plugin") !== -1;
      results.push({
        id: "plugin_panel",
        pass: !!el && live,
        detail: el
          ? (live
            ? "found " + describe(el) + ", live content: \"" + text.slice(0, 80) + "\""
            : "found " + describe(el) + " but no live content after replay (body=\"" + text.slice(0, 80) + "\")")
          : "no [data-qa=\"plugin-panel\"] in document"
      });
    })();

    assertNoConsoleErrors(results);
    return results;
  }

  // --- phase set: used when the replay was truncated (--upto/--phase) ----
  //     Same 7-assertion shape, but the two assertions that need the FULL
  //     event stream (details_live_after_replay, plugin_panel) are replaced
  //     by phase_progress + phase_dom_state, which verify the DOM is
  //     consistent with exactly the slice that was replayed.

  function runPhaseAssertions(applied, records) {
    var results = [];

    assertRailExists(results);
    assertModulesPresent(results);

    // --- phase_progress --------------------------------------------------
    (function () {
      var expected = (typeof window.__QA_UPTO__ === "number" && isFinite(window.__QA_UPTO__))
        ? window.__QA_UPTO__
        : applied.replayed;
      var fill = document.getElementById("progress-fill");
      var pct = fill ? parseInt(fill.getAttribute("aria-valuenow") || "0", 10) : 0;
      var pass = applied.replayed === expected && pct > 0;
      results.push({
        id: "phase_progress",
        pass: pass,
        detail: pass
          ? "replayed " + applied.replayed + "/" + applied.total + " records, progress bar at " + pct + "%"
          : "replayed " + applied.replayed + " (expected " + expected + "), progress bar at " + pct + "%"
      });
    })();

    // --- phase_dom_state -------------------------------------------------
    // Consistency check between the replayed slice and the DOM: whatever the
    // cut, the page must show exactly the state that slice implies.
    (function () {
      var slice = records.slice(0, applied.replayed);
      var problems = [];

      var stemMentioned = slice.some(function (r) {
        if (!r || typeof r !== "object") return false;
        if (r.kind === "event" && r.payload && typeof r.payload === "object" && r.payload.stem) return true;
        if (r.kind === "step" && /'[^']+'/.test(String(r.payload))) return true;
        return false;
      });
      var eqEvent = slice.some(function (r) {
        return r && r.kind === "event" && r.payload && r.payload.type === "bus_eq_band";
      });
      var compEvent = slice.some(function (r) {
        return r && r.kind === "event" && r.payload && r.payload.type === "compressor" && r.payload.stem;
      });
      var pluginEvent = slice.some(function (r) {
        return r && r.kind === "event" && r.payload &&
          (r.payload.type === "character_processor" || r.payload.type === "plugin_hosted");
      });
      var hasStep = slice.some(function (r) { return r && r.kind === "step"; });

      var stemRows = qaAll(".stem-row");
      var stemEmpty = document.getElementById("stem-rows-empty");
      if (stemMentioned && stemRows.length === 0) problems.push("slice mentions a stem but no .stem-row exists");
      if (!stemMentioned && !stemEmpty) problems.push("no stem in slice but #stem-rows-empty is gone");

      function isIdle(id) {
        var el = document.getElementById(id);
        var t = elText(el);
        return !t || t === "in attesa..." || /^in attesa di dati/i.test(t);
      }
      if (eqEvent && isIdle("eq-detail")) problems.push("bus_eq_band replayed but #eq-detail still idle");
      if (compEvent && isIdle("comp-detail")) problems.push("compressor replayed but #comp-detail still idle");

      var pluginEmpty = document.querySelector("#plugin-panel .plugin-panel-empty");
      if (pluginEvent && pluginEmpty) problems.push("plugin event replayed but .plugin-panel-empty still shown");
      if (!pluginEvent && !pluginEmpty) problems.push("no plugin event in slice but .plugin-panel-empty is gone");

      var advanced = qaAll(".pipeline-node.active, .pipeline-node.complete").length;
      if (hasStep && advanced === 0) problems.push("steps replayed but no .pipeline-node is active/complete");

      var pass = problems.length === 0;
      results.push({
        id: "phase_dom_state",
        pass: pass,
        detail: pass
          ? "DOM consistent with slice: " + stemRows.length + " .stem-row, rail advanced=" + advanced +
            ", plugin empty=" + !!pluginEmpty
          : problems.join("; ")
      });
    })();

    assertCancelControl(results);
    assertSliderReadouts(results);
    assertNoConsoleErrors(results);
    return results;
  }

  // --- edge set: recovery behaviors the smoke path doesn't exercise ------
  //     Order matters: the empty-state snapshot is taken FIRST because the
  //     interactions below intentionally replace the plugin panel and the
  //     log idle state.

  function runEdgeAssertions(done) {
    var results = [];
    var calls = window.__QA_CALLS__;

    // --- empty_states_present --------------------------------------------
    (function () {
      var pluginEmpty = document.querySelector("#plugin-panel .plugin-panel-empty");
      var stemEmpty = document.getElementById("stem-rows-empty");
      var logIdle = document.getElementById("log-idle");
      var missing = [];
      if (!pluginEmpty) missing.push("#plugin-panel .plugin-panel-empty");
      if (!stemEmpty) missing.push("#stem-rows-empty");
      if (!logIdle) missing.push("#log-idle");
      var pass = missing.length === 0;
      results.push({
        id: "empty_states_present",
        pass: pass,
        detail: pass
          ? "intentional empty states present: #plugin-panel .plugin-panel-empty, #stem-rows-empty, #log-idle"
          : "missing empty state(s): " + missing.join(", ")
      });
    })();

    // --- double_submit_single_flight -------------------------------------
    // Two rapid clicks on #processor-apply: RedlineBusy.run() must let the
    // first through and swallow the second, so the stub bridge sees exactly
    // ONE enable_processor_variants + ONE set_character_spec call.
    (function () {
      var sel = document.getElementById("processor-select");
      var btn = document.getElementById("processor-apply");
      if (!sel || !btn) {
        results.push({
          id: "double_submit_single_flight",
          pass: false,
          detail: "missing #processor-select or #processor-apply"
        });
        finishEdge();
        return;
      }

      // The select is populated asynchronously by loadBuiltinProcessors();
      // wait (bounded) until the stub's processors have landed.
      var tries = 0;
      (function waitForOptions() {
        if (sel.options.length > 1 || tries >= 40) {
          sel.value = "distortion";
          var beforeEnable = calls.byMethod.enable_processor_variants || 0;
          var beforeSpec = calls.byMethod.set_character_spec || 0;

          btn.click();
          var busySeen = btn.classList.contains("is-busy") || btn.disabled;
          btn.click(); // second rapid click while the first is still in flight

          setTimeout(function () {
            var enableCalls = (calls.byMethod.enable_processor_variants || 0) - beforeEnable;
            var specCalls = (calls.byMethod.set_character_spec || 0) - beforeSpec;
            var pass = enableCalls === 1 && specCalls === 1 && busySeen;
            results.push({
              id: "double_submit_single_flight",
              pass: pass,
              detail: pass
                ? "2 rapid clicks -> enable_processor_variants=" + enableCalls +
                  ", set_character_spec=" + specCalls + ", is-busy observed mid-flight=" + busySeen
                : "enable_processor_variants=" + enableCalls + " (want 1), set_character_spec=" +
                  specCalls + " (want 1), is-busy observed=" + busySeen
            });
            runCancelCheck();
          }, 60);
          return;
        }
        tries++;
        setTimeout(waitForOptions, 25);
      })();
    })();

    // --- cancel_path ------------------------------------------------------
    function runCancelCheck() {
      var btn = document.getElementById("btn-cancel");
      if (!btn) {
        results.push({ id: "cancel_path", pass: false, detail: "no #btn-cancel in document" });
        runSliderCheck();
        return;
      }
      var before = calls.byMethod.cancel_run || 0;
      btn.click();
      var disabledNow = !!btn.disabled;
      var busyNow = !!(window.RedlineBusy && window.RedlineBusy.isBusy(btn));
      setTimeout(function () {
        var cancelCalls = (calls.byMethod.cancel_run || 0) - before;
        var pass = cancelCalls === 1 && (disabledNow || busyNow);
        results.push({
          id: "cancel_path",
          pass: pass,
          detail: pass
            ? "cancel_run called " + cancelCalls + "x, button busy/disabled after click (disabled=" +
              disabledNow + ", is-busy=" + busyNow + ")"
            : "cancel_run calls=" + cancelCalls + " (want 1), disabled=" + disabledNow + ", is-busy=" + busyNow
        });
        runSliderCheck();
      }, 60);
    }

    // --- slider_readout_update -------------------------------------------
    function runSliderCheck() {
      var slider = document.getElementById("warmth");
      var val = document.getElementById("warmth-val");
      var before = val ? String(val.textContent) : null;
      var pass = false;
      var after = before;
      if (slider && val) {
        slider.value = "0.7";
        slider.dispatchEvent(new Event("input", { bubbles: true }));
        after = String(val.textContent);
        pass = before !== after && after === "0.7";
      }
      results.push({
        id: "slider_readout_update",
        pass: pass,
        detail: pass
          ? "#warmth set to 0.7 + input event -> #warmth-val \"" + before + "\" -> \"" + after + "\""
          : "slider=" + !!slider + ", readout=" + !!val + ", before=\"" + before + "\", after=\"" + after + "\""
      });
      assertNoConsoleErrors(results);
      finishEdge();
    }

    function finishEdge() {
      done(results);
    }
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

    var scenario = window.__QA_SCENARIO__ || "smoke";

    function publishResults(results, extra) {
      var pass = results.every(function (r) { return r.pass; });
      var payload = {
        pass: pass,
        scenario: scenario,
        results: results,
        consoleErrors: (window.__QA_CONSOLE_ERRORS__ || []).slice(),
        resourceErrors: (window.__QA_RESOURCE_ERRORS__ || []).slice()
      };
      if (extra) {
        for (var k in extra) {
          if (Object.prototype.hasOwnProperty.call(extra, k)) payload[k] = extra[k];
        }
      }
      publish(payload);
    }

    if (scenario === "edge") {
      // No fixture replay: the edge suite drives the real UI directly.
      setTimeout(function () {
        runEdgeAssertions(function (results) {
          publishResults(results, {
            fixtureSource: "(none — edge scenario)",
            applied: { steps: 0, events: 0, skipped: 0, replayed: 0, total: 0 }
          });
        });
      }, 50);
      return;
    }

    loadFixture(function (records, source) {
      var upto = (typeof window.__QA_UPTO__ === "number" && isFinite(window.__QA_UPTO__))
        ? window.__QA_UPTO__
        : null;
      var applied = replay(records, upto);
      var truncated = applied.replayed < records.length;

      // Let rAF/setTimeout-driven DOM updates settle before asserting.
      setTimeout(function () {
        var results = truncated
          ? runPhaseAssertions(applied, records)
          : runSmokeAssertions();
        publishResults(results, {
          fixtureSource: source,
          applied: applied,
          phase: truncated ? (window.__QA_PHASE__ || ("upto-" + applied.replayed)) : "full"
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
