// Node built-in test runner: `node --test tests/js`
// app_util.js is a plain browser script (no import/export) that attaches its
// helpers to the global object -- importing it here runs that side effect.
import { test } from "node:test";
import assert from "node:assert/strict";
import "../../app/web/app_util.js";

const { cappedAppend } = globalThis;

// Minimal DOM stub: cappedAppend only touches appendChild, children,
// firstChild and removeChild.
function makeContainer() {
  const children = [];
  return {
    get children() { return children; },
    get firstChild() { return children.length ? children[0] : null; },
    appendChild(node) { children.push(node); return node; },
    removeChild(node) {
      const i = children.indexOf(node);
      if (i === -1) throw new Error("removeChild: node is not a child");
      children.splice(i, 1);
      return node;
    },
  };
}

function node(name) { return { name }; }

test("cappedAppend enforces the cap", () => {
  const c = makeContainer();
  for (let i = 0; i < 5; i++) cappedAppend(c, node(`n${i}`), 3);
  assert.equal(c.children.length, 3);
});

test("cappedAppend evicts oldest first", () => {
  const c = makeContainer();
  for (let i = 0; i < 5; i++) cappedAppend(c, node(`n${i}`), 3);
  assert.deepEqual(c.children.map((n) => n.name), ["n2", "n3", "n4"]);
});

test("cappedAppend calls onEvict once per eviction with the evicted node", () => {
  const c = makeContainer();
  const evicted = [];
  for (let i = 0; i < 5; i++) cappedAppend(c, node(`n${i}`), 3, (n) => evicted.push(n));
  assert.deepEqual(evicted.map((n) => n.name), ["n0", "n1"]);
});

test("cappedAppend does not call onEvict while under the cap", () => {
  const c = makeContainer();
  let calls = 0;
  cappedAppend(c, node("a"), 3, () => { calls++; });
  cappedAppend(c, node("b"), 3, () => { calls++; });
  assert.equal(calls, 0);
  assert.equal(c.children.length, 2);
});

test("cappedAppend returns the appended node", () => {
  const c = makeContainer();
  const n = node("x");
  assert.equal(cappedAppend(c, n, 3), n);
});

test("cappedAppend works without an onEvict callback", () => {
  const c = makeContainer();
  for (let i = 0; i < 4; i++) cappedAppend(c, node(`n${i}`), 2);
  assert.equal(c.children.length, 2);
});

test("cappedAppend with max 0 evicts the node it just appended", () => {
  const c = makeContainer();
  const evicted = [];
  cappedAppend(c, node("only"), 0, (n) => evicted.push(n));
  assert.equal(c.children.length, 0);
  assert.deepEqual(evicted.map((n) => n.name), ["only"]);
});
