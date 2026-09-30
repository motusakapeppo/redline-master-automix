#!/usr/bin/env node
/**
 * scripts/qa/run.js — zero-dependency browser QA harness for the RedLine GUI.
 *
 * Loads the REAL frontend (app/web/index.html + app.js + style.css) in
 * headless Edge, injects an offline stub of the pywebview bridge, replays a
 * recorded event/step fixture through the app's own onStep()/onEvent()
 * globals, runs DOM assertions IN-PAGE, and captures a screenshot plus a
 * machine-readable verdict. No npm, no network, no Playwright, no Python.
 *
 * Usage:
 *   node scripts/qa/run.js --scenario smoke
 *   node scripts/qa/run.js --scenario smoke --fixture=tests/fixtures/events_full.jsonl
 *   node scripts/qa/run.js --scenario smoke --shots=docs/screenshots
 *   node scripts/qa/run.js --scenario smoke --engine=edge --budget=15000 --keep-temp
 *   node scripts/qa/run.js --scenario smoke --phase=early   # 10_overhaul_early.png
 *   node scripts/qa/run.js --scenario smoke --phase=mid     # 11_overhaul_mid.png
 *   node scripts/qa/run.js --scenario smoke --phase=done    # 12_overhaul_done.png
 *   node scripts/qa/run.js --scenario edge                  # edge/recovery suite
 *
 * Options:
 *   --scenario=<name>   Scenario to run: "smoke" (fixture replay + 7 assertions)
 *                       or "edge" (double-submit / cancel / empty states /
 *                       slider readouts + console-error check, 5 assertions;
 *                       behavioral, so it needs no fixture file). Default: smoke.
 *   --engine=<name>     Browser engine; only "edge" is supported. Default: edge.
 *   --fixture=<path>    Fixture file: .jsonl (one {"kind","payload"} per line,
 *                       as written by scripts/qa/gen_fixtures.py) or .json
 *                       (array of the same records). Omit to use the tiny
 *                       built-in inline fixture inside scripts/qa/inpage.js.
 *   --upto=<n>          Replay only the FIRST n fixture records before
 *                       asserting/screenshotting (phase-progress shots).
 *                       Optional; default = all records (existing behavior).
 *                       The in-page runner switches to a phase-specific
 *                       assertion set when n < the full fixture length, so a
 *                       truncated replay still publishes a PASS/FAIL verdict.
 *   --phase=<name>      Convenience alias for the three overhaul progress
 *                       shots; sets --upto and the output filename:
 *                         early -> --upto=4  -> docs/screenshots/10_overhaul_early.png
 *                         mid   -> --upto=8  -> docs/screenshots/11_overhaul_mid.png
 *                         done  -> --upto=all-> docs/screenshots/12_overhaul_done.png
 *                       (explicit --upto wins over the phase's default cut).
 *                       What each phase replays (built-in fixture, 17 records):
 *                         early: records 0-3 — load+analyze steps only; no
 *                                stem rows yet, plugin panel still empty.
 *                         mid:   records 0-7 — mix phase started; 'vocals'
 *                                stem row exists, EQ + compressor live.
 *                         done:  all 17 — full replay, full smoke set.
 *   --shots=<dir>       Directory to copy the screenshot into. Default: docs/screenshots.
 *   --budget=<ms>       Chromium --virtual-time-budget. Default: 15000.
 *   --timeout=<ms>      Hard wall-clock timeout for the Edge process. Default: 120000.
 *   --keep-temp         Keep the temp web root (printed) for debugging.
 *
 * Exit code: 0 = PASS, 1 = FAIL (or harness error).
 *
 * How it works:
 *   1. Copies app/web -> %TEMP%/redline-qa-<pid> (skipping the gitignored,
 *      regenerated _preview/ WAVs). Production files are never touched.
 *   2. Writes __qa_boot.js into the temp web root and injects a single
 *      <script src="__qa_boot.js"></script> at the TOP of <head> in the
 *      COPIED index.html. The boot loader document.writes bridge_stub.js
 *      then inpage.js, so the error capture in inpage.js is installed
 *      before app_util.js/app.js ever run.
 *   3. Serves the temp dir from an in-process static server (MIME map
 *      mirrored from scripts/static-server.js).
 *   4. Launches Edge headless with --dump-dom + --screenshot and parses the
 *      <pre id="__qa_result"> JSON out of the dumped DOM.
 */

"use strict";

const http = require("http");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn } = require("child_process");

const REPO_ROOT = path.resolve(__dirname, "..", "..");
const WEB_SRC = path.join(REPO_ROOT, "app", "web");
const EDGE_DEFAULT = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";

// MIME map mirrored from scripts/static-server.js (plus a couple of extras
// the QA harness itself needs: .jsonl/.map/.wasm are harmless to add).
const MIME = {
  ".html": "text/html",
  ".js": "application/javascript",
  ".css": "text/css",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".glb": "model/gltf-binary",
  ".gltf": "model/gltf+json",
  ".bin": "application/octet-stream",
  ".json": "application/json",
  ".jsonl": "application/x-ndjson",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".wav": "audio/wav",
  ".mp3": "audio/mpeg",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
  ".map": "application/json",
  ".wasm": "application/wasm",
};

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

function parseArgs(argv) {
  const opts = {
    scenario: "smoke",
    engine: "edge",
    fixture: null,
    upto: null, // null = replay every fixture record (existing behavior)
    phase: null,
    shots: path.join(REPO_ROOT, "docs", "screenshots"),
    budget: 15000,
    timeout: 120000,
    keepTemp: false,
  };
  const args = argv.slice(2);
  for (let i = 0; i < args.length; i++) {
    const m = /^--([^=]+)(?:=(.*))?$/.exec(args[i]);
    if (!m) continue;
    const key = m[1];
    let value = m[2];
    // Support both "--key=value" and "--key value" (the latter only when the
    // next token is not itself a flag).
    if (value === undefined && i + 1 < args.length && !/^--/.test(args[i + 1])) {
      value = args[++i];
    }
    switch (key) {
      case "scenario": opts.scenario = value || "smoke"; break;
      case "engine": opts.engine = value || "edge"; break;
      case "fixture": opts.fixture = value ? path.resolve(process.cwd(), value) : null; break;
      case "upto": opts.upto = value ? parseInt(value, 10) : null; break;
      case "phase": opts.phase = value || null; break;
      case "shots": opts.shots = path.resolve(process.cwd(), value || "docs/screenshots"); break;
      case "budget": opts.budget = parseInt(value, 10) || 15000; break;
      case "timeout": opts.timeout = parseInt(value, 10) || 120000; break;
      case "keep-temp": opts.keepTemp = true; break;
      default: break; // unknown flags ignored
    }
  }
  return opts;
}

// Phase-progress shots: each phase is a cut point into the fixture plus a
// distinct output filename. "done" replays everything (upto = null).
const PHASES = {
  early: { upto: 4, shot: "10_overhaul_early.png" },
  mid: { upto: 8, shot: "11_overhaul_mid.png" },
  done: { upto: null, shot: "12_overhaul_done.png" },
};

// Resolves --phase/--upto into { upto, shotName }. An explicit --upto always
// wins over the phase's default cut; without either, the shot keeps the
// historical "<scenario>.png" name and the full replay. A bare --upto (no
// --phase) gets "<scenario>_upto<n>.png" so it can never clobber smoke.png.
function resolvePhase(opts) {
  const phase = opts.phase ? PHASES[opts.phase] : null;
  if (opts.phase && !phase) {
    throw new Error(`Unknown phase "${opts.phase}" (expected early|mid|done)`);
  }
  const explicitUpto = (opts.upto !== null && !isNaN(opts.upto)) ? opts.upto : null;
  const upto = explicitUpto !== null ? explicitUpto : (phase ? phase.upto : null);
  let shotName;
  if (phase) shotName = phase.shot;
  else if (explicitUpto !== null) shotName = `${opts.scenario}_upto${explicitUpto}.png`;
  else shotName = `${opts.scenario}.png`;
  return { upto, shotName };
}

// ---------------------------------------------------------------------------
// Fixture loading
// ---------------------------------------------------------------------------

function loadFixtureRecords(fixturePath) {
  const raw = fs.readFileSync(fixturePath, "utf8");
  const ext = path.extname(fixturePath).toLowerCase();
  let records;

  if (ext === ".jsonl" || ext === ".ndjson") {
    records = raw
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => JSON.parse(line));
  } else {
    const parsed = JSON.parse(raw);
    records = Array.isArray(parsed) ? parsed : (parsed && parsed.records) || [];
  }

  if (!Array.isArray(records) || records.length === 0) {
    throw new Error(`Fixture ${fixturePath} contains no records`);
  }
  return records;
}

// ---------------------------------------------------------------------------
// Temp web root
// ---------------------------------------------------------------------------

function copyWebTree(src, dest) {
  fs.cpSync(src, dest, {
    recursive: true,
    filter: (source) => {
      // _preview/ is gitignored, regenerated per render, and ~87 MB of WAVs
      // the harness never needs (the bridge stub serves canned URLs).
      const rel = path.relative(src, source);
      if (rel === "_preview" || rel.startsWith("_preview" + path.sep)) return false;
      return true;
    },
  });
}

function copyHarnessScripts(webRoot) {
  // bridge_stub.js / inpage.js live next to this orchestrator, not in
  // app/web — copy them into the temp web root so the injected
  // <script src="..."> tags resolve over the static server.
  for (const name of ["bridge_stub.js", "inpage.js"]) {
    fs.copyFileSync(path.join(__dirname, name), path.join(webRoot, name));
  }
}

function writeBootLoader(webRoot, scenario, upto, phaseName) {
  // document.write during parsing is synchronous and blocking, so both
  // scripts are guaranteed to execute before app_util.js/app.js (which sit
  // at the bottom of <body>).
  const boot = [
    "/* __qa_boot.js — generated by scripts/qa/run.js. Do not edit. */",
    "(function () {",
    "  window.__QA_SCENARIO__ = " + JSON.stringify(scenario) + ";",
    "  window.__QA_UPTO__ = " + (upto === null || upto === undefined ? "null" : String(upto)) + ";",
    "  window.__QA_PHASE__ = " + JSON.stringify(phaseName || null) + ";",
    "  document.write('<script src=\"bridge_stub.js\"><\\/script>');",
    "  document.write('<script src=\"inpage.js\"><\\/script>');",
    "})();",
    "",
  ].join("\n");
  fs.writeFileSync(path.join(webRoot, "__qa_boot.js"), boot, "utf8");
}

function injectBootScript(webRoot) {
  const indexPath = path.join(webRoot, "index.html");
  let html = fs.readFileSync(indexPath, "utf8");
  if (html.includes("__qa_boot.js")) return; // already injected
  if (!html.includes("<head>")) throw new Error("index.html has no <head> to inject into");
  html = html.replace("<head>", '<head>\n<script src="__qa_boot.js"></script>');
  fs.writeFileSync(indexPath, html, "utf8");
}

// ---------------------------------------------------------------------------
// Static server (in-process; MIME logic mirrored from scripts/static-server.js)
// ---------------------------------------------------------------------------

function startStaticServer(root) {
  return new Promise((resolve, reject) => {
    const server = http.createServer((req, res) => {
      let urlPath = decodeURIComponent(req.url.split("?")[0]);
      if (urlPath === "/") urlPath = "/index.html";
      const filePath = path.join(root, urlPath);
      if (!filePath.startsWith(root)) {
        res.writeHead(403);
        res.end("Forbidden");
        return;
      }
      fs.stat(filePath, (err, stat) => {
        if (err || !stat.isFile()) {
          res.writeHead(404);
          res.end("Not found");
          return;
        }
        const ext = path.extname(filePath).toLowerCase();
        res.writeHead(200, {
          "Content-Type": MIME[ext] || "application/octet-stream",
          "Content-Length": stat.size,
          "Cache-Control": "no-store",
        });
        const stream = fs.createReadStream(filePath);
        stream.on("error", () => { try { res.destroy(); } catch (e) { /* ignore */ } });
        stream.pipe(res);
      });
    });
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      resolve({ server, port: server.address().port });
    });
  });
}

// ---------------------------------------------------------------------------
// Edge headless
// ---------------------------------------------------------------------------

function runEdge(edgePath, url, opts, tempDir) {
  return new Promise((resolve, reject) => {
    const shotPath = path.join(tempDir, "shot.png");
    const profileDir = path.join(tempDir, "edge-profile");
    const args = [
      "--headless=new",
      "--disable-gpu",
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-extensions",
      "--disable-background-networking",
      "--disable-sync",
      "--mute-audio",
      "--hide-scrollbars",
      "--window-size=880,680",
      "--user-data-dir=" + profileDir,
      "--virtual-time-budget=" + opts.budget,
      "--run-all-compositor-stages-before-draw",
      "--screenshot=" + shotPath,
      "--dump-dom",
      url,
    ];

    const child = spawn(edgePath, args, { stdio: ["ignore", "pipe", "pipe"], windowsHide: true });
    const stdout = [];
    const stderr = [];
    let settled = false;

    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      try { child.kill(); } catch (e) { /* ignore */ }
      reject(new Error(`Edge timed out after ${opts.timeout}ms`));
    }, opts.timeout);

    child.stdout.on("data", (chunk) => stdout.push(chunk));
    child.stderr.on("data", (chunk) => stderr.push(chunk));
    child.on("error", (err) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      reject(err);
    });
    child.on("close", (code) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve({
        code,
        dom: Buffer.concat(stdout).toString("utf8"),
        stderr: Buffer.concat(stderr).toString("utf8"),
        shotPath,
      });
    });
  });
}

// ---------------------------------------------------------------------------
// Verdict parsing
// ---------------------------------------------------------------------------

function unescapeHtml(s) {
  return s
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&");
}

function parseVerdict(dom) {
  const titleMatch = /<title>([^<]*)<\/title>/i.exec(dom);
  const title = titleMatch ? titleMatch[1].trim() : "";

  const preMatch = /<pre[^>]*id="__qa_result"[^>]*>([\s\S]*?)<\/pre>/i.exec(dom);
  if (preMatch) {
    try {
      return { verdict: JSON.parse(unescapeHtml(preMatch[1])), title, raw: preMatch[1] };
    } catch (e) {
      return { verdict: null, title, raw: preMatch[1], parseError: String(e) };
    }
  }
  return { verdict: null, title, raw: null, parseError: "no <pre id=\"__qa_result\"> in dumped DOM" };
}

// ---------------------------------------------------------------------------
// Reporting
// ---------------------------------------------------------------------------

function printSummary(opts, parsed, shotDest, tempDir, phase) {
  const v = parsed.verdict;
  console.log("");
  console.log("=== RedLine QA harness ===");
  console.log(`scenario : ${opts.scenario}`);
  console.log(`engine   : ${opts.engine}`);
  console.log(`fixture  : ${opts.fixture || "(built-in inline fixture)"}`);
  if (phase && phase.upto !== null) {
    console.log(`phase    : ${opts.phase || "upto"} (replay first ${phase.upto} records)`);
  } else if (opts.phase) {
    console.log(`phase    : ${opts.phase} (full replay)`);
  }
  console.log(`temp web : ${tempDir}`);
  console.log(`screenshot: ${shotDest}`);
  console.log("");

  if (!v) {
    console.log(`VERDICT  : FAIL (could not parse in-page result)`);
    console.log(`title    : ${parsed.title || "(none)"}`);
    console.log(`reason   : ${parsed.parseError || "unknown"}`);
    if (parsed.raw) console.log(`raw      : ${String(parsed.raw).slice(0, 500)}`);
    return false;
  }

  console.log(`fixture source: ${v.fixtureSource} (steps=${v.applied.steps}, events=${v.applied.events}, skipped=${v.applied.skipped})`);
  console.log("");
  for (const r of v.results) {
    console.log(`  [${r.pass ? "PASS" : "FAIL"}] ${r.id} — ${r.detail}`);
  }
  console.log("");

  const failed = v.results.filter((r) => !r.pass);
  if (failed.length) {
    console.log(`FAILED ASSERTIONS (${failed.length}/${v.results.length}):`);
    for (const r of failed) {
      console.log(`  - ${r.id}: ${r.detail}`);
    }
    console.log("");
  }

  if (v.consoleErrors && v.consoleErrors.length) {
    console.log(`console errors (${v.consoleErrors.length}):`);
    for (const e of v.consoleErrors.slice(0, 10)) console.log(`  ! ${e}`);
    console.log("");
  }

  console.log(`VERDICT  : ${v.pass ? "PASS" : "FAIL"} (${v.results.filter((r) => r.pass).length}/${v.results.length} assertions)`);
  return !!v.pass;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  const opts = parseArgs(process.argv);

  if (opts.scenario !== "smoke" && opts.scenario !== "edge") {
    console.error(`Unknown scenario "${opts.scenario}" (implemented: "smoke", "edge").`);
    process.exit(1);
  }
  if (opts.engine !== "edge") {
    console.error(`Unknown engine "${opts.engine}" (only "edge" is supported).`);
    process.exit(1);
  }

  let phase;
  try {
    phase = resolvePhase(opts);
  } catch (err) {
    console.error(String(err && err.message ? err.message : err));
    process.exit(1);
  }

  const edgePath = process.env.REDLINE_QA_EDGE || EDGE_DEFAULT;
  if (!fs.existsSync(edgePath)) {
    console.error(`Edge not found at ${edgePath} (override with REDLINE_QA_EDGE).`);
    process.exit(1);
  }
  if (!fs.existsSync(path.join(WEB_SRC, "index.html"))) {
    console.error(`Frontend not found at ${WEB_SRC}`);
    process.exit(1);
  }

  const tempDir = path.join(os.tmpdir(), `redline-qa-${process.pid}`);
  fs.rmSync(tempDir, { recursive: true, force: true });
  fs.mkdirSync(tempDir, { recursive: true });

  let server = null;
  let exitCode = 1;

  try {
    // 1. Copy the real frontend (production files untouched).
    copyWebTree(WEB_SRC, tempDir);

    // 2. Inject the QA boot loader at the top of <head>.
    copyHarnessScripts(tempDir);
    writeBootLoader(tempDir, opts.scenario, phase.upto, opts.phase);
    injectBootScript(tempDir);

    // 3. Optional fixture -> __qa_fixture.json in the temp web root.
    if (opts.fixture) {
      const records = loadFixtureRecords(opts.fixture);
      fs.writeFileSync(path.join(tempDir, "__qa_fixture.json"), JSON.stringify(records), "utf8");
      console.log(`Fixture: ${records.length} records from ${opts.fixture}`);
    }

    // 4. Serve + launch.
    const started = await startStaticServer(tempDir);
    server = started.server;
    const url = `http://127.0.0.1:${started.port}/index.html`;
    console.log(`Serving ${tempDir} at ${url}`);

    const run = await runEdge(edgePath, url, opts, tempDir);

    // 5. Screenshot -> shots dir.
    fs.mkdirSync(opts.shots, { recursive: true });
    const shotDest = path.join(opts.shots, phase.shotName);
    if (fs.existsSync(run.shotPath)) {
      fs.copyFileSync(run.shotPath, shotDest);
    } else {
      console.log("WARNING: Edge did not write a screenshot");
    }

    // 6. Parse + report.
    const parsed = parseVerdict(run.dom);
    const pass = printSummary(opts, parsed, shotDest, tempDir, phase);
    exitCode = pass ? 0 : 1;

    if (!parsed.verdict && run.stderr) {
      console.log("--- edge stderr (tail) ---");
      console.log(run.stderr.split(/\r?\n/).slice(-15).join("\n"));
    }
  } catch (err) {
    console.error("Harness error:", err && err.stack ? err.stack : err);
    exitCode = 1;
  } finally {
    if (server) {
      await new Promise((resolve) => server.close(resolve));
    }
    if (opts.keepTemp) {
      console.log(`Temp web root kept at ${tempDir}`);
    } else {
      try { fs.rmSync(tempDir, { recursive: true, force: true }); } catch (e) { /* ignore */ }
    }
  }

  process.exit(exitCode);
}

main();
