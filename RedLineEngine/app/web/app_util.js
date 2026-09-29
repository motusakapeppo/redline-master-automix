/**
 * app_util.js — small, pure, DOM-light helpers shared by app.js.
 *
 * Loaded as a plain (non-module) script before app.js in index.html, so it
 * must not use import/export and must not depend on anything else on the
 * page. Exposes its helpers on the global object.
 */
(function (global) {
  "use strict";

  /**
   * Appends `node` to `container` while enforcing a maximum child count.
   * Oldest children are evicted first (FIFO). `onEvict(evictedNode)` is
   * called exactly once per evicted node, so callers can release per-node
   * resources (event listeners, timers, ...) that would otherwise leak for
   * the life of the session.
   *
   * @param {Element} container - parent to append to.
   * @param {Node} node - node to append.
   * @param {number} max - maximum number of children to keep (clamped to >= 0).
   * @param {(evicted: Node) => void} [onEvict] - called once per eviction.
   * @returns {Node} the appended node.
   */
  function cappedAppend(container, node, max, onEvict) {
    if (!container || !node) return node;
    container.appendChild(node);
    const limit = Math.max(0, max | 0);
    while (container.children.length > limit) {
      const evicted = container.firstChild;
      container.removeChild(evicted);
      if (typeof onEvict === "function") onEvict(evicted);
    }
    return node;
  }

  global.cappedAppend = cappedAppend;
})(typeof window !== "undefined" ? window : globalThis);
