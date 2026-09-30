# RedLine Engine GUI QA harness

Operator guide for the zero-dependency browser harness that tests the RedLine
frontend. It runs the real UI in headless Edge, replays a recorded event stream
through the app's own callbacks, and asserts DOM invariants in-page.

## 1. What this proves, and what it doesn't

The harness loads the actual frontend (`app/web/index.html`, `app.js`,
`style.css`) in headless Edge, injects an offline stub of the pywebview bridge,
and drives the real `onStep()` / `onEvent()` globals with a deterministic
fixture. It then checks seven DOM invariants and fails if any of them break.

What it proves:

- The real frontend boots and renders without throwing.
- The pipeline rail, the nine modules, the slider readouts, the cancel control,
  and the plugin panel all exist in the live DOM.
- Replaying a real engine event stream lights up every module detail (no module
  is left idle).
- Zero `console.error` and zero uncaught `window.onerror` during load and replay.

What it is not:

- Not a visual pixel-diff. It captures a screenshot for humans, but no assertion
  compares pixels.
- Not the full pywebview runtime. The Python bridge is replaced by
  `scripts/qa/bridge_stub.js`, so it can't catch a bug that only shows up in the
  real webview host.
- Not the engine gate. That's `ci_check.py` (see the note at the end).

## 2. Prerequisites

- Node >= 22. The harness uses the global `WebSocket` and `node --test`. Verified
  on Node v25.8.1.
- Microsoft Edge installed at the standard path:
  `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`. Override with
  the `REDLINE_QA_EDGE` environment variable if yours lives elsewhere.
- No npm install, no network, no Playwright, no Python needed to run the GUI
  harness. The fixture generator and its guard test do need the repo's Python
  venv.

## 3. Commands

Run the smoke scenario:

```
node scripts/qa/run.js --scenario smoke
```

Useful flags (all parsed by `scripts/qa/run.js`):

| Flag | Default | Meaning |
| --- | --- | --- |
| `--scenario=<name>` | `smoke` | Scenario to run. Only `smoke` is implemented. |
| `--engine=<name>` | `edge` | Browser engine. Only `edge` is supported. |
| `--fixture=<path>` | built-in inline fixture | `.jsonl` (one `{"kind","payload"}` per line) or `.json` (array of the same records). |
| `--shots=<dir>` | `docs/screenshots` | Directory the screenshot is copied into. |
| `--budget=<ms>` | `15000` | Chromium `--virtual-time-budget`. |
| `--timeout=<ms>` | `120000` | Hard wall-clock timeout for the Edge process. |
| `--keep-temp` | off | Keep the temp web root (printed) for debugging. |

Examples:

```
node scripts/qa/run.js --scenario smoke --shots=docs/screenshots
node scripts/qa/run.js --scenario smoke --fixture=tests/fixtures/events_full.jsonl
node scripts/qa/run.js --scenario smoke --engine=edge --budget=15000 --keep-temp
```

Pure-module unit tests (no browser, no Python):

```
node --test tests/js
```

`tests/js/index.js` is a compatibility shim so that exact directory form works
on Node 21+; glob invocations and bare `node --test` discovery are unaffected.

## 4. The seven assertions

The runner lives in `scripts/qa/inpage.js` (`runAssertions()`). The
machine-readable manifest is `scripts/qa/assertions.json`.

| id | What it checks | How it fails |
| --- | --- | --- |
| `rail_exists` | `#screen-progress` exists and at least one `.pipeline-node` is rendered. | Screen missing or zero pipeline nodes. |
| `modules_present` | Exactly nine `.module` elements are in the DOM. | Count is anything other than 9. |
| `details_live_after_replay` | Every `.module-detail` shows a real value after replay. | A detail is empty, `in attesa...`, or matches `/^in attesa di dati/i`. |
| `cancel_control` | `[data-qa="cancel-run"]` or `#btn-cancel` is reachable. | Neither selector matches. |
| `slider_readouts` | All five sliders (`warmth`, `vocal_prominence`, `stereo_width`, `transient_attack`, `transient_sustain`) have a `#<id>-val` readout inside the same `.field`. | A slider, its readout, or the sibling relationship is missing. |
| `plugin_panel` | `[data-qa="plugin-panel"]` exists and `#plugin-panel-body` shows live content containing `QA Test Plugin`. | Panel missing, body empty, or plugin name not rendered. |
| `no_console_errors` | `window.__QA_CONSOLE_ERRORS__` is empty. | Any `console.error` or uncaught `window.onerror` was captured. |

## 5. The fixture

`tests/fixtures/events_full.jsonl` is generated, not hand-written. The generator
is `scripts/qa/gen_fixtures.py`:

```
.venv\Scripts\python.exe scripts/qa/gen_fixtures.py
```

It runs a real `render_mix` + `render_master` with the `on_step` / `on_event`
callbacks tapped, then writes every narration string and structured event as one
JSON object per line. Generating instead of hand-writing keeps the fixture in
sync with the engine: the frontend's `onEvent` switch is a contract with the
engine, and a hand-written fixture would drift the moment the engine changes.

Why it's deterministic:

- The synthetic stems come from `tests/test_neutral_golden.py` with a fixed seed
  (`np.random.default_rng(7)`), plus a few extra deterministic stems.
- Records are canonically sorted by `(kind, payload)` because the engine emits
  some events from a thread pool, so wall-clock order varies run to run.
- Output uses `\n` newlines and `sort_keys=True`, and any absolute path is
  scrubbed to `<PATH>`, so the same bytes come out on every platform.
- `.gitattributes` forces `*.jsonl text eol=lf` so git's autocrlf can't rewrite
  the file to CRLF on checkout and break the byte comparison.

The guard test is `tests/test_fixture_gen.py`. It checks the fixture parses line
by line, covers the required event types, and regenerates it in a temp dir and
compares bytes against the committed file. If the engine's event stream changes,
that test fails and tells you to regenerate.

## 6. Interpreting output

Exit code `0` means PASS, `1` means FAIL (or a harness error). The screenshot is
copied to `<shots>/<scenario>.png`, so the default run writes
`docs/screenshots/smoke.png`.

The last line of the run is the verdict:

```
VERDICT  : PASS (7/7 assertions)
```

A real run looks like this:

```
=== RedLine QA harness ===
scenario : smoke
engine   : edge
fixture  : (built-in inline fixture)
temp web : C:\Users\motus\AppData\Local\Temp\redline-qa-24396
screenshot: D:\FASE REM_automix\RedLineEngine\docs\screenshots\smoke.png

fixture source: builtin (steps=6, events=11, skipped=0)

  [PASS] rail_exists — #screen-progress present, 6 .pipeline-node
  [PASS] modules_present — .module count=9 (expected exactly 9)
  [PASS] details_live_after_replay — 9 .module-detail, none stale
  [PASS] cancel_control — found button#btn-cancel.btn.btn-cancel
  [PASS] slider_readouts — 5/5 sliders have a #<id>-val sibling readout
  [PASS] plugin_panel — found div#plugin-panel.plugin-panel.live.pulse, live content: "Plugin: QA Test Plugin
    2 parametri
    Gain3.5 dBMix100%"
  [PASS] no_console_errors — 0 console.error / window.onerror during load + replay

VERDICT  : PASS (7/7 assertions)
```

When a run fails, the summary lists the failed assertions with their detail
strings, and any captured console errors are printed under `console errors`.

Unknown event types are harmless. The replay loop in `inpage.js` only acts on
`kind === "step"` and `kind === "event"`; anything else, or any record the
current build can't parse, hits the `default:` / catch branch and is counted as
`skipped` instead of breaking the run. That's why a fixture generated by a newer
engine still replays cleanly against an older frontend.

## 7. Adding a new assertion

1. Add the check to `runAssertions()` in `scripts/qa/inpage.js`. Push one result
   object with `{ id, pass, detail }`, following the existing blocks.
2. Add a matching entry to `scripts/qa/assertions.json` so the manifest stays in
   sync with the runner.
3. Re-run `node scripts/qa/run.js --scenario smoke` and confirm the new id shows
   up in the output and the verdict still passes.

## Note on `ci_check.py`

`ci_check.py` is the engine quality gate (Python version, dependencies, pytest,
gain staging, Neural Monitor). It is not the GUI gate, and this harness does not
replace it. It also has a known crash on Windows: it prints non-ASCII status
text that can raise a `cp1252` encoding error when stdout isn't UTF-8. Don't
treat it as the GUI check.
