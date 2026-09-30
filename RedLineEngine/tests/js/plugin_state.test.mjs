// Node built-in test runner: `node --test tests/js`
// plugin_state.js is a plain browser script (no import/export) that attaches
// its helpers to the global object -- importing it here runs that side effect.
import { test } from "node:test";
import assert from "node:assert/strict";
import "../../app/web/plugin_state.js";

const { RedlinePluginState } = globalThis;

test("processorViewModel builds title/subtitle/rows from real keys", () => {
  const vm = RedlinePluginState.processorViewModel({
    stem: "Vocal_Lead",
    processor: "distortion",
    params: { drive_db: 6.0, mix: 0.5 },
  });
  assert.equal(vm.live, true);
  assert.match(vm.title, /distortion/);
  assert.match(vm.subtitle, /Vocal_Lead/);
  assert.ok(Array.isArray(vm.rows));
  assert.ok(vm.rows.length >= 2);
  for (const row of vm.rows) {
    assert.equal(typeof row.label, "string");
    assert.equal(typeof row.value, "string");
  }
  const labels = vm.rows.map((r) => r.label);
  assert.ok(labels.includes("drive_db"));
  assert.ok(labels.includes("mix"));
});

test("processorViewModel tolerates missing keys without throwing", () => {
  const vm = RedlinePluginState.processorViewModel({});
  assert.equal(vm.live, true);
  assert.equal(typeof vm.title, "string");
  assert.equal(typeof vm.subtitle, "string");
  assert.deepEqual(vm.rows, []);
  assert.doesNotThrow(() => RedlinePluginState.processorViewModel());
  assert.doesNotThrow(() => RedlinePluginState.processorViewModel(null));
});

test("pluginViewModel maps parameters[].label and raw_value", () => {
  const vm = RedlinePluginState.pluginViewModel({
    name: "MyVST",
    parameters: [
      { name: "gain", label: "Gain", raw_value: 0.75 },
      { name: "mix", label: "Mix", raw_value: 1.0 },
    ],
  });
  assert.equal(vm.live, true);
  assert.match(vm.title, /MyVST/);
  assert.deepEqual(vm.rows, [
    { label: "Gain", value: "0.75" },
    { label: "Mix", value: "1" },
  ]);
});

test("pluginViewModel falls back to parameter name when label is missing", () => {
  const vm = RedlinePluginState.pluginViewModel({
    name: "P",
    parameters: [{ name: "cutoff", raw_value: 440 }],
  });
  assert.deepEqual(vm.rows, [{ label: "cutoff", value: "440" }]);
});

test("pluginViewModel tolerates missing keys without throwing", () => {
  const vm = RedlinePluginState.pluginViewModel({});
  assert.equal(vm.live, true);
  assert.equal(typeof vm.title, "string");
  assert.deepEqual(vm.rows, []);
  assert.doesNotThrow(() => RedlinePluginState.pluginViewModel());
  assert.doesNotThrow(() => RedlinePluginState.pluginViewModel(null));
  assert.doesNotThrow(() => RedlinePluginState.pluginViewModel({ parameters: "nope" }));
});

test("emptyState is the intentional no-plugin placeholder", () => {
  const vm = RedlinePluginState.emptyState();
  assert.equal(vm.title, "Nessun plugin");
  assert.equal(typeof vm.subtitle, "string");
  assert.ok(vm.subtitle.length > 0);
  assert.deepEqual(vm.rows, []);
  assert.equal(vm.live, false);
});
