// Node built-in test runner: `node --test tests/js`
// rack_state.js is a plain browser script (no import/export) that attaches
// its helpers to the global object -- importing it here runs that side effect.
import { test } from "node:test";
import assert from "node:assert/strict";
import "../../app/web/rack_state.js";

const { RedlineRack } = globalThis;

const CANONICAL = [
  ["eq", "#eq-detail"],
  ["comp", "#comp-detail"],
  ["deess", "#deess-detail"],
  ["vu", "#vu-detail"],
  ["qc", "#qc-detail"],
  ["reverb", "#reverb-detail"],
  ["sat", "#saturation-detail"],
  ["master", "#master-detail"],
  ["midside", "#midside-detail"],
];

test("MODULES lists the 9 canonical modules in order with detail ids", () => {
  assert.equal(RedlineRack.MODULES.length, 9);
  assert.deepEqual(
    RedlineRack.MODULES.map((m) => [m.id, m.detailId]),
    CANONICAL
  );
  for (const m of RedlineRack.MODULES) {
    assert.equal(typeof m.label, "string");
    assert.ok(m.label.length > 0);
  }
});

test("IDLE_TEXT is the Italian placeholder", () => {
  assert.equal(RedlineRack.IDLE_TEXT, "in attesa...");
});

test("initialState returns 9 idle modules", () => {
  const state = RedlineRack.initialState();
  assert.equal(state.length, 9);
  for (const m of state) {
    assert.equal(m.text, RedlineRack.IDLE_TEXT);
    assert.equal(m.live, false);
    assert.equal(typeof m.detailId, "string");
  }
  assert.deepEqual(state.map((m) => m.id), CANONICAL.map(([id]) => id));
});

test("describe maps bus_eq_band to eq with a human text", () => {
  const d = RedlineRack.describe({ type: "bus_eq_band", freq_hz: 250, gain_db: -2.5 });
  assert.equal(d.moduleId, "eq");
  assert.equal(d.live, true);
  assert.match(d.text, /250/);
  assert.match(d.text, /-2\.5/);
});

test("describe maps compressor and bus_compressor to comp", () => {
  const a = RedlineRack.describe({ type: "compressor", ratio: 4.0, threshold_db: -18.0 });
  assert.equal(a.moduleId, "comp");
  assert.match(a.text, /4\.0:1/);
  assert.match(a.text, /-18/);
  const b = RedlineRack.describe({ type: "bus_compressor", ratio: 2.0, threshold_db: -12.0 });
  assert.equal(b.moduleId, "comp");
});

test("describe maps deesser, saturation, reverb, midside, master, qc", () => {
  assert.equal(RedlineRack.describe({ type: "deesser", low_hz: 5000, high_hz: 9000 }).moduleId, "deess");
  assert.equal(RedlineRack.describe({ type: "saturation", drive: 0.4 }).moduleId, "sat");
  assert.equal(RedlineRack.describe({ type: "reverb_send", bus: "hall", mix: 0.3 }).moduleId, "reverb");
  assert.equal(RedlineRack.describe({ type: "reverb_bus_render", buses: ["hall"] }).moduleId, "reverb");
  assert.equal(RedlineRack.describe({ type: "mid_side", mono_below_hz: 120 }).moduleId, "midside");
  assert.equal(RedlineRack.describe({ type: "music_bus_ms", mid_dip_db: -2 }).moduleId, "midside");
  assert.equal(RedlineRack.describe({ type: "limiter", ceiling_db: -1 }).moduleId, "master");
  assert.equal(RedlineRack.describe({ type: "loudness_gain", current_lufs: -14, target_lufs: -9, gain_db: 5 }).moduleId, "master");
  assert.equal(RedlineRack.describe({ type: "soft_clip", ceiling_db: -0.5 }).moduleId, "master");
  assert.equal(RedlineRack.describe({ type: "qc_report", lufs: -9.5, true_peak_db: -1.0, mono_compatibility: 0.9, passed: true }).moduleId, "qc");
});

test("describe maps vu-ish and done events to vu", () => {
  assert.equal(RedlineRack.describe({ type: "vu", lufs: -12 }).moduleId, "vu");
  assert.equal(RedlineRack.describe({ type: "vu_meter", lufs: -12 }).moduleId, "vu");
  assert.equal(RedlineRack.describe({ type: "done", stage: "mix" }).moduleId, "vu");
});

test("describe returns null for unknown or malformed events", () => {
  assert.equal(RedlineRack.describe({ type: "llm_token", text: "x" }), null);
  assert.equal(RedlineRack.describe({ type: "stem_instrument", stem: "vox" }), null);
  assert.equal(RedlineRack.describe({}), null);
  assert.equal(RedlineRack.describe(null), null);
  assert.equal(RedlineRack.describe(undefined), null);
});

test("describe tolerates missing keys without throwing", () => {
  const d = RedlineRack.describe({ type: "compressor" });
  assert.equal(d.moduleId, "comp");
  assert.equal(typeof d.text, "string");
  assert.ok(d.text.length > 0);
});

test("reduce returns a NEW array with the matching module replaced", () => {
  const before = RedlineRack.initialState();
  const after = RedlineRack.reduce(before, { type: "compressor", ratio: 4.0, threshold_db: -18.0 });
  assert.notEqual(after, before, "must be a new array");
  assert.equal(before[1].live, false, "input state must not be mutated");
  assert.equal(after[1].id, "comp");
  assert.equal(after[1].live, true);
  assert.match(after[1].text, /4\.0:1/);
  assert.equal(after[0].text, RedlineRack.IDLE_TEXT, "other modules untouched");
});

test("reduce leaves state unchanged for unknown events", () => {
  const before = RedlineRack.initialState();
  const after = RedlineRack.reduce(before, { type: "llm_token", text: "x" });
  assert.notEqual(after, before, "still a new array (immutable contract)");
  assert.deepEqual(after, before);
});

test("reduce does not mutate the input array or its entries", () => {
  const before = RedlineRack.initialState();
  const snapshot = JSON.parse(JSON.stringify(before));
  RedlineRack.reduce(before, { type: "limiter", ceiling_db: -1 });
  assert.deepEqual(before, snapshot);
});

test("resetAll equals initialState", () => {
  assert.deepEqual(RedlineRack.resetAll(), RedlineRack.initialState());
});
