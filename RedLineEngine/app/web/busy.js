/**
 * busy.js — single-flight + busy-state helpers for async GUI actions.
 *
 * Loaded as a plain (non-module) script before app.js in index.html, so it
 * must not use import/export and must not depend on anything else on the
 * page. Exposes its helpers on the global object.
 *
 * Only DOM surface used: `el.disabled` (when present) and `el.classList`
 * (add/remove/contains). No other DOM APIs, so a minimal stub is enough.
 */
(function (global) {
  "use strict";

  // Per-element pending flag: a second guarded call on the same element
  // while the first is still awaiting is ignored (double-click protection).
  // WeakMap so elements can be garbage-collected normally.
  const pending = new WeakMap();

  /**
   * Toggles the busy state of `el`: `disabled` (if the element has it) and
   * the `is-busy` class. Returns the new state as a boolean.
   *
   * @param {object|null} el - element-like object (may be null).
   * @param {boolean} on - desired busy state.
   * @returns {boolean} the new state.
   */
  function set(el, on) {
    const state = !!on;
    if (el) {
      if ("disabled" in el) el.disabled = state;
      if (el.classList) {
        if (state) el.classList.add("is-busy");
        else el.classList.remove("is-busy");
      }
    }
    return state;
  }

  /**
   * True if `el` currently carries the `is-busy` class.
   *
   * @param {object|null} el - element-like object (may be null).
   * @returns {boolean}
   */
  function isBusy(el) {
    return !!(el && el.classList && el.classList.contains("is-busy"));
  }

  /**
   * Wraps `fn` in a guarded async call bound to `el`.
   *
   * While a call is pending, further calls are single-flight: they are
   * ignored, return `undefined` and do NOT invoke `fn`. The wrapper sets
   * `is-busy` for the duration of the awaited `fn()` and always clears it
   * in `finally`, even when `fn` throws.
   *
   * @param {object|null} el - element whose busy state is toggled.
   * @param {Function} fn - async work to run.
   * @returns {Function} guarded async function.
   */
  function wrap(el, fn) {
    // NOTE: deliberately NOT an async function -- an async function always
    // returns a Promise, so the single-flight branch could not return a
    // literal `undefined` as the contract requires.
    return function guarded() {
      if (el && pending.get(el)) return undefined;
      if (el) pending.set(el, true);
      set(el, true);
      let result;
      try {
        result = fn.apply(this, arguments);
      } catch (err) {
        if (el) pending.delete(el);
        set(el, false);
        return Promise.reject(err);
      }
      return Promise.resolve(result).finally(function () {
        if (el) pending.delete(el);
        set(el, false);
      });
    };
  }

  /**
   * Sugar for a one-shot guarded call: `run(el, fn)` invokes the guarded
   * async call immediately and returns its promise (or `undefined` when a
   * call on the same element is already pending).
   *
   * @param {object|null} el - element whose busy state is toggled.
   * @param {Function} fn - async work to run.
   * @returns {Promise|undefined}
   */
  function run(el, fn) {
    return wrap(el, fn)();
  }

  global.RedlineBusy = { set: set, isBusy: isBusy, wrap: wrap, run: run };
})(typeof window !== "undefined" ? window : globalThis);
