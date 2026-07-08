// --- Cinematic boot sequence: auto-dismisses after ~1.9s, or immediately on
// click/tap to skip -- the real app underneath (avatar init, preset load)
// keeps loading normally the whole time, this never gates real readiness.
(function bootSequence() {
  const overlay = document.getElementById("boot-overlay");
  if (!overlay) return;
  let dismissed = false;
  function dismiss() {
    if (dismissed) return;
    dismissed = true;
    overlay.classList.add("boot-hidden");
    setTimeout(() => overlay.remove(), 700);
  }
  overlay.addEventListener("click", dismiss);
  setTimeout(dismiss, 1900);
})();

let selectedInput = null;
let selectedOutput = null;

// --- Progress % + ETA: on_step carries no step-count/total (it's a plain
// narration string), so this is a fuzzy estimate, not exact tracking --
// stems announced up front seed an expected step count (empirically ~8
// onStep calls per stem through the mix chain), and if the real count runs
// past that guess the estimate grows instead of the bar stalling at 100%.
let _progressSeen = 0;
let _progressExpected = 40;
let _progressStepTimes = [];
const _PROGRESS_HISTORY = 10;
const _STEPS_PER_STEM_GUESS = 8;

const PROGRESS_MILESTONE_LINES = {
  25: ["Si comincia a sentire la forma del pezzo...", "Le prime tracce stanno prendendo colore..."],
  50: ["Siamo a metà, e suona già bene...", "Mix a buon punto, avanti così..."],
  75: ["Ci siamo quasi, rifiniture finali...", "Ultimi ritocchi prima del traguardo..."],
};
let _progressMilestonesFired = new Set();

function resetProgress() {
  _progressSeen = 0;
  _progressExpected = 40;
  _progressStepTimes = [];
  _progressMilestonesFired = new Set();
  document.getElementById("progress-wrap")?.classList.remove("hidden");
  document.getElementById("speech-bubble")?.classList.add("hidden");
  clearTimeout(_bubbleHideTimer);
  const fill = document.getElementById("progress-fill");
  const pct = document.getElementById("progress-pct");
  const eta = document.getElementById("progress-eta");
  if (fill) fill.style.width = "0%";
  if (pct) pct.textContent = "0%";
  if (eta) eta.textContent = "stima tempo rimanente: --";
}

function bumpProgress(msg) {
  // Neural Monitor toggle narration reuses the same onStep() channel as
  // real pipeline steps (see toggle_neural_monitor's _narrate call in
  // api.py) but isn't a pipeline step at all -- counting it made the bar
  // creep forward every time the switch was flipped, on or off, mid-render
  // or not.
  if (/^Neural Monitor:/.test(msg)) return;
  const now = performance.now();
  _progressStepTimes.push(now);
  if (_progressStepTimes.length > _PROGRESS_HISTORY) _progressStepTimes.shift();
  _progressSeen += 1;

  const stemCountMatch = msg.match(/Caricati (\d+) stem/);
  if (stemCountMatch) {
    _progressExpected = Math.max(20, parseInt(stemCountMatch[1], 10) * _STEPS_PER_STEM_GUESS);
  }
  if (_progressSeen > _progressExpected) {
    _progressExpected = Math.ceil(_progressSeen * 1.15);
  }

  const pctValue = Math.min(97, (_progressSeen / _progressExpected) * 100);
  const fill = document.getElementById("progress-fill");
  const pctEl = document.getElementById("progress-pct");
  if (fill) fill.style.width = `${pctValue.toFixed(0)}%`;
  if (pctEl) pctEl.textContent = `${pctValue.toFixed(0)}%`;

  // Flavor bubbles at progress milestones -- only once per milestone per
  // run, and only if no macro-phase bubble already claimed this exact tick
  // (simplifyMacroMessage's bubble takes priority in onStep; this fires
  // independently from the progress bar instead).
  for (const threshold of [25, 50, 75]) {
    if (pctValue >= threshold && !_progressMilestonesFired.has(threshold)) {
      _progressMilestonesFired.add(threshold);
      const lines = PROGRESS_MILESTONE_LINES[threshold];
      sayBubble(lines[Math.floor(Math.random() * lines.length)]);
    }
  }

  const etaEl = document.getElementById("progress-eta");
  if (etaEl && _progressStepTimes.length >= 2) {
    const span = _progressStepTimes[_progressStepTimes.length - 1] - _progressStepTimes[0];
    const avgPerStep = span / (_progressStepTimes.length - 1);
    const remaining = Math.max(0, _progressExpected - _progressSeen);
    const etaSeconds = Math.round((avgPerStep * remaining) / 1000);
    etaEl.textContent = etaSeconds > 0
      ? `stima tempo rimanente: ~${etaSeconds}s`
      : "stima tempo rimanente: quasi fatto";
  }
}

function startIdleBreathing() {
  if (window.avatarAPI) window.avatarAPI.setActivity(0.3);
}
startIdleBreathing();

function startBlinkCycle() {
  // Three.js handles blink animation
}
startBlinkCycle();

function startEyeSaccades() {
  // Three.js handles eye animation
}
startEyeSaccades();

function setBrowExpression(level) {
  // Three.js handles expressions
}

function expressSurprise() {
  // Three.js handles expressions
}

function expressConcentrate() {
  // Three.js handles expressions
}

function expressRelax() {
  // Three.js handles expressions
}

function expressFlinch(intensity) {
  // Three.js handles expressions
}

function animateMouth(openAmount) {
  // Three.js handles mouth animation
}

function startLipSync(text) {
  // Three.js handles lip sync
}

function randomLookAround() {
  // Three.js handles idle animation
}
randomLookAround();

// --- QC canvas "breathing" waveform: a proxy for "the machine is listening"
// — activity spikes on every real step/event and decays, driving the wave's
// amplitude, instead of a canned idle loop with no relation to what's happening.
let qcActivityLevel = 0;
let qcCanvasAnimationStarted = false;

function bumpActivity() {
  qcActivityLevel = 1.0;
  startQcCanvasLoop();
}

function startQcCanvasLoop() {
  if (qcCanvasAnimationStarted) return;
  qcCanvasAnimationStarted = true;
  const canvas = document.getElementById("qc-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  let phase = 0;

  function draw() {
    ctx.clearRect(0, 0, w, h);
    qcActivityLevel *= 0.94; // decay
    const amplitude = 2 + qcActivityLevel * (h / 2 - 3);
    ctx.beginPath();
    ctx.strokeStyle = "#ff003f";
    ctx.lineWidth = 1.5;
    for (let x = 0; x <= w; x += 2) {
      const y = h / 2 + Math.sin(x * 0.15 + phase) * amplitude * Math.sin(x * 0.02 + phase * 0.3);
      if (x === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
    phase += 0.15 + qcActivityLevel * 0.1;
    requestAnimationFrame(draw);
  }
  draw();
}

function showScreen(id) {
  const current = document.querySelector(".screen.active");
  const next = document.getElementById(id);
  if (current === next) return;

  if (typeof playWhoosh === "function") playWhoosh();

  if (typeof gsap === "undefined") {
    // GSAP failed to load (vendored file missing/corrupt) -- the screen
    // switch itself must never depend on it, only the transition's polish does.
    document.querySelectorAll(".screen").forEach((el) => el.classList.remove("active"));
    next.classList.add("active");
    return;
  }

  if (current) {
    gsap.to(current, {
      opacity: 0, x: -24, scale: 0.985, duration: 0.28, ease: "power2.in",
      onComplete: () => current.classList.remove("active"),
    });
  }
  next.classList.add("active");
  gsap.fromTo(
    next,
    { opacity: 0, x: 24, scale: 0.985 },
    { opacity: 1, x: 0, scale: 1, duration: 0.45, delay: current ? 0.16 : 0, ease: "power3.out" }
  );

  // Cascading settle of the new screen's direct children -- a premium
  // "assembling itself" read instead of the whole block appearing at once.
  // Deliberately animates only position (not opacity, already handled by
  // the container tween above) to avoid double-fading the same element.
  const children = Array.from(next.children);
  if (children.length) {
    gsap.fromTo(
      children,
      { y: 14 },
      { y: 0, duration: 0.45, ease: "power2.out", stagger: 0.04, delay: current ? 0.18 : 0.05 }
    );
  }
}

// Alias -- the HTML markup calls this name directly for clarity ("go to
// the next screen"), same cinematic transition either way.
function goToScreen(id) {
  showScreen(id);
}

async function chooseInput() {
  const path = await window.pywebview.api.pick_input_path();
  if (path) {
    selectedInput = path;
    document.getElementById("input-path").textContent = path;
    document.getElementById("btn-next").disabled = false;
  }
}

async function chooseFile() {
  const path = await window.pywebview.api.pick_input_file();
  if (path) {
    selectedInput = path;
    document.getElementById("input-path").textContent = path;
    document.getElementById("btn-next").disabled = false;
  }
}

async function startRun() {
  selectedOutput = await window.pywebview.api.pick_output_dir();
  if (!selectedOutput) return;

  showScreen("screen-progress");
  document.getElementById("log").innerHTML = "";
  document.getElementById("spinner").classList.remove("hidden");
  document.getElementById("result").classList.add("hidden");
  document.getElementById("result").innerHTML = "";
  eqBands = {};
  busEqBands = {};
  _rackDisplayStem = null;
  _rackPinned = false;
  redrawEq();
  resetProgress();
  setAssistantLabel("al lavoro...");

  const prefs = {
    creative_brief: document.getElementById("creative_brief").value,
    aggressiveness: parseInt(document.getElementById("aggressiveness").value, 10),
    warmth: parseFloat(document.getElementById("warmth").value),
    vocal_prominence: parseFloat(document.getElementById("vocal_prominence").value),
    stereo_width: parseFloat(document.getElementById("stereo_width").value),
    transient_attack: parseFloat(document.getElementById("transient_attack").value),
    transient_sustain: parseFloat(document.getElementById("transient_sustain").value),
    genre_override: document.getElementById("genre_override").value,
    do_mastering: document.getElementById("do_mastering").checked,
    platform: document.getElementById("platform").value,
    stop_after_mix: document.getElementById("workflow_mode").value === "stop_at_mix",
  };

  const result = await window.pywebview.api.run_pipeline(selectedInput, prefs, selectedOutput);
  onDone(result);
}

// --- Preset system: load/save named MixPreferences configurations
// via the Python PresetManager bridge.

let presetNames = [];

async function loadPresets() {
  if (!window.pywebview) return;
  try {
    presetNames = await window.pywebview.api.list_presets();
  } catch (e) {
    presetNames = [];
  }
  const sel = document.getElementById("preset-select");
  if (!sel) return;
  const current = sel.value;
  sel.innerHTML = '<option value="">-- Carica preset --</option>';
  for (const name of presetNames) {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    sel.appendChild(opt);
  }
  if (current && presetNames.includes(current)) sel.value = current;
}

async function onPresetSelect(name) {
  if (!name || !window.pywebview) return;
  const result = await window.pywebview.api.load_preset(name);
  if (!result || !result.ok) {
    addEventChip(`\u26A0\uFE0F Preset: ${result ? result.error : "errore sconosciuto"}`);
    return;
  }
  // Update all slider/input values
  const agg = document.getElementById("aggressiveness");
  const warm = document.getElementById("warmth");
  const vocal = document.getElementById("vocal_prominence");
  const sw = document.getElementById("stereo_width");
  const ta = document.getElementById("transient_attack");
  const ts = document.getElementById("transient_sustain");
  const genre = document.getElementById("genre_override");
  const master = document.getElementById("do_mastering");

  if (agg) { agg.value = result.aggressiveness; document.getElementById("aggressiveness-val").textContent = result.aggressiveness; }
  if (warm) warm.value = result.warmth;
  if (vocal) vocal.value = result.vocal_prominence;
  if (sw) sw.value = result.stereo_width || 0;
  if (ta) ta.value = result.transient_attack || 0;
  if (ts) ts.value = result.transient_sustain || 0;
  if (genre) genre.value = result.genre_override || "";
  if (master) master.checked = result.do_mastering;

  addEventChip(`\u{1F4CB} Preset caricato: ${name}`);
}

async function saveCurrentPreset() {
  const name = prompt("Nome del preset:");
  if (!name || !name.trim()) return;
  const prefs = {
    aggressiveness: parseInt(document.getElementById("aggressiveness").value, 10),
    warmth: parseFloat(document.getElementById("warmth").value),
    vocal_prominence: parseFloat(document.getElementById("vocal_prominence").value),
    stereo_width: parseFloat(document.getElementById("stereo_width").value),
    transient_attack: parseFloat(document.getElementById("transient_attack").value),
    transient_sustain: parseFloat(document.getElementById("transient_sustain").value),
    genre_override: document.getElementById("genre_override").value,
    do_mastering: document.getElementById("do_mastering").checked,
  };
  const result = await window.pywebview.api.save_preset(name.trim(), prefs);
  if (result && result.ok) {
    addEventChip(`\u{1F4BE} Preset salvato: ${name.trim()}`);
    await loadPresets();
  } else {
    addEventChip(`\u26A0\uFE0F Errore salvataggio preset: ${result ? result.error : "sconosciuto"}`);
  }
}

// --- Speech bubble: a plain-language, non-technical narration of macro
// phase changes only (never micro sub-steps -- those fire too often per
// second to read as anything but noise). Deliberately NOT a rewrite of the
// technical log itself -- that log's exact strings are the engine's own
// narration (on_step calls throughout redline/mixengine.py and
// masterengine.py) and rewriting them risks changing what tests/behavior
// depend on. This is a parallel, friendlier layer for non-expert users,
// built from pattern-matching the same messages.
let _bubbleHideTimer = null;

function sayBubble(text) {
  const bubble = document.getElementById("speech-bubble");
  const textEl = document.getElementById("speech-bubble-text");
  if (!bubble || !textEl) return;
  textEl.textContent = text;
  bubble.classList.remove("hidden", "showing");
  void bubble.offsetWidth; // restart the pop-in/fade-out animation
  bubble.classList.add("showing");
  clearTimeout(_bubbleHideTimer);
  _bubbleHideTimer = setTimeout(() => bubble.classList.add("hidden"), 4000);
}

// Only the handful of patterns covering genuine phase transitions get a
// bubble -- an unmatched macro line just doesn't produce one (silence is
// better than surfacing a half-translated technical string).
function simplifyMacroMessage(msg) {
  if (/^Carico l'audio/.test(msg)) return "Sto caricando il tuo brano...";
  if (/^Rilevati \d+ file/.test(msg)) return "Ho trovato i file audio, comincio ad analizzarli.";
  if (/^Caricati \d+ stem/.test(msg)) return "Tracce separate, si parte con l'analisi!";
  if (/^Analizzo bpm/.test(msg)) return "Sto capendo genere, ritmo e tonalità del brano...";
  const bpmMatch = msg.match(/^BPM ([\d.]+)\s.*Genere (.+?)\s{2,}/);
  if (bpmMatch) return `Ho capito: è un pezzo a ${Math.round(parseFloat(bpmMatch[1]))} BPM, genere ${bpmMatch[2]}.`;
  if (/^Avvio il mix/.test(msg)) return "Comincio a mixare le tracce...";
  const stemMatch = msg.match(/^Elaborazione stem '([^']+)'/);
  if (stemMatch) return `Ora sto lavorando su: ${stemMatch[1]}`;
  if (/^Interpreto la richiesta/.test(msg)) return "Sto capendo cosa mi hai chiesto...";
  if (/^Richiesta applicata/.test(msg)) return "Fatto, applico le modifiche che hai chiesto.";
  if (/^In attesa di conferma/.test(msg)) return "Aspetto la tua conferma per continuare...";
  if (/^Domande sugli strumenti/.test(msg)) return "Ho bisogno del tuo aiuto per riconoscere alcuni strumenti.";
  if (/^Mix salvato/.test(msg)) return "Mix pronto!";
  if (/^Avvio il mastering/.test(msg)) return "Passo al mastering finale...";
  if (/^Master salvato/.test(msg)) return "Master pronto!";
  if (/^Rielaborazione del mix/.test(msg)) return "Rifaccio il mix con le tue indicazioni...";
  if (/^Ricalibro in base al feedback/.test(msg)) return "Aggiusto il suono come mi hai chiesto...";
  if (/^Mix pronto\. In attesa di revisione/.test(msg)) return "Mix pronto, dai un ascolto quando vuoi!";
  if (/^Fatto\.?$/.test(msg) || /^Fatto \(solo mix\)/.test(msg)) return "Ho finito! Dai un ascolto ✨";
  if (/^Errore/.test(msg)) return "Qualcosa non ha funzionato, controlla il messaggio qui sotto.";
  return null;
}

function onStep(msg) {
  const log = document.getElementById("log");
  const line = document.createElement("div");
  // The engine's own narration convention already distinguishes macro
  // phases ("Elaborazione stem 'X'...", no leading spaces) from micro
  // sub-steps ("  'X': risonanza a 250Hz...", 2-space indented) -- reuse it
  // for visual hierarchy in the unified log instead of a separate panel.
  const isMacro = !msg.startsWith("  ");
  line.className = isMacro ? "log-line log-macro" : "log-line log-micro";
  line.textContent = msg;
  log.appendChild(line);
  log.scrollTop = log.scrollHeight;
  if (window.avatarAPI) window.avatarAPI.onStep(msg);
  bumpActivity();
  bumpProgress(msg);
  if (isMacro) {
    const bubbleText = simplifyMacroMessage(msg);
    if (bubbleText) sayBubble(bubbleText);
  }
  wireInteractiveLine(line, msg);

  // "Elaborazione stem 'X' (...)" / "  'X': ..." narration lines create or
  // re-select that stem's row immediately, so the row exists (and lights up)
  // even before its first tagged badge event arrives.
  const stemMatch = msg.match(/'([^']+)'/);
  if (stemMatch) touchStemRow(stemMatch[1]);
}

// Turns a log line into a "console" element: hovering a line that mentions a
// frequency flashes exactly that point on the EQ curve; clicking a line
// about saturation/distortion triggers a brief visual glitch on the rack.
function wireInteractiveLine(line, msg) {
  const hzMatch = msg.match(/([\d.]+)\s*k?Hz/i);
  if (hzMatch) {
    const isKilo = /kHz/i.test(hzMatch[0]);
    const freq = parseFloat(hzMatch[1]) * (isKilo ? 1000 : 1);
    line.style.cursor = "pointer";
    line.addEventListener("mouseenter", () => showEqHoverMarker(freq));
    line.addEventListener("mouseleave", hideEqHoverMarker);
  }
  if (/satura/i.test(msg)) {
    line.style.cursor = "pointer";
    line.addEventListener("click", triggerGlitch);
  }
}

function showEqHoverMarker(freq) {
  const marker = document.getElementById("eq-hover-marker");
  if (!marker) return;
  const x = freqToX(freq);
  marker.setAttribute("x1", x.toFixed(1));
  marker.setAttribute("x2", x.toFixed(1));
  marker.classList.remove("hidden");
  flashDetail("eq-detail", `${(freq / 1000).toFixed(2)}kHz`);
}

function hideEqHoverMarker() {
  const marker = document.getElementById("eq-hover-marker");
  if (marker) marker.classList.add("hidden");
}

function triggerGlitch() {
  const rack = document.querySelector(".rack");
  if (rack) {
    rack.classList.remove("glitch");
    void rack.offsetWidth;
    rack.classList.add("glitch");
  }
  if (window.avatarAPI) window.avatarAPI.onGlitch();
}

function setAssistantLabel(text) {
  const label = document.getElementById("assistant-label");
  if (label) label.textContent = text;
}

// --- Reactions driven by real DSP values, not a canned loop ---

function reactToCompression(ratio, releaseMs) {
  if (window.avatarAPI) window.avatarAPI.onCompression(ratio, releaseMs);
}

function reactToGlueCompression(ratio) {
  if (window.avatarAPI) window.avatarAPI.onGlueCompression(ratio);
}

function setListening(on) {
  const hp = document.getElementById("headphones");
  if (!hp) return;
  hp.classList.toggle("active", on);
  if (window.avatarAPI) window.avatarAPI.onListening(on);
}

// --- Neural Monitor (Live Audition): lets the user hear a real before/after
// through actual speakers (redline/audition.py), not just read a ratio.
function toggleAudition() {
  const isChecked = document.getElementById("audition-switch").checked;
  if (window.pywebview) {
    window.pywebview.api.toggle_neural_monitor(isChecked);
  }
}

// Called directly from Python (api.py's _audition) around each half of the
// dry/wet playback -- reflects what's coming out of the speakers right now
// onto the avatar so the A/B comparison reads as one continuous moment,
// not a silent pause.
function setAuditionState(state) {
  if (window.avatarAPI) window.avatarAPI.onAuditionState(state);
  if (state === "BEFORE") {
    setAssistantLabel("ascolto: grezzo");
  } else if (state === "AFTER") {
    setAssistantLabel("ascolto: mixato");
  } else {
    setAssistantLabel("pronto");
  }
}

function reactToDeesser() {
  if (window.avatarAPI) window.avatarAPI.onDeesser();
}

function syncAssistantToBpm(bpm) {
  if (window.avatarAPI) window.avatarAPI.onBpm(bpm);
}

// --- Fase 5: local LLM advisory UX. Local CPU inference can take tens of
// seconds; these three functions exist so that wait reads as "the machine
// is thinking" rather than a frozen UI: a slow dark-red halo on the
// assistant, a live streaming console of the model's raw output, and a
// 60fps cylon sweep bar that keeps moving independently of the DSP/LLM
// thread to prove the UI thread itself hasn't hung.
let cylonAnimationId = null;

function startDeepScan(stemCount) {
  if (window.avatarAPI) window.avatarAPI.onDeepScan(stemCount);
  const assistant = document.getElementById("assistant");
  if (assistant) assistant.classList.add("deep-scan");
  setAssistantLabel("deep scan...");
  const console_ = document.getElementById("llm-console");
  const consoleWrap = document.getElementById("llm-console-wrap");
  if (console_) console_.textContent = "";
  if (consoleWrap) consoleWrap.classList.add("active");
  const bar = document.getElementById("cylon-bar");
  if (bar) bar.classList.add("active");
  startCylonLoop();
  addEventChip(`\u{1F9E0} LLM advisory: analizzo ${stemCount} stem ambigui...`);
}

function appendLlmToken(text) {
  const console_ = document.getElementById("llm-console");
  if (!console_) return;
  console_.textContent += text;
  console_.scrollTop = console_.scrollHeight;
}

function stopDeepScan() {
  if (window.avatarAPI) window.avatarAPI.onDeepScanDone();
  const assistant = document.getElementById("assistant");
  if (assistant) assistant.classList.remove("deep-scan");
  setAssistantLabel("");
  const consoleWrap = document.getElementById("llm-console-wrap");
  if (consoleWrap) consoleWrap.classList.remove("active");
  const bar = document.getElementById("cylon-bar");
  if (bar) bar.classList.remove("active");
  if (cylonAnimationId !== null) {
    cancelAnimationFrame(cylonAnimationId);
    cylonAnimationId = null;
  }
}

function startCylonLoop() {
  if (cylonAnimationId !== null) return; // already running
  const eye = document.getElementById("cylon-bar-eye");
  const bar = document.getElementById("cylon-bar");
  if (!eye || !bar) return;

  function sweep(timestamp) {
    const period = 1400; // ms for a full left-right-left cycle
    const t = (timestamp % period) / period;
    // triangle wave 0..1..0 so the eye reverses direction at each edge
    const phase = t < 0.5 ? t * 2 : 2 - t * 2;
    const travel = bar.clientWidth - eye.clientWidth;
    eye.style.transform = `translateX(${(phase * travel).toFixed(1)}px)`;
    cylonAnimationId = requestAnimationFrame(sweep);
  }
  cylonAnimationId = requestAnimationFrame(sweep);
}

// --- Web Audio chime: a short tone on render completion/error, so the user
// can look away during a 40-60s LLM/DSP wait and still notice when it's
// done. Independent of the native sd.play() audition/monitor path -- this
// is a browser-side AudioContext beep, no engine audio involved.
let _chimeCtx = null;

function _getChimeCtx() {
  if (!_chimeCtx) {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (Ctx) _chimeCtx = new Ctx();
  }
  return _chimeCtx;
}

function playChime(kind) {
  const ctx = _getChimeCtx();
  if (!ctx) return;
  const freqs = kind === "error" ? [220, 175] : [880, 1320];
  const now = ctx.currentTime;
  freqs.forEach((freq, i) => {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = freq;
    const start = now + i * 0.11;
    gain.gain.setValueAtTime(0, start);
    gain.gain.linearRampToValueAtTime(0.15, start + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.001, start + 0.25);
    osc.connect(gain).connect(ctx.destination);
    osc.start(start);
    osc.stop(start + 0.3);
  });
}

// --- UI sound design: short, quiet Web Audio blips for deliberate,
// infrequent interactions (button clicks, panel open/close, screen
// transitions, module hover) -- shares the chime's AudioContext. Explicitly
// NOT wired to high-frequency events (badge lighting, per-stem log lines
// fire "dozens of times per second during a render" per onEvent's own
// comments) -- that volume of clicks would be a buzz, not a cue.
function _playUiTone(freq, peak = 0.045, dur = 0.08, type = "sine") {
  const ctx = _getChimeCtx();
  if (!ctx) return;
  const now = ctx.currentTime;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = type;
  osc.frequency.value = freq;
  gain.gain.setValueAtTime(0, now);
  gain.gain.linearRampToValueAtTime(peak, now + 0.008);
  gain.gain.exponentialRampToValueAtTime(0.001, now + dur);
  osc.connect(gain).connect(ctx.destination);
  osc.start(now);
  osc.stop(now + dur + 0.02);
}

function playClickTick() { _playUiTone(1100, 0.04, 0.05); }
function playHoverTick() { _playUiTone(2400, 0.012, 0.025); }
function playPanelOpen() { _playUiTone(660, 0.045, 0.12, "triangle"); }
function playPanelClose() { _playUiTone(440, 0.035, 0.1, "triangle"); }
function playWhoosh() { _playUiTone(320, 0.03, 0.16, "sine"); }

// Delegated so it covers every .btn on the page, including ones added
// dynamically later (result cards, DAW screen) without re-binding anything.
document.addEventListener("click", (e) => {
  const btn = e.target.closest(".btn");
  if (btn && !btn.disabled) playClickTick();
});

// Static rack modules only (9 fixed cards from index.html) -- a hover tick
// on every button/row would be noisy; this is deliberately limited to the
// handful of large, static rack cards.
document.querySelectorAll(".module").forEach((m) => {
  m.addEventListener("mouseenter", () => playHoverTick());
});

function onDone(result) {
  document.getElementById("spinner").classList.add("hidden");
  document.getElementById("progress-wrap")?.classList.add("hidden");
  const resultEl = document.getElementById("result");
  resultEl.classList.remove("hidden");

  playChime(result && result.ok ? "done" : "error");

  if (result && result.ok && result.stage === "mix") {
    // Workflow choice was "stop after mix" (or mastering was skipped
    // entirely): show the mix DAW instead of a final result -- listen,
    // optionally describe/adjust changes, then either re-render just the
    // mix or continue on to mastering.
    lastRunResult = result;
    resultEl.innerHTML = `
      <div class="result-card daw-card">
        <div class="result-title">Mix pronto</div>
        <div>Genere: ${result.genre} &middot; BPM: ${result.bpm.toFixed(1)} &middot; Tonalit&agrave;: ${result.key}</div>

        <div id="daw-waveforms" class="daw-waveforms"><div class="daw-loading">Carico le tracce...</div></div>
        <div id="daw-track-detail" class="stem-row-detail hidden"></div>

        <div class="audition-abc">
          <div class="audition-abc-label">Riascolta:</div>
          <button class="btn" onclick="auditionStage('dry')">Senza mix</button>
          <button class="btn" onclick="auditionStage('mix')">Con mix</button>
          <label class="loudness-match-label" title="Confronto a parit&agrave; di volume (LUFS)">
            <input type="checkbox" id="loudness-match-switch" onchange="toggleLoudnessMatch()">
            Match LUFS
          </label>
        </div>
        ${_blendSliderHtml("dry", "mix", "Senza mix", "Con mix")}

        <div class="feedback-box">
          <label for="feedback-text">Cosa vorresti cambiare nel mix? (es. "voce pi&ugrave; avanti", "pi&ugrave; caldo")</label>
          <textarea id="feedback-text" rows="2" placeholder="Descrivi le modifiche, o lascia vuoto e clicca solo Rielabora"></textarea>
          <button class="btn" onclick="reprocessMix()">Rielabora il mix</button>
          <button class="btn" onclick="undoLastChange()" title="Ctrl+Z">Annulla</button>
          <button class="btn" onclick="redoLastChange()" title="Ctrl+Shift+Z">Ripeti</button>
          <div id="feedback-status"></div>
        </div>

        <button class="btn btn-accent" onclick="continueToMastering()">Procedi al mastering</button>
        <button class="btn" onclick="openOutput()">Apri cartella risultati</button>
        <button class="btn" onclick="exportFinal('mix')">Esporta mix...</button>
      </div>`;
    renderDawWaveforms();
    return;
  }

  if (result && result.ok) {
    lastRunResult = result;
    resultEl.innerHTML = `
      <div class="result-card">
        <div class="result-title">Fatto</div>
        <div>Genere: ${result.genre} &middot; BPM: ${result.bpm.toFixed(1)} &middot; Tonalit&agrave;: ${result.key}</div>
        <div>Loudness: ${result.lufs.toFixed(1)} LUFS</div>
        <button class="btn btn-accent" onclick="openOutput()">Apri cartella risultati</button>
        <button class="btn" onclick="exportFinal('auto')">Esporta...</button>

        <div class="audition-abc">
          <div class="audition-abc-label">Riascolta:</div>
          <button class="btn" onclick="auditionStage('dry')">Senza mix</button>
          <button class="btn" onclick="auditionStage('mix')">Con mix</button>
          <button class="btn" onclick="auditionStage('master')" ${result.master_path ? "" : "disabled"}>Con mastering</button>
          <label class="loudness-match-label" title="Confronto a parit&agrave; di volume (LUFS)">
            <input type="checkbox" id="loudness-match-switch" onchange="toggleLoudnessMatch()">
            Match LUFS
          </label>
        </div>
        ${result.master_path ? _blendSliderHtml("mix", "master", "Solo mix", "Con mastering") : ""}

        <div class="feedback-box">
          <label for="feedback-text">Feedback (es. "pi&ugrave; caldo", "pi&ugrave; forte", "pi&ugrave; brillante")</label>
          <textarea id="feedback-text" rows="2" placeholder="Cosa vorresti cambiare?"></textarea>
          <button class="btn btn-accent" onclick="submitFeedback()" ${result.master_path ? "" : "disabled"}>Rielabora (veloce)</button>
          <div id="feedback-status"></div>
        </div>

        <div class="daw-reopen-buttons">
          <button class="btn" onclick="reopenDaw('mix')">MIX</button>
          <button class="btn" onclick="reopenDaw('master')" ${result.master_path ? "" : "disabled"}>MASTERING</button>
        </div>
      </div>`;
  } else {
    const errorMsg = result ? result.error : "errore sconosciuto";
    resultEl.innerHTML = `<div class="result-card error">Errore: ${errorMsg}</div>`;
  }
}

let lastRunResult = null;

// --- Real waveform DAW view: was previously just a plugin-parameter list
// with no audio shown at all -- this renders an actual per-track waveform
// on a shared timeline (so misalignment between takes is visible at a
// glance, same as any real DAW's track view), backed by
// api.get_waveform_peaks() (downsampled min/max envelopes, never raw
// sample data). Clicking a lane reuses the same recorded-parameter data
// the per-stem rows' channel strip already collects (see
// stemEventParams/_describeStemEvent above).
async function renderDawWaveforms() {
  const container = document.getElementById("daw-waveforms");
  if (!container || !window.pywebview) return;
  const data = await window.pywebview.api.get_waveform_peaks(600);
  if (!data || !data.ok) {
    container.innerHTML = `<div class="daw-loading">Forme d'onda non disponibili.</div>`;
    return;
  }

  const names = Object.keys(data.tracks).filter((n) => n !== "__MIX__");
  const orderedNames = data.tracks["__MIX__"] ? ["__MIX__", ...names] : names;

  container.innerHTML = "";
  for (const name of orderedNames) {
    const lane = document.createElement("div");
    lane.className = "daw-track-lane" + (name === "__MIX__" ? " daw-track-lane-mix" : "");

    const label = document.createElement("div");
    label.className = "daw-track-label";
    label.textContent = name === "__MIX__" ? "MIX (riferimento)" : name;
    label.title = name;
    lane.appendChild(label);

    const canvas = document.createElement("canvas");
    canvas.className = "daw-track-canvas";
    canvas.width = 600;
    canvas.height = 40;
    lane.appendChild(canvas);

    _drawWaveform(canvas, data.tracks[name]);

    if (name !== "__MIX__") {
      lane.addEventListener("click", () => _toggleDawTrackDetail(name, lane));
    }

    container.appendChild(lane);
  }
}

function _drawWaveform(canvas, peaks) {
  const ctx = canvas.getContext("2d");
  const w = canvas.width, h = canvas.height, mid = h / 2;
  ctx.clearRect(0, 0, w, h);
  ctx.strokeStyle = "#FF003F";
  ctx.lineWidth = 1;
  if (!peaks || peaks.length === 0) return;
  const step = w / peaks.length;
  ctx.beginPath();
  for (let i = 0; i < peaks.length; i++) {
    const [lo, hi] = peaks[i];
    const x = i * step;
    ctx.moveTo(x, mid - hi * mid);
    ctx.lineTo(x, mid - lo * mid);
  }
  ctx.stroke();
}

function _toggleDawTrackDetail(name, lane) {
  const detail = document.getElementById("daw-track-detail");
  if (!detail) return;
  document.querySelectorAll(".daw-track-lane.selected").forEach((l) => l.classList.remove("selected"));
  const wasOpenForThisTrack = !detail.classList.contains("hidden") && detail.dataset.track === name;
  if (wasOpenForThisTrack) {
    detail.classList.add("hidden");
    playPanelClose();
    return;
  }
  const params = stemEventParams.get(name) || {};
  const lines = Object.entries(params).map(([type, evt]) => _describeStemEvent(type, evt));
  detail.innerHTML = lines.length
    ? `<div class="stem-row-detail-line"><strong>${name}</strong></div>` + lines.map((l) => `<div class="stem-row-detail-line">${l}</div>`).join("")
    : `<div class="stem-row-detail-line">Nessun parametro registrato per questa traccia.</div>`;
  detail.dataset.track = name;
  detail.classList.remove("hidden");
  playPanelOpen();
  lane.classList.add("selected");
}

// Undo/redo for mix reprocessing: swaps a cached buffer server-side (see
// undo_mix/redo_mix in api.py) -- no DSP re-render, so this stays fast no
// matter how long the original "Rielabora il mix" took.
async function undoLastChange() {
  if (!window.pywebview) return;
  const res = await window.pywebview.api.undo_mix();
  if (res && res.ok) {
    addEventChip("↩️ Mix: annullato");
    if (lastRunResult) onDone({ ...lastRunResult, stage: "mix" });
  } else if (res) {
    addEventChip(`ℹ️ ${res.error}`);
  }
}

async function redoLastChange() {
  if (!window.pywebview) return;
  const res = await window.pywebview.api.redo_mix();
  if (res && res.ok) {
    addEventChip("↪️ Mix: ripristinato");
    if (lastRunResult) onDone({ ...lastRunResult, stage: "mix" });
  } else if (res) {
    addEventChip(`ℹ️ ${res.error}`);
  }
}

// "Rielabora il mix": re-runs only render_mix (stems/analysis already
// cached server-side) with the edited feedback text, then re-shows the
// mix DAW with the new result.
async function reprocessMix() {
  const status = document.getElementById("feedback-status");
  const text = document.getElementById("feedback-text")?.value?.trim() || "";
  if (status) status.textContent = "Rielaborazione in corso...";
  const prefs = { creative_brief: text };
  const result = await window.pywebview.api.reprocess_mix(prefs);
  onDone(result);
}

// "Procedi al mastering": resumes from the cached mix straight into the
// mastering stage, then shows the normal final result screen.
async function continueToMastering() {
  const platform = document.getElementById("platform")?.value || "auto";
  const result = await window.pywebview.api.continue_to_mastering({ platform });
  onDone(result);
}

// Final-screen "MIX"/"MASTERING" buttons: reopen the relevant DAW view at
// any point after the pipeline has finished, without re-running anything.
function reopenDaw(which) {
  if (!lastRunResult) return;
  if (which === "mix") {
    onDone({ ...lastRunResult, stage: "mix" });
  } else {
    onDone({ ...lastRunResult, stage: "master" });
  }
}

function openOutput() {
  window.pywebview.api.open_folder(selectedOutput);
}

// --- Session History screen: past renders persisted server-side
// (~/.redline/sessions.json via redline/session_history.py), listed most
// recent first with the fields that already come back from run_pipeline.
async function openSessionHistory() {
  goToScreen("screen-history");
  const list = document.getElementById("session-history-list");
  if (!list || !window.pywebview) return;
  list.innerHTML = `<div class="daw-loading">Carico la cronologia...</div>`;
  const sessions = await window.pywebview.api.list_sessions();
  if (!sessions || sessions.length === 0) {
    list.innerHTML = `<div class="daw-loading">Nessuna sessione precedente.</div>`;
    return;
  }
  list.innerHTML = sessions.map((s) => {
    const date = new Date(s.timestamp * 1000).toLocaleString("it-IT");
    const stageLabel = s.stage === "master" ? "Mix + Mastering" : "Solo mix";
    return `
      <div class="session-history-row">
        <div class="session-history-main">
          <div class="session-history-date">${date}</div>
          <div>${s.genre || "?"} &middot; BPM ${s.bpm ? s.bpm.toFixed(1) : "?"} &middot; ${s.key || "?"} &middot; ${s.lufs ? s.lufs.toFixed(1) : "?"} LUFS &middot; ${stageLabel}</div>
        </div>
        <button class="btn" onclick="openSessionFolder('${s.id}')">Apri cartella</button>
      </div>`;
  }).join("");
}

async function openSessionFolder(id) {
  if (!window.pywebview) return;
  const res = await window.pywebview.api.open_session_folder(id);
  if (res && !res.ok) addEventChip(`⚠️ ${res.error}`);
}

async function exportFinal(stage) {
  if (!window.pywebview) return;
  const res = await window.pywebview.api.export_final(stage || "auto");
  if (res && res.ok) {
    addEventChip(`\u{1F4E6} Esportato: ${res.path}`);
  } else if (res && res.error !== "Esportazione annullata.") {
    addEventChip(`⚠️ Esportazione fallita: ${res.error}`);
  }
}

// --- Post-render re-evaluation: A/B/C audition of the three cached render
// stages, and free-text feedback that triggers a fast re-mastering-only
// pass (skips re-running the mix, which is the expensive part).

let _lastAuditionStage = null;

async function auditionStage(stage) {
  if (!window.pywebview) return;
  _lastAuditionStage = stage;
  const lm = document.getElementById("loudness-match-switch")?.checked || false;
  const res = await window.pywebview.api.audition_stage(stage, lm);
  if (res && !res.ok) {
    addEventChip(`\u{26A0}\u{FE0F} Ascolto non disponibile: ${res.error}`);
  }
}

// Quick-Compare slider: not a live crossfade (see audition_blend() in
// api.py for why) -- dragging just moves the handle, releasing computes one
// fresh (1-t)*a + t*b blend server-side and plays it once. Honest tradeoff:
// costs one playback round-trip per release instead of true real-time audio.
function _blendSliderHtml(stageA, stageB, labelA, labelB) {
  return `
    <div class="blend-slider-row">
      <span class="blend-slider-label">${labelA}</span>
      <input type="range" class="blend-slider" min="0" max="1" step="0.01" value="0"
             data-stage-a="${stageA}" data-stage-b="${stageB}"
             onchange="auditionBlend(this)">
      <span class="blend-slider-label">${labelB}</span>
    </div>`;
}

async function auditionBlend(slider) {
  if (!window.pywebview) return;
  const t = parseFloat(slider.value);
  const res = await window.pywebview.api.audition_blend(slider.dataset.stageA, slider.dataset.stageB, t);
  if (res && !res.ok) {
    addEventChip(`\u{26A0}\u{FE0F} Confronto non disponibile: ${res.error}`);
  }
}

function toggleLoudnessMatch() {
  const lm = document.getElementById("loudness-match-switch")?.checked || false;
  if (_lastAuditionStage && window.pywebview) {
    window.pywebview.api.audition_stage(_lastAuditionStage, lm);
  }
}

async function submitFeedback() {
  const input = document.getElementById("feedback-text");
  const status = document.getElementById("feedback-status");
  const text = input ? input.value.trim() : "";
  if (!text || !window.pywebview) return;
  if (status) status.textContent = "Ricalibro...";
  const res = await window.pywebview.api.submit_feedback(text);
  if (status) {
    status.textContent = res && res.ok
      ? `Nuova versione salvata (v${res.version}): ${res.master_path}`
      : `Errore: ${res ? res.error : "sconosciuto"}`;
  }
}

// --- Director Mode: the pipeline is genuinely paused on a Python thread
// (threading.Event) waiting for this exact button click -- nothing here is
// simulated, approveDirectorCheckpoint() really does unblock render_mix().
// Each stem gets a role/layer/register dropdown pre-selected to what the
// engine already guessed, so confirming without touching anything is a
// single click (sends {}, no corrections) and fixing a wrong guess is a
// couple more clicks, not retyping everything by hand.
const ROLE_ICONS = { vocal: "\u{1F3A4}", bass: "\u{1F3B8}", drums: "\u{1F941}", other: "\u{1F3B9}" };
const ROLE_OPTIONS = ["vocal", "bass", "drums", "other"];
const ROLE_LABELS = { vocal: "Voce", bass: "Basso", drums: "Batteria", other: "Altro" };
const LAYER_OPTIONS = ["primary", "double"];
const LAYER_LABELS = { primary: "Principale", double: "Doppia" };
// Only these actually change the engine's per-register DSP recipe
// (vocalstack.py) -- "-- auto --" leaves the engine's own pitch-based
// classification in charge, same as not touching the dropdown at all.
const REGISTER_OPTIONS = ["", "low", "unison", "high", "falsetto"];
const REGISTER_LABELS = { "": "-- auto --", low: "Basso", unison: "Unisono", high: "Alto", falsetto: "Falsetto" };

function _selectHtml(id, options, labels, current) {
  const opts = options
    .map((v) => `<option value="${v}"${v === current ? " selected" : ""}>${labels[v] ?? v}</option>`)
    .join("");
  return `<select id="${id}">${opts}</select>`;
}

function showDirectorCheckpoint(evt) {
  const panel = document.getElementById("director-panel");
  const list = document.getElementById("director-stems");
  if (!panel || !list) return;

  list.innerHTML = evt.stems
    .map((s, i) => {
      const icon = ROLE_ICONS[s.role] || "\u{2753}";
      return `
        <div class="director-stem-row stem-correction-row" data-stem="${s.name}">
          <span class="stem-correction-name">${icon} <strong>${s.name}</strong></span>
          <span class="stem-correction-fields">
            ${_selectHtml(`stem-role-${i}`, ROLE_OPTIONS, ROLE_LABELS, s.role)}
            ${_selectHtml(`stem-layer-${i}`, LAYER_OPTIONS, LAYER_LABELS, s.layer)}
            ${_selectHtml(`stem-register-${i}`, REGISTER_OPTIONS, REGISTER_LABELS, s.register || "")}
          </span>
        </div>`;
    })
    .join("");

  panel.classList.remove("hidden");
  playPanelOpen();
  setAssistantLabel("in attesa di conferma");
}

function approveDirectorCheckpoint() {
  const panel = document.getElementById("director-panel");
  const corrections = {};
  if (panel) {
    panel.querySelectorAll(".stem-correction-row").forEach((row, i) => {
      const stem = row.dataset.stem;
      const role = document.getElementById(`stem-role-${i}`)?.value;
      const layer = document.getElementById(`stem-layer-${i}`)?.value;
      const register = document.getElementById(`stem-register-${i}`)?.value;
      const fix = {};
      if (role) fix.role = role;
      if (layer) fix.layer = layer;
      if (register) fix.register = register;
      if (Object.keys(fix).length > 0) corrections[stem] = fix;
    });
    panel.classList.add("hidden");
    playPanelClose();
  }
  if (window.avatarAPI) window.avatarAPI.onApprove();
  if (window.pywebview) {
    window.pywebview.api.approve_director_checkpoint(corrections);
  }
}

// --- Instrument-identity questions: mixengine.py's
// render_mix() is genuinely blocked on a Python thread waiting for
// answer_instrument_questions(), same pausing mechanism as the role
// checkpoint above, just carrying back an actual answer per stem instead
// of a plain yes/no.
const INSTRUMENT_LABELS = {
  strings: "Archi", guitar_acoustic: "Chitarra acustica", guitar_electric: "Chitarra elettrica",
  keys: "Piano/Tastiere", organ: "Organo", brass: "Fiati", percussion: "Percussioni",
  choir: "Coro", synth_pad: "Synth pad", synth_lead: "Synth lead", generic: "Generico (nessuna preferenza)",
};

function showInstrumentQuestions(evt) {
  const panel = document.getElementById("instrument-questions-panel");
  const list = document.getElementById("instrument-questions-list");
  if (!panel || !list) return;

  list.innerHTML = (evt.questions || [])
    .map((q, i) => {
      const options = q.options
        .map((opt) => `<option value="${opt}">${INSTRUMENT_LABELS[opt] || opt}</option>`)
        .join("");
      return `
        <div class="director-stem-row instrument-question-row">
          <strong>${q.stem}</strong>
          <select id="instrument-answer-${i}" data-stem="${q.stem}">
            <option value="">-- non so, lascia decidere al motore --</option>
            ${options}
          </select>
        </div>`;
    })
    .join("");

  panel.classList.remove("hidden");
  playPanelOpen();
  setAssistantLabel("in attesa di risposta");
}

function submitInstrumentAnswers() {
  const panel = document.getElementById("instrument-questions-panel");
  const answers = {};
  panel.querySelectorAll("select[data-stem]").forEach((sel) => {
    if (sel.value) answers[sel.dataset.stem] = sel.value;
  });
  if (panel) panel.classList.add("hidden");
  playPanelClose();
  if (window.pywebview) {
    window.pywebview.api.answer_instrument_questions(answers);
  }
}

// --- Animated "studio rack": every visual here reacts to a real value the
// engine just computed (an actual EQ freq/gain, a real compressor ratio, a
// real de-esser band, a real QC measurement) — not a generic looping
// animation. onEvent() is called by app/api.py's _emit(), fed straight from
// the on_event callbacks threaded through mixengine.py/masterengine.py.

let eqBands = {}; // key -> {freq, gain} — the currently-drawn curve (bus tilt + at most one stem's own bands, see renderStemChannelStrip)

const FREQ_MIN = 20;
const FREQ_MAX = 20000;

function freqToX(freq) {
  const t = (Math.log10(freq) - Math.log10(FREQ_MIN)) / (Math.log10(FREQ_MAX) - Math.log10(FREQ_MIN));
  return Math.max(0, Math.min(300, t * 300));
}

function gainToY(gainDb) {
  return 45 - Math.max(-6, Math.min(6, gainDb)) * 6;
}

function redrawEq() {
  const points = Object.values(eqBands).sort((a, b) => a.freq - b.freq);
  if (points.length === 0) {
    document.getElementById("eq-path").setAttribute("d", "M0,45 L300,45");
    return;
  }
  let d = `M0,${gainToY(0)} `;
  for (const p of points) {
    d += `L${freqToX(p.freq).toFixed(1)},${gainToY(p.gain_db).toFixed(1)} `;
  }
  d += `L300,${gainToY(0)}`;
  document.getElementById("eq-path").setAttribute("d", d);
}

// VU meter: maps a LUFS value (typical mix range -30..0) to a 0-100% fill.
// Updated only on discrete events (qc_report, loudness_gain) -- there is no
// continuous audio level stream from the engine to drive a "live" meter.
function updateVuMeter(lufs, label) {
  const fill = document.getElementById("vu-fill");
  const detail = document.getElementById("vu-detail");
  if (!fill) return;
  const pct = Math.max(0, Math.min(100, ((lufs + 30) / 30) * 100));
  fill.style.width = `${pct.toFixed(0)}%`;
  if (detail) detail.textContent = label || `${lufs.toFixed(1)} LUFS`;
}

function flashDetail(id, text) {
  const el = document.getElementById(id);
  el.textContent = text;
  el.classList.add("flash");
  setTimeout(() => el.classList.remove("flash"), 400);

  const module = el.closest(".module");
  if (module) {
    module.classList.add("module-active");
    clearTimeout(module._activeTimer);
    module._activeTimer = setTimeout(() => module.classList.remove("module-active"), 500);
  }
}

// --- Per-stem breakdown rows: one row per track for the whole render,
// keyed by stem name, so processing the same stem again (e.g. a double's
// register-classification thread finishing after another stem's) re-uses
// its existing row and lights up the badge for whatever stage just fired,
// instead of the old scrolling log where earlier stems' progress just
// disappeared off the top.
const STEM_STAGE_BADGES = [
  { key: "instrument", label: "INST" },
  { key: "denoise", label: "NR" },
  { key: "hpf", label: "HPF" },
  { key: "resonance", label: "RES" },
  { key: "compressor", label: "COMP" },
  { key: "deesser", label: "DEESS" },
  { key: "saturation", label: "SAT" },
  { key: "masking", label: "MASK" },
  { key: "reverb", label: "VERB" },
  { key: "register", label: "REG" },
];
const stemRows = new Map(); // stem name -> { row, badges: {stageKey: el} }

function getOrCreateStemRow(name) {
  if (stemRows.has(name)) return stemRows.get(name);
  const container = document.getElementById("stem-rows");
  if (!container) return null;

  const row = document.createElement("div");
  row.className = "stem-row";
  row.title = "Clicca per vedere i parametri di questa traccia";

  const label = document.createElement("div");
  label.className = "stem-row-label";
  label.textContent = name;
  label.title = name;
  row.appendChild(label);

  const badgeStrip = document.createElement("div");
  badgeStrip.className = "stem-row-badges";
  const badges = {};
  for (const stage of STEM_STAGE_BADGES) {
    const b = document.createElement("span");
    b.className = "stem-badge";
    b.textContent = stage.label;
    badgeStrip.appendChild(b);
    badges[stage.key] = b;
  }
  row.appendChild(badgeStrip);

  // Channel-strip detail panel: hidden until the row is clicked, then shows
  // every recorded parameter for this stem in one place -- a first, minimal
  // version of the "click a track to see/adjust its plugins" DAW view.
  const detail = document.createElement("div");
  detail.className = "stem-row-detail hidden";
  row.appendChild(detail);

  row.addEventListener("click", (ev) => {
    if (ev.target.closest(".stem-row-detail")) return; // clicks inside the detail panel don't toggle it shut
    // Pins the rack's EQ/compressor/de-esser/saturation/reverb modules to
    // this stem's own chain -- stays pinned until the pipeline moves on to
    // processing a different stem live, or forever if the render already
    // finished (see _routeStemEvent).
    pinStemChannelStrip(name);
    const isOpen = !detail.classList.contains("hidden");
    // Only one channel strip open at a time -- keeps the track list scannable.
    document.querySelectorAll(".stem-row-detail").forEach((d) => d.classList.add("hidden"));
    document.querySelectorAll(".stem-row.selected").forEach((r) => r.classList.remove("selected"));
    if (isOpen) { playPanelClose(); return; }
    const params = stemEventParams.get(name) || {};
    const lines = Object.entries(params).map(([type, evt]) => _describeStemEvent(type, evt));
    detail.innerHTML = lines.length
      ? lines.map((l) => `<div class="stem-row-detail-line">${l}</div>`).join("")
      : `<div class="stem-row-detail-line">Nessun parametro registrato ancora.</div>`;
    detail.classList.remove("hidden");
    playPanelOpen();
    row.classList.add("selected");
  });

  container.appendChild(row);
  const entry = { row, badges, detail };
  stemRows.set(name, entry);
  _makeStemRowDraggable(row, name);
  _applySavedStemOrder();
  return entry;
}

// --- Drag-to-reorder stem rows: HTML5 drag & drop, order persisted in
// localStorage per output folder so it survives across runs on the same
// project (a fresh run on a different folder starts unsorted again).
const STEM_ORDER_KEY = "redline_stem_order";

function _stemOrderKey() {
  return `${STEM_ORDER_KEY}:${selectedOutput || "default"}`;
}

function _makeStemRowDraggable(row, name) {
  row.draggable = true;
  row.dataset.stemName = name;

  row.addEventListener("dragstart", (e) => {
    e.dataTransfer.setData("text/plain", name);
    row.classList.add("dragging");
  });
  row.addEventListener("dragend", () => row.classList.remove("dragging"));
  row.addEventListener("dragover", (e) => {
    e.preventDefault();
    const container = document.getElementById("stem-rows");
    const dragging = container.querySelector(".dragging");
    if (!dragging || dragging === row) return;
    const rect = row.getBoundingClientRect();
    const after = (e.clientY - rect.top) > rect.height / 2;
    container.insertBefore(dragging, after ? row.nextSibling : row);
  });
  row.addEventListener("drop", (e) => {
    e.preventDefault();
    _persistStemOrder();
  });
}

function _persistStemOrder() {
  const container = document.getElementById("stem-rows");
  if (!container) return;
  const order = Array.from(container.children).map((el) => el.dataset.stemName).filter(Boolean);
  try {
    localStorage.setItem(_stemOrderKey(), JSON.stringify(order));
  } catch (e) { /* localStorage unavailable -- reordering just won't persist */ }
}

function _applySavedStemOrder() {
  const container = document.getElementById("stem-rows");
  if (!container) return;
  let saved;
  try {
    saved = JSON.parse(localStorage.getItem(_stemOrderKey()) || "null");
  } catch (e) {
    return;
  }
  if (!Array.isArray(saved) || saved.length === 0) return;

  const rowsByName = new Map(Array.from(container.children).map((el) => [el.dataset.stemName, el]));
  for (const name of saved) {
    const el = rowsByName.get(name);
    if (el) container.appendChild(el);
  }
}

function touchStemRow(name) {
  const entry = getOrCreateStemRow(name);
  if (!entry) return;
  entry.row.classList.add("row-active");
  clearTimeout(entry._activeTimer);
  entry._activeTimer = setTimeout(() => entry.row.classList.remove("row-active"), 1400);
}

function markStemStage(name, stageKey) {
  const entry = getOrCreateStemRow(name);
  if (!entry) return;
  touchStemRow(name);
  const badge = entry.badges[stageKey];
  if (!badge) return;
  badge.classList.add("done");
  badge.classList.add("flash");
  clearTimeout(badge._flashTimer);
  badge._flashTimer = setTimeout(() => badge.classList.remove("flash"), 900);
}

// Was a separate #event-feed box above #log -- two panels for one stream of
// "what's happening" read as redundant once the per-stem rows (#stem-rows)
// and the DAW panel took over showing structured state. Chips now append
// into the same #log panel as onStep's macro/micro lines, in the same
// chronological order they actually happened in, instead of two boxes the
// user had to cross-reference by eye.
function addEventChip(text) {
  const log = document.getElementById("log");
  const chip = document.createElement("div");
  chip.className = "log-line log-chip";
  chip.textContent = text;
  log.appendChild(chip);
  log.scrollTop = log.scrollHeight;
  while (log.children.length > 400) log.removeChild(log.firstChild);
}

// Generic per-stem parameter log: every event carrying `evt.stem` gets
// recorded here regardless of type, keyed by event type so a re-fired event
// (e.g. a corrected resonance cut) replaces its own previous entry instead
// of piling up duplicates. This is what makes stem rows clickable (A4) --
// it's also the data source the mix-review DAW (Part C) reads from, so no
// separate bookkeeping is needed once that screen exists.
const stemEventParams = new Map(); // stem name -> { evtType: evt }

function _recordStemParam(evt) {
  if (!evt || !evt.stem) return;
  if (!stemEventParams.has(evt.stem)) stemEventParams.set(evt.stem, {});
  stemEventParams.get(evt.stem)[evt.type] = evt;
}

// Human-readable one-line summary of a recorded event, for the channel-strip
// detail panel -- reuses the same field names the DSP layer already emits
// (freq_hz, gain_db, ratio, threshold_db, low_hz/high_hz, pan, instrument...)
// instead of a generic key:value dump.
function _describeStemEvent(type, evt) {
  const g = (v) => (v > 0 ? `+${v}` : `${v}`);
  switch (type) {
    case "instrument_chain": return `Strumento: ${evt.instrument}`;
    case "dynamic_hpf": return `HPF: ${evt.cutoff_hz}Hz (fondamentale ${evt.fundamental_hz}Hz)`;
    case "resonance_cut": return `Risonanza: ${evt.freq_hz}Hz ${g(evt.gain_db)}dB`;
    case "presence_boost": return `Presenza: ${evt.freq_hz}Hz ${g(evt.gain_db)}dB`;
    case "instrument_eq": return `EQ: ${evt.freq_hz}Hz ${g(evt.gain_db)}dB (${evt.kind})`;
    case "masking_cut": return `Mascheramento: ${evt.freq_hz}Hz ${g(evt.gain_db)}dB`;
    case "midrange_masking_cut": return `Accumulo medio: ${evt.freq_hz}Hz ${g(evt.gain_db)}dB`;
    case "compressor": return `Compressore: ${evt.ratio.toFixed(1)}:1 @ ${evt.threshold_db}dB (attack ${evt.attack_ms}ms)`;
    case "deesser": return `De-esser: banda ${Math.round(evt.low_hz)}-${Math.round(evt.high_hz)}Hz`;
    case "saturation": return `Saturazione: drive ${evt.drive}`;
    case "auto_pan": return `Pan: ${evt.pan > 0 ? "dx" : "sx"} ${Math.abs(evt.pan * 100).toFixed(0)}%`;
    case "reverb_send": return `Riverbero: ${evt.bus} ${Math.round(evt.mix * 100)}%`;
    case "register_classified": return `Registro: ${evt.register} (${evt.fundamental_hz}Hz)`;
    case "denoise": return `Riduzione rumore: attiva`;
    default: return type;
  }
}

// --- Per-track "channel strip" view: the EQ curve + compressor/de-esser/
// saturation/reverb modules show exactly one stem's own processing, not a
// running sum of every stem the pipeline has touched so far. _rackDisplayStem
// is either whichever stem is being processed live right now, or (once the
// user clicks a stem row) pinned there for inspection -- any later live
// event for a DIFFERENT stem always wins and breaks the pin, since that
// means the pipeline has moved on. Once the render finishes, no more
// per-stem events arrive, so whatever is displayed (live or pinned) just
// stays, which is also the "finished -> stays on what I clicked" behavior.
let _rackDisplayStem = null;
let _rackPinned = false;
// Bus-level EQ tilt (genre tilt, applied to the whole mix bus, not any one
// stem) -- kept separate from per-stem bands and always drawn underneath
// whichever stem's own curve is currently displayed.
let busEqBands = {};

function _routeStemEvent(evt) {
  if (!evt.stem) return;
  if (_rackDisplayStem !== evt.stem) {
    // Pipeline just moved on to a different stem -- any pin is stale now.
    _rackDisplayStem = evt.stem;
    _rackPinned = false;
  }
  renderStemChannelStrip(evt.stem);
}

// Called when the user clicks a stem row (see getOrCreateStemRow below).
function pinStemChannelStrip(name) {
  _rackDisplayStem = name;
  _rackPinned = true;
  renderStemChannelStrip(name);
}

function refreshEqDisplay() {
  if (_rackDisplayStem) {
    renderStemChannelStrip(_rackDisplayStem);
  } else {
    eqBands = { ...busEqBands };
    redrawEq();
  }
}

// Rebuilds the EQ curve and the per-stem plugin modules from exactly one
// stem's last-known parameters (stemEventParams -- the same source the
// text channel-strip detail panel already reads), instead of the
// accumulated total across every stem processed so far.
function renderStemChannelStrip(name) {
  const params = stemEventParams.get(name) || {};

  const bands = { ...busEqBands };
  if (params.resonance_cut) bands.res = { freq: params.resonance_cut.freq_hz, gain_db: params.resonance_cut.gain_db };
  if (params.presence_boost) bands.pres = { freq: params.presence_boost.freq_hz, gain_db: params.presence_boost.gain_db };
  if (params.instrument_eq) bands.inst = { freq: params.instrument_eq.freq_hz, gain_db: params.instrument_eq.gain_db };
  if (params.masking_cut) bands.mask = { freq: params.masking_cut.freq_hz, gain_db: params.masking_cut.gain_db };
  if (params.midrange_masking_cut) bands.midmask = { freq: params.midrange_masking_cut.freq_hz, gain_db: params.midrange_masking_cut.gain_db };
  eqBands = bands;
  redrawEq();

  const fill = document.getElementById("gr-fill");
  const comp = params.compressor;
  if (fill) fill.style.width = comp ? `${Math.min(100, (comp.ratio - 1) * 14)}%` : "0%";
  const compDetail = document.getElementById("comp-detail");
  if (compDetail) compDetail.textContent = comp ? `${name}: ${comp.ratio.toFixed(1)}:1 @ ${comp.threshold_db}dB` : "in attesa...";

  const dial = document.getElementById("deess-dial");
  const deess = params.deesser;
  if (dial) dial.textContent = deess ? `${(((deess.low_hz + deess.high_hz) / 2) / 1000).toFixed(1)}kHz` : "—";
  const deessDetail = document.getElementById("deess-detail");
  if (deessDetail) deessDetail.textContent = deess ? `${name}: banda ${deess.low_hz.toFixed(0)}-${deess.high_hz.toFixed(0)}Hz` : "in attesa...";

  const satDetail = document.getElementById("saturation-detail");
  const sat = params.saturation;
  if (satDetail) satDetail.textContent = sat ? `${name}: drive ${sat.drive}` : "in attesa...";

  const revDetail = document.getElementById("reverb-detail");
  const rev = params.reverb_send;
  if (revDetail) revDetail.textContent = rev ? `${name}: send ${rev.bus} ${Math.round(rev.mix * 100)}%` : "in attesa...";
}

function onEvent(evt) {
  bumpActivity();
  _recordStemParam(evt);
  switch (evt.type) {
    case "bus_eq_band":
      busEqBands[`bus_${evt.freq_hz}`] = { freq: evt.freq_hz, gain_db: evt.gain_db };
      refreshEqDisplay();
      flashDetail("eq-detail", `Bus: ${evt.freq_hz}Hz ${evt.gain_db > 0 ? "+" : ""}${evt.gain_db}dB`);
      break;

    case "stem_instrument":
      if (window.avatarAPI) window.avatarAPI.onInstrument(evt.instrument);
      addEventChip(`\u{1F3B8} ${evt.stem}: ${evt.instrument}`);
      break;

    case "instrument_chain":
      addEventChip(`\u{1F3BB} ${evt.stem}: catena '${evt.instrument}'`);
      markStemStage(evt.stem, "instrument");
      break;

    case "resonance_cut":
      _routeStemEvent(evt);
      flashDetail("eq-detail", `${evt.stem}: risonanza ${evt.freq_hz.toFixed(0)}Hz ${evt.gain_db}dB`);
      markStemStage(evt.stem, "resonance");
      break;

    case "dynamic_hpf":
      flashDetail("eq-detail", `${evt.stem}: HPF dinamico ${evt.cutoff_hz}Hz (fondamentale ${evt.fundamental_hz}Hz)`);
      addEventChip(`\u{1F3A4} ${evt.stem}: taglio adattivo a ${evt.cutoff_hz}Hz`);
      markStemStage(evt.stem, "hpf");
      break;

    // Was previously not emitted at all -- the EQ curve only ever showed
    // cuts (resonance_cut, masking_cut) because boosts (vocal presence,
    // several instrument recipes' presence/air shelves) were applied with
    // no event, making the engine look cut-only when it already boosts
    // where the instrument recipe calls for it.
    case "presence_boost":
      _routeStemEvent(evt);
      flashDetail("eq-detail", `${evt.stem}: presenza ${evt.gain_db > 0 ? "+" : ""}${evt.gain_db}dB @ ${evt.freq_hz}Hz`);
      addEventChip(`\u{2B06}\u{FE0F} ${evt.stem}: presenza ${evt.gain_db > 0 ? "+" : ""}${evt.gain_db}dB`);
      break;

    case "instrument_eq":
      _routeStemEvent(evt);
      flashDetail("eq-detail", `${evt.stem}: ${evt.gain_db > 0 ? "+" : ""}${evt.gain_db}dB @ ${evt.freq_hz}Hz`);
      addEventChip(`${evt.gain_db >= 0 ? "\u{2B06}\u{FE0F}" : "\u{2B07}\u{FE0F}"} ${evt.stem}: ${evt.gain_db > 0 ? "+" : ""}${evt.gain_db}dB @ ${evt.freq_hz}Hz`);
      markStemStage(evt.stem, "instrument");
      break;

    case "compressor":
    case "bus_compressor": {
      const ratio = evt.ratio;
      if (evt.stem) {
        _routeStemEvent(evt);
        flashDetail("comp-detail", `${evt.stem}: ${ratio.toFixed(1)}:1 @ ${evt.threshold_db}dB`);
        markStemStage(evt.stem, "compressor");
      } else if (!_rackPinned) {
        // Bus-level glue compressor -- not tied to any stem, so it only
        // drives the shared Compressore module while nothing is pinned;
        // a pinned per-stem channel strip keeps that module showing its
        // own stem's compressor instead of being overwritten by the bus.
        const pct = Math.min(100, (ratio - 1) * 14);
        const fill = document.getElementById("gr-fill");
        if (fill) fill.style.width = `${pct}%`;
        flashDetail("comp-detail", `bus: ${ratio.toFixed(1)}:1 @ ${evt.threshold_db}dB`);
      }
      reactToCompression(ratio, evt.release_ms);
      if (!evt.stem) {
        // No per-stem name on the event -- this is a bus-level compressor,
        // exactly the "how hard is the glue squeezing" moment the squint
        // reaction exists for.
        reactToGlueCompression(ratio);
      }
      break;
    }

    case "parallel_bus":
      addEventChip(`\u{1F3B8} Bus parallelo (NY comp) ${Math.round(evt.mix * 100)}%`);
      break;

    case "deesser": {
      _routeStemEvent(evt);
      const dial = document.getElementById("deess-dial");
      dial.classList.remove("pulse");
      void dial.offsetWidth; // restart animation
      dial.classList.add("pulse");
      flashDetail("deess-detail", `${evt.stem}: banda ${evt.low_hz.toFixed(0)}-${evt.high_hz.toFixed(0)}Hz`);
      markStemStage(evt.stem, "deesser");
      reactToDeesser();
      break;
    }

    case "time_align":
      addEventChip(`\u{23F1}\u{FE0F} ${evt.stem} allineata (${evt.delay_ms > 0 ? "+" : ""}${evt.delay_ms}ms)`);
      break;

    case "denoise":
      addEventChip(`\u{1F9FC} ${evt.stem}: riduzione rumore`);
      markStemStage(evt.stem, "denoise");
      setListening(true);
      setTimeout(() => setListening(false), 1200);
      break;

    case "elastic_align":
      addEventChip(`\u{1F9F5} ${evt.stem}: allineamento elastico ${evt.windows_stretched}/${evt.windows_total}`);
      break;

    case "depth_stage": {
      const depthIcon = { foreground: "\u{1F3AF}", midground: "\u{1F538}", background: "\u{1F30C}" }[evt.depth] || "\u{1F3AF}";
      const depthLabel = { foreground: "primo piano", midground: "centro", background: "sfondo" }[evt.depth] || evt.depth;
      addEventChip(`${depthIcon} ${evt.stem}: ${depthLabel}`);
      break;
    }

    case "role_correction":
      addEventChip(`\u{26A0}\u{FE0F} ${evt.stem}: ${evt.from} -> ${evt.to}`);
      break;

    case "auto_pan": {
      const side = evt.pan < 0 ? "sx" : "dx";
      addEventChip(`\u{1F3A7} ${evt.stem}: pan ${side} ${Math.abs(evt.pan * 100).toFixed(0)}%`);
      break;
    }

    case "spectral_duck":
      addEventChip(`\u{1F507} Ducking spettrale ${evt.band_low_hz}-${evt.band_high_hz}Hz (${evt.amount_db}dB)`);
      break;

    case "loudness_gain":
      addEventChip(`\u{1F50A} ${evt.current_lufs} LUFS -> ${evt.target_lufs} LUFS (${evt.gain_db}dB)`);
      updateVuMeter(evt.target_lufs, `${evt.current_lufs} -> ${evt.target_lufs} LUFS`);
      break;

    case "soft_clip":
      addEventChip(`\u{2702}\u{FE0F} Soft clip a ${evt.ceiling_db}dB`);
      flashDetail("master-detail", `Soft clip: ceiling ${evt.ceiling_db}dB`);
      break;

    case "mid_side":
      addEventChip(`\u{2194}\u{FE0F} M/S: mono sotto ${evt.mono_below_hz}Hz`);
      flashDetail("midside-detail", `Mono < ${evt.mono_below_hz}Hz, air shelf side`);
      break;

    case "limiter":
      addEventChip(`\u{1F6A7} Limiter a ${evt.ceiling_db}dB`);
      flashDetail("master-detail", `Limiter: ceiling ${evt.ceiling_db}dB`);
      break;

    case "qc_report": {
      if (window.avatarAPI) window.avatarAPI.onListening(true);
      setTimeout(() => { if (window.avatarAPI) window.avatarAPI.onListening(false); }, 2500);
      const hp = document.getElementById("headphones");
      hp.classList.add("active");
      setTimeout(() => hp.classList.remove("active"), 2500);
      flashDetail(
        "qc-detail",
        `${evt.lufs} LUFS, peak ${evt.true_peak_db}dB, mono ${evt.mono_compatibility} — ${evt.passed ? "OK" : "corretto"}`
      );
      updateVuMeter(evt.lufs, `${evt.lufs} LUFS (QC)`);
      setAssistantLabel(evt.passed ? "tutto ok" : "corretto");
      break;
    }

    case "register_classified":
      addEventChip(`\u{1F3B5} ${evt.stem}: ${evt.fundamental_hz}Hz -> ${evt.register}`);
      markStemStage(evt.stem, "register");
      break;

    case "backing_vocals_bus":
      addEventChip(`\u{1F465} Bus voci di supporto: ${evt.registers.join(", ")}`);
      break;

    case "kick_bass_sidechain":
      addEventChip(`\u{1F941} Sidechain kick/basso ${evt.amount_db}dB`);
      break;

    case "masking_cut":
      addEventChip(`\u{1F3B8} ${evt.stem}: mascheramento a ${evt.freq_hz}Hz (${evt.gain_db}dB)`);
      markStemStage(evt.stem, "masking");
      _routeStemEvent(evt);
      break;

    case "midrange_masking_cut":
      addEventChip(`\u{1FA98} ${evt.stem}: accumulo medio a ${evt.freq_hz}Hz (${evt.gain_db}dB)`);
      markStemStage(evt.stem, "masking");
      _routeStemEvent(evt);
      break;

    case "music_bus_ms":
      addEventChip(`\u{1F3B9} Bus musicale M/S: buco ${evt.mid_dip_db}dB`);
      break;

    case "multiband_compressor":
      addEventChip(`\u{1F39B}\u{FE0F} Multibanda: <${evt.low_hz}Hz / ${evt.low_hz}-${evt.high_hz}Hz / >${evt.high_hz}Hz`);
      reactToGlueCompression(evt.recipes.mid.ratio);
      flashDetail("master-detail", `Multibanda: 3 bande, split ${evt.low_hz}/${evt.high_hz}Hz`);
      break;

    case "vocal_space":
      addEventChip(`\u{1F30C} Spazio voce: riverbero+delay ${Math.round(evt.mix * 100)}%`);
      syncAssistantToBpm(evt.bpm);
      // Bus-level (not tied to any one stem) -- don't stomp on a pinned
      // per-stem channel strip's own reverb-send reading.
      if (!_rackPinned) flashDetail("reverb-detail", `Voce: riverbero+delay BPM-sync ${Math.round(evt.mix * 100)}%`);
      break;

    case "concurrent_take_leveling":
      addEventChip(`\u{2696}\u{FE0F} Bilanciamento prese multiple: ${evt.stems.length} tracce`);
      break;

    case "saturation":
      addEventChip(`\u{1F525} ${evt.stem}: saturazione (drive ${evt.drive})`);
      _routeStemEvent(evt);
      flashDetail("saturation-detail", `${evt.stem}: drive ${evt.drive}`);
      markStemStage(evt.stem, "saturation");
      if (window.avatarAPI) window.avatarAPI.onSaturation(evt.drive);
      break;

    case "reverb_send":
      addEventChip(`\u{2601}\u{FE0F} ${evt.stem}: riverbero lungo ${Math.round(evt.mix * 100)}%`);
      _routeStemEvent(evt);
      flashDetail("reverb-detail", `${evt.stem}: send ${evt.bus} ${Math.round(evt.mix * 100)}%`);
      markStemStage(evt.stem, "reverb");
      break;

    case "reverb_bus_render":
      addEventChip(`\u{1F3DB}\u{FE0F} Bus riverbero renderizzati: ${evt.buses.join(", ")}`);
      // Bus-level (not tied to any one stem) -- don't stomp on a pinned
      // per-stem channel strip's own reverb-send reading.
      if (!_rackPinned) flashDetail("reverb-detail", `Bus renderizzati: ${evt.buses.join(", ")}`);
      break;

    case "ltas_match":
      addEventChip(`\u{1F3A7} Matchering FIR: delta entro ±${evt.max_delta_db}dB (${evt.fir_taps} tap)`);
      setListening(true);
      setTimeout(() => setListening(false), 2000);
      break;

    case "rt60_calibration":
      addEventChip(`\u{1F3DB}\u{FE0F} RT60 dalla reference: ${evt.rt60_seconds}s`);
      setListening(true);
      setTimeout(() => setListening(false), 2000);
      break;

    case "llm_advisory_start":
      startDeepScan(evt.stem_count);
      break;

    case "llm_token":
      appendLlmToken(evt.text);
      break;

    case "llm_advisory_done":
      stopDeepScan();
      break;

    case "llm_reclassification":
      addEventChip(`\u{1F9E0} ${evt.stem}: LLM -> ${evt.category} (${evt.role})`);
      break;

    case "director_checkpoint":
      if (evt.checkpoint === "instrument_questions") {
        showInstrumentQuestions(evt);
      } else {
        showDirectorCheckpoint(evt);
      }
      break;

    case "done":
      if (window.avatarAPI) window.avatarAPI.onDone();
      setAssistantLabel("fatto!");
      break;

    case "system_ready": {
      if (window.avatarAPI) window.avatarAPI.onSystemReady();
      setAssistantLabel("pronto");
      addEventChip("\u2705 Sistema pronto — bridge Python attivo");
      break;
    }

    case "vocal_main_bus":
      addEventChip(`\u{1F3A4} Bus Vocal_Main: ${evt.stems.length} tracce sommate`);
      break;

    case "bass_chain":
      addEventChip(`\u{1F3B8} Basso: split 2-banda + saturazione armonica`);
      flashDetail("saturation-detail", `Basso: split 2-banda + saturazione armonica`);
      break;

    case "stereo_widen":
      addEventChip(`\u{2194}\u{FE0F} Stereo widening: width=${evt.width}`);
      flashDetail("midside-detail", `Stereo width: ${evt.width}`);
      break;

    case "transient_shaper":
      addEventChip(`\u{26A1} Transient shaper: attack=${evt.attack_gain_db}dB, sustain=${evt.sustain_gain_db}dB`);
      flashDetail("comp-detail", `Transient: attack ${evt.attack_gain_db}dB / sustain ${evt.sustain_gain_db}dB`);
      break;

    default:
      // Every backend event is meant to be seen -- a silently dropped case
      // here is exactly why effects the engine actually uses (reverb,
      // saturation, limiter, bus glue...) could look "missing" to someone
      // watching the log, when they were really just never rendered. Any
      // event type without a specific case above still gets a generic chip
      // instead of vanishing.
      if (evt && evt.type) {
        addEventChip(`⚙️ ${evt.type}`);
      }
      break;
  }
}

// Initialize Three.js avatar when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    initThreeAvatar();
    loadPresets();
  });
} else {
  initThreeAvatar();
  loadPresets();
}

function initThreeAvatar() {
  if (window.avatarAPI && document.getElementById('fx-canvas')) {
    window.avatarAPI.init('fx-canvas');
  }
}

// --- Keyboard shortcuts: Space=play/pause (Neural Monitor toggle),
// Ctrl+S=save preset (wizard screen only), Escape=close checkpoint panels,
// Ctrl+Z/Ctrl+Shift+Z=undo/redo (see undoLastChange/redoLastChange below).
// Ignored while typing in a text field so shortcuts don't fight normal
// editing (space in a textarea, browser-native Ctrl+Z in a text input).
document.addEventListener("keydown", (e) => {
  const tag = document.activeElement?.tagName;
  const isTyping = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";

  if (e.key === "Escape") {
    document.getElementById("director-panel")?.classList.add("hidden");
    document.getElementById("instrument-questions-panel")?.classList.add("hidden");
    return;
  }

  if (isTyping) return;

  if (e.key === " ") {
    const switchEl = document.getElementById("audition-switch");
    if (switchEl) {
      e.preventDefault();
      switchEl.checked = !switchEl.checked;
      toggleAudition();
    }
    return;
  }

  if (e.ctrlKey && !e.shiftKey && e.key.toLowerCase() === "s") {
    if (document.getElementById("screen-wizard")?.classList.contains("active")) {
      e.preventDefault();
      saveCurrentPreset();
    }
    return;
  }

  if (e.ctrlKey && !e.shiftKey && e.key.toLowerCase() === "z") {
    e.preventDefault();
    if (typeof undoLastChange === "function") undoLastChange();
    return;
  }

  if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === "z") {
    e.preventDefault();
    if (typeof redoLastChange === "function") redoLastChange();
    return;
  }

  // Easter egg: Ctrl+Alt+R ("RedLine") draws a Lissajous curve over the
  // avatar for a few seconds -- purely decorative, no functional purpose.
  if (e.ctrlKey && e.altKey && e.key.toLowerCase() === "r") {
    e.preventDefault();
    if (window.avatarAPI) window.avatarAPI.onEasterEgg();
    return;
  }
});

// Wire preset dropdown change event (delegated so it works even if the
// dropdown is populated after DOMContentLoaded).
document.addEventListener("change", (e) => {
  if (e.target.id === "preset-select") {
    onPresetSelect(e.target.value);
  }
});
