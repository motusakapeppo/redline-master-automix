/**
 * rack_state.js — pure state model for the 9 rack modules.
 *
 * Loaded as a plain (non-module) script before app.js in index.html, so it
 * must not use import/export and must not depend on anything else on the
 * page. Exposes its helpers on the global object.
 *
 * The module is intentionally DOM-free: `describe`/`reduce` turn backend
 * event dicts into the text each `.module-detail` should show, and app.js
 * is responsible for writing that text into the DOM.
 */
(function (global) {
  "use strict";

  const IDLE_TEXT = "in attesa...";

  // Canonical rack order, matching the .module blocks in index.html.
  const MODULES = [
    { id: "eq", label: "EQ", detailId: "#eq-detail" },
    { id: "comp", label: "Compressore", detailId: "#comp-detail" },
    { id: "deess", label: "De-esser", detailId: "#deess-detail" },
    { id: "vu", label: "VU", detailId: "#vu-detail" },
    { id: "qc", label: "Ascolto / QC", detailId: "#qc-detail" },
    { id: "reverb", label: "Riverbero / Spazio", detailId: "#reverb-detail" },
    { id: "sat", label: "Saturazione", detailId: "#saturation-detail" },
    { id: "master", label: "Master", detailId: "#master-detail" },
    { id: "midside", label: "Mid/Side", detailId: "#midside-detail" },
  ];

  // --- small formatting helpers (all tolerant of missing keys) ------------

  function num(v, digits) {
    return typeof v === "number" && isFinite(v) ? v.toFixed(digits) : null;
  }

  function signed(v, digits) {
    const s = num(v, digits);
    return s === null ? null : (v > 0 ? "+" : "") + s;
  }

  function live(moduleId, text) {
    return { moduleId: moduleId, live: true, text: text };
  }

  // --- per-event text builders --------------------------------------------

  function eqText(evt) {
    const bits = [];
    const f = num(evt.freq_hz, 0);
    if (f !== null) bits.push(f + "Hz");
    const g = signed(evt.gain_db, 1);
    if (g !== null) bits.push(g + "dB");
    return bits.length ? "Bus: " + bits.join(" ") : "bus EQ aggiornato";
  }

  function compText(evt) {
    const bits = [];
    const ratio = num(evt.ratio, 1);
    if (ratio !== null) bits.push("ratio " + ratio + ":1");
    const thr = num(evt.threshold_db, 1);
    if (thr !== null) bits.push("thr " + thr + " dB");
    return bits.length ? bits.join(", ") : "compressione attiva";
  }

  function deessText(evt) {
    const lo = num(evt.low_hz, 0);
    const hi = num(evt.high_hz, 0);
    if (lo !== null && hi !== null) return "banda " + lo + "-" + hi + "Hz";
    if (lo !== null) return "banda da " + lo + "Hz";
    if (hi !== null) return "banda fino a " + hi + "Hz";
    return "de-esser attivo";
  }

  function satText(evt) {
    const drive = num(evt.drive, 2);
    if (drive !== null) return "drive " + drive;
    return "saturazione attiva";
  }

  function reverbSendText(evt) {
    const bits = [];
    if (evt.bus) bits.push(String(evt.bus));
    const mix = num(evt.mix, 3);
    if (mix !== null) bits.push(Math.round(evt.mix * 100) + "%");
    return bits.length ? bits.join(" ") : "riverbero attivo";
  }

  function reverbBusText(evt) {
    if (Array.isArray(evt.buses) && evt.buses.length) {
      return "bus: " + evt.buses.join(", ");
    }
    return "bus riverbero renderizzati";
  }

  function midSideText(evt) {
    const bits = [];
    const mono = num(evt.mono_below_hz, 0);
    if (mono !== null) bits.push("mono < " + mono + "Hz");
    const air = num(evt.air_gain_db, 1);
    if (air !== null) bits.push("air " + signed(evt.air_gain_db, 1) + "dB");
    return bits.length ? bits.join(", ") : "mid/side attivo";
  }

  function musicBusMsText(evt) {
    const dip = num(evt.mid_dip_db, 1);
    if (dip !== null) return "buco " + dip + "dB";
    return "bus musicale M/S";
  }

  function limiterText(evt) {
    const ceiling = num(evt.ceiling_db, 1);
    if (ceiling !== null) return "ceiling " + ceiling + "dB";
    return "limiter attivo";
  }

  function loudnessText(evt) {
    const cur = num(evt.current_lufs, 1);
    const target = num(evt.target_lufs, 1);
    const gain = signed(evt.gain_db, 1);
    if (cur !== null && target !== null) {
      return cur + " -> " + target + " LUFS" + (gain !== null ? " (" + gain + "dB)" : "");
    }
    if (target !== null) return "target " + target + " LUFS";
    return "loudness aggiornato";
  }

  function softClipText(evt) {
    const ceiling = num(evt.ceiling_db, 1);
    if (ceiling !== null) return "soft clip " + ceiling + "dB";
    return "soft clip attivo";
  }

  function qcText(evt) {
    const bits = [];
    const lufs = num(evt.lufs, 1);
    if (lufs !== null) bits.push(lufs + " LUFS");
    const peak = num(evt.true_peak_db, 1);
    if (peak !== null) bits.push("peak " + peak + "dB");
    const mono = num(evt.mono_compatibility, 2);
    if (mono !== null) bits.push("mono " + mono);
    const verdict = evt.passed === true ? "OK" : evt.passed === false ? "corretto" : null;
    if (verdict) bits.push(verdict);
    return bits.length ? bits.join(", ") : "QC completato";
  }

  function vuText(evt) {
    const lufs = num(evt.lufs, 1);
    if (lufs !== null) return lufs + " LUFS";
    return "VU aggiornato";
  }

  // --- public API ----------------------------------------------------------

  /**
   * Maps ONE backend event dict to the rack module it should light up.
   * Returns `{moduleId, live: true, text}` or `null` when the event does
   * not belong to any rack module. Never throws on missing keys.
   */
  function describe(evt) {
    if (!evt || typeof evt !== "object") return null;
    switch (evt.type) {
      case "bus_eq_band": return live("eq", eqText(evt));
      case "compressor":
      case "bus_compressor": return live("comp", compText(evt));
      case "deesser": return live("deess", deessText(evt));
      case "saturation": return live("sat", satText(evt));
      case "reverb_send": return live("reverb", reverbSendText(evt));
      case "reverb_bus_render": return live("reverb", reverbBusText(evt));
      case "mid_side": return live("midside", midSideText(evt));
      case "music_bus_ms": return live("midside", musicBusMsText(evt));
      case "limiter": return live("master", limiterText(evt));
      case "loudness_gain": return live("master", loudnessText(evt));
      case "soft_clip": return live("master", softClipText(evt));
      case "qc_report": return live("qc", qcText(evt));
      case "vu":
      case "vu_meter": return live("vu", vuText(evt));
      case "done": return live("vu", "render completato");
      default: return null;
    }
  }

  /** Fresh state: all 9 modules idle. */
  function initialState() {
    return MODULES.map(function (m) {
      return { id: m.id, label: m.label, detailId: m.detailId, text: IDLE_TEXT, live: false };
    });
  }

  /**
   * Immutable reducer: returns a NEW state array. When `evt` maps to a
   * module, that entry is replaced with the described text and `live:true`;
   * unknown events leave the contents unchanged (still a new array).
   */
  function reduce(state, evt) {
    const base = Array.isArray(state) ? state : initialState();
    const d = describe(evt);
    if (!d) return base.slice();
    return base.map(function (m) {
      if (m.id !== d.moduleId) return m;
      return { id: m.id, label: m.label, detailId: m.detailId, text: d.text, live: true };
    });
  }

  /** Same as `initialState()` — convenience for the reset button. */
  function resetAll() {
    return initialState();
  }

  global.RedlineRack = {
    MODULES: MODULES,
    IDLE_TEXT: IDLE_TEXT,
    describe: describe,
    initialState: initialState,
    reduce: reduce,
    resetAll: resetAll,
  };
})(typeof window !== "undefined" ? window : globalThis);
