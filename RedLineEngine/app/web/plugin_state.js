/**
 * plugin_state.js — pure view-model builders for the plugin/processor panel.
 *
 * Loaded as a plain (non-module) script before app.js in index.html, so it
 * must not use import/export and must not depend on anything else on the
 * page. Exposes its helpers on the global object.
 *
 * Every builder is defensive: missing keys, wrong types or a null payload
 * degrade to a usable view model instead of throwing, so a malformed event
 * can never blank the panel.
 */
(function (global) {
  "use strict";

  function str(v) {
    return v === null || v === undefined ? "" : String(v);
  }

  function row(label, value) {
    return { label: str(label), value: str(value) };
  }

  /**
   * View model for a built-in processor applied to one stem.
   * `{stem, processor, params}` -> `{title, subtitle, rows, live:true}`.
   */
  function processorViewModel(payload) {
    const p = payload && typeof payload === "object" ? payload : {};
    const processor = str(p.processor) || "processore";
    const stem = str(p.stem);

    const rows = [];
    const params = p.params;
    if (params && typeof params === "object") {
      for (const key of Object.keys(params)) {
        rows.push(row(key, params[key]));
      }
    }

    return {
      title: "Processore: " + processor,
      subtitle: stem ? "Traccia: " + stem : "Nessuna traccia selezionata",
      rows: rows,
      live: true,
    };
  }

  /**
   * View model for an external plugin description
   * (`{name, parameters:[{label, raw_value}]}` from redline/plugins.py).
   */
  function pluginViewModel(payload) {
    const p = payload && typeof payload === "object" ? payload : {};
    const name = str(p.name) || "plugin";

    const rows = [];
    if (Array.isArray(p.parameters)) {
      for (const param of p.parameters) {
        if (!param || typeof param !== "object") continue;
        const label = str(param.label) || str(param.name);
        rows.push(row(label, param.raw_value));
      }
    }

    return {
      title: "Plugin: " + name,
      subtitle: rows.length + (rows.length === 1 ? " parametro" : " parametri"),
      rows: rows,
      live: true,
    };
  }

  /** Intentional empty state — never a blank hole in the panel. */
  function emptyState() {
    return {
      title: "Nessun plugin",
      subtitle: "In attesa di un processore o plugin...",
      rows: [],
      live: false,
    };
  }

  global.RedlinePluginState = {
    processorViewModel: processorViewModel,
    pluginViewModel: pluginViewModel,
    emptyState: emptyState,
  };
})(typeof window !== "undefined" ? window : globalThis);
