// Node built-in test runner: `node --test tests/js`
// busy.js is a plain browser script (no import/export) that attaches its
// helpers to the global object -- importing it here runs that side effect.
import { test } from "node:test";
import assert from "node:assert/strict";
import "../../app/web/busy.js";

const { RedlineBusy } = globalThis;

// Minimal DOM stub: busy.js only touches `disabled` and `classList`.
function makeEl() {
  const classes = new Set();
  return {
    disabled: false,
    classList: {
      add: (c) => classes.add(c),
      remove: (c) => classes.delete(c),
      contains: (c) => classes.has(c),
    },
  };
}

test("set toggles disabled and is-busy, returns the new state", () => {
  const el = makeEl();
  assert.equal(RedlineBusy.set(el, true), true);
  assert.equal(el.disabled, true);
  assert.equal(el.classList.contains("is-busy"), true);
  assert.equal(RedlineBusy.set(el, false), false);
  assert.equal(el.disabled, false);
  assert.equal(el.classList.contains("is-busy"), false);
});

test("isBusy reflects the is-busy class", () => {
  const el = makeEl();
  assert.equal(RedlineBusy.isBusy(el), false);
  RedlineBusy.set(el, true);
  assert.equal(RedlineBusy.isBusy(el), true);
});

test("wrap is single-flight: a second call while pending is ignored", async () => {
  const el = makeEl();
  let calls = 0;
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const guarded = RedlineBusy.wrap(el, async () => {
    calls++;
    await gate;
    return "done";
  });

  const first = guarded();
  const second = guarded();
  assert.equal(second, undefined, "second call must return undefined");
  assert.equal(calls, 1, "fn must be invoked exactly once");
  assert.equal(el.classList.contains("is-busy"), true, "busy while pending");

  release();
  assert.equal(await first, "done");
  assert.equal(calls, 1);
  assert.equal(el.classList.contains("is-busy"), false, "cleared after settle");
});

test("wrap clears is-busy even when fn throws", async () => {
  const el = makeEl();
  const guarded = RedlineBusy.wrap(el, async () => { throw new Error("boom"); });
  await assert.rejects(guarded(), /boom/);
  assert.equal(el.classList.contains("is-busy"), false);
  assert.equal(el.disabled, false);
});

test("wrap allows a new call after the previous one settled", async () => {
  const el = makeEl();
  let calls = 0;
  const guarded = RedlineBusy.wrap(el, async () => { calls++; return calls; });
  assert.equal(await guarded(), 1);
  assert.equal(await guarded(), 2);
  assert.equal(calls, 2);
});

test("run invokes the guarded call immediately and returns its promise", async () => {
  const el = makeEl();
  let calls = 0;
  const result = RedlineBusy.run(el, async () => { calls++; return "ok"; });
  assert.equal(calls, 1, "fn invoked synchronously up to the first await");
  assert.equal(el.classList.contains("is-busy"), true);
  assert.equal(await result, "ok");
  assert.equal(el.classList.contains("is-busy"), false);
});

test("run is single-flight across two direct calls", async () => {
  const el = makeEl();
  let calls = 0;
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const p1 = RedlineBusy.run(el, async () => { calls++; await gate; return 1; });
  const p2 = RedlineBusy.run(el, async () => { calls++; await gate; return 2; });
  assert.equal(p2, undefined);
  release();
  assert.equal(await p1, 1);
  assert.equal(calls, 1);
});

test("set tolerates an element without disabled", () => {
  const el = { classList: { add() {}, remove() {}, contains() { return false; } } };
  assert.equal(RedlineBusy.set(el, true), true);
  assert.equal(RedlineBusy.set(el, false), false);
});
