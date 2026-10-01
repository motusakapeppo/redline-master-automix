// Node built-in test runner: `node --test tests/js`
//
// three-avatar.js is an ES module with bare-specifier imports ("three",
// "three/addons/...") that Node cannot resolve, so it cannot be imported
// directly here. Instead the pure sizing helper is extracted from the source
// between explicit marker comments and evaluated in isolation -- the same
// function the browser runs, with zero DOM/WebGL dependencies.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC = readFileSync(
  path.join(__dirname, "..", "..", "app", "web", "three-avatar.js"),
  "utf8"
);

function extractComputeAvatarSize() {
  const m = /\/\/ __AVATAR_SIZING_HELPER_START__([\s\S]*?)\/\/ __AVATAR_SIZING_HELPER_END__/.exec(SRC);
  assert.ok(
    m,
    "three-avatar.js must contain the __AVATAR_SIZING_HELPER_START__/__AVATAR_SIZING_HELPER_END__ marker block"
  );
  // eslint-disable-next-line no-new-func
  const factory = new Function(`${m[1]}\nreturn computeAvatarSize;`);
  return factory();
}

test("computeAvatarSize returns the real dimensions and aspect for normal sizes", () => {
  const computeAvatarSize = extractComputeAvatarSize();
  const size = computeAvatarSize(190, 240);
  assert.equal(size.width, 190);
  assert.equal(size.height, 240);
  assert.equal(size.aspect, 190 / 240);
});

test("computeAvatarSize guards a zero width (never divides by zero)", () => {
  const computeAvatarSize = extractComputeAvatarSize();
  const size = computeAvatarSize(0, 240);
  assert.equal(size.width, 1);
  assert.equal(size.height, 240);
  assert.equal(size.aspect, 1 / 240);
  assert.ok(Number.isFinite(size.aspect));
});

test("computeAvatarSize guards a zero height", () => {
  const computeAvatarSize = extractComputeAvatarSize();
  const size = computeAvatarSize(190, 0);
  assert.equal(size.width, 190);
  assert.equal(size.height, 1);
  assert.equal(size.aspect, 190);
});

test("computeAvatarSize falls back to 1x1 when both dimensions are zero", () => {
  const computeAvatarSize = extractComputeAvatarSize();
  const size = computeAvatarSize(0, 0);
  assert.deepEqual(size, { width: 1, height: 1, aspect: 1 });
});

test("computeAvatarSize guards negative dimensions", () => {
  const computeAvatarSize = extractComputeAvatarSize();
  const size = computeAvatarSize(-50, -10);
  assert.deepEqual(size, { width: 1, height: 1, aspect: 1 });
});

test("computeAvatarSize guards NaN / undefined / non-numeric input", () => {
  const computeAvatarSize = extractComputeAvatarSize();
  assert.deepEqual(computeAvatarSize(NaN, 240), { width: 1, height: 240, aspect: 1 / 240 });
  assert.deepEqual(computeAvatarSize(undefined, undefined), { width: 1, height: 1, aspect: 1 });
  assert.deepEqual(computeAvatarSize("abc", "def"), { width: 1, height: 1, aspect: 1 });
});

test("computeAvatarSize coerces numeric strings", () => {
  const computeAvatarSize = extractComputeAvatarSize();
  const size = computeAvatarSize("300", "150");
  assert.equal(size.width, 300);
  assert.equal(size.height, 150);
  assert.equal(size.aspect, 2);
});

test("three-avatar.js wires window resize + ResizeObserver to the sizing path", () => {
  // The bug this guards: resize() existed but was never called, so the 3D
  // canvas never followed window/panel resizes. The wiring must exist in the
  // source even though it cannot be executed in Node.
  assert.match(SRC, /window\.addEventListener\(\s*['"]resize['"]/, "window resize listener missing");
  assert.match(SRC, /new ResizeObserver\(/, "ResizeObserver missing");
  assert.match(SRC, /_syncCanvasSize\(\)/, "post-init _syncCanvasSize() call missing");
});
