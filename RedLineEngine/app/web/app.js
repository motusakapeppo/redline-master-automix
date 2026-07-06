let selectedInput = null;
let selectedOutput = null;

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

  if (typeof gsap === "undefined") {
    // GSAP failed to load (vendored file missing/corrupt) -- the screen
    // switch itself must never depend on it, only the transition's polish does.
    document.querySelectorAll(".screen").forEach((el) => el.classList.remove("active"));
    next.classList.add("active");
    return;
  }

  if (current) {
    gsap.to(current, {
      opacity: 0, x: -16, duration: 0.25, ease: "power1.in",
      onComplete: () => current.classList.remove("active"),
    });
  }
  next.classList.add("active");
  gsap.fromTo(next, { opacity: 0, x: 16 }, { opacity: 1, x: 0, duration: 0.35, delay: current ? 0.15 : 0, ease: "power2.out" });
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
  document.getElementById("event-feed").innerHTML = "";
  document.getElementById("spinner").classList.remove("hidden");
  document.getElementById("result").classList.add("hidden");
  document.getElementById("result").innerHTML = "";
  eqBands = {};
  redrawEq();
  setAssistantLabel("al lavoro...");

  const prefs = {
    aggressiveness: parseInt(document.getElementById("aggressiveness").value, 10),
    warmth: parseFloat(document.getElementById("warmth").value),
    vocal_prominence: parseFloat(document.getElementById("vocal_prominence").value),
    genre_override: document.getElementById("genre_override").value,
    do_mastering: document.getElementById("do_mastering").checked,
    platform: document.getElementById("platform").value,
  };

  const result = await window.pywebview.api.run_pipeline(selectedInput, prefs, selectedOutput);
  onDone(result);
}

function onStep(msg) {
  const log = document.getElementById("log");
  const line = document.createElement("div");
  line.className = "log-line";
  line.textContent = msg;
  log.appendChild(line);
  log.scrollTop = log.scrollHeight;
  if (window.avatarAPI) window.avatarAPI.onStep(msg);
  bumpActivity();
  wireInteractiveLine(line, msg);
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
  if (!rack) return;
  rack.classList.remove("glitch");
  void rack.offsetWidth;
  rack.classList.add("glitch");
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
  if (console_) {
    console_.textContent = "";
    console_.classList.add("active");
  }
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

function onDone(result) {
  document.getElementById("spinner").classList.add("hidden");
  const resultEl = document.getElementById("result");
  resultEl.classList.remove("hidden");

  if (result && result.ok) {
    resultEl.innerHTML = `
      <div class="result-card">
        <div class="result-title">Fatto</div>
        <div>Genere: ${result.genre} &middot; BPM: ${result.bpm.toFixed(1)} &middot; Tonalit&agrave;: ${result.key}</div>
        <div>Loudness: ${result.lufs.toFixed(1)} LUFS</div>
        <button class="btn btn-accent" onclick="openOutput()">Apri cartella risultati</button>
      </div>`;
  } else {
    const errorMsg = result ? result.error : "errore sconosciuto";
    resultEl.innerHTML = `<div class="result-card error">Errore: ${errorMsg}</div>`;
  }
}

function openOutput() {
  window.pywebview.api.open_folder(selectedOutput);
}

// --- Director Mode: the pipeline is genuinely paused on a Python thread
// (threading.Event) waiting for this exact button click -- nothing here is
// simulated, approveDirectorCheckpoint() really does unblock render_mix().
function showDirectorCheckpoint(evt) {
  const panel = document.getElementById("director-panel");
  const list = document.getElementById("director-stems");
  if (!panel || !list) return;

  const roleIcons = { vocal: "\u{1F3A4}", bass: "\u{1F3B8}", drums: "\u{1F941}", other: "\u{1F3B9}" };
  list.innerHTML = evt.stems
    .map((s) => {
      const icon = roleIcons[s.role] || "\u{2753}";
      const detail = [s.role, s.layer !== "primary" ? s.layer : null, s.register].filter(Boolean).join(" / ");
      return `<div class="director-stem-row">${icon} <strong>${s.name}</strong> &mdash; ${detail}</div>`;
    })
    .join("");

  panel.classList.remove("hidden");
  setAssistantLabel("in attesa di conferma");
}

function approveDirectorCheckpoint() {
  const panel = document.getElementById("director-panel");
  if (panel) panel.classList.add("hidden");
  if (window.pywebview) {
    window.pywebview.api.approve_director_checkpoint();
  }
}

// --- Animated "studio rack": every visual here reacts to a real value the
// engine just computed (an actual EQ freq/gain, a real compressor ratio, a
// real de-esser band, a real QC measurement) — not a generic looping
// animation. onEvent() is called by app/api.py's _emit(), fed straight from
// the on_event callbacks threaded through mixengine.py/masterengine.py.

let eqBands = {}; // key -> {freq, gain} — accumulates the bus EQ shape as it's built

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

function flashDetail(id, text) {
  const el = document.getElementById(id);
  el.textContent = text;
  el.classList.add("flash");
  setTimeout(() => el.classList.remove("flash"), 400);
}

function addEventChip(text) {
  const feed = document.getElementById("event-feed");
  const chip = document.createElement("div");
  chip.className = "event-chip";
  chip.textContent = text;
  feed.appendChild(chip);
  feed.scrollTop = feed.scrollHeight;
  // keep the feed from growing unbounded during a long render
  while (feed.children.length > 40) feed.removeChild(feed.firstChild);
}

function onEvent(evt) {
  bumpActivity();
  switch (evt.type) {
    case "bus_eq_band":
      eqBands[`bus_${evt.freq_hz}`] = { freq: evt.freq_hz, gain_db: evt.gain_db };
      redrawEq();
      flashDetail("eq-detail", `Bus: ${evt.freq_hz}Hz ${evt.gain_db > 0 ? "+" : ""}${evt.gain_db}dB`);
      break;

    case "resonance_cut":
      eqBands[`res_${evt.stem}`] = { freq: evt.freq_hz, gain_db: evt.gain_db };
      redrawEq();
      flashDetail("eq-detail", `${evt.stem}: risonanza ${evt.freq_hz.toFixed(0)}Hz ${evt.gain_db}dB`);
      break;

    case "dynamic_hpf":
      flashDetail("eq-detail", `${evt.stem}: HPF dinamico ${evt.cutoff_hz}Hz (fondamentale ${evt.fundamental_hz}Hz)`);
      addEventChip(`\u{1F3A4} ${evt.stem}: taglio adattivo a ${evt.cutoff_hz}Hz`);
      break;

    case "compressor":
    case "bus_compressor": {
      const ratio = evt.ratio;
      const pct = Math.min(100, (ratio - 1) * 14);
      const fill = document.getElementById("gr-fill");
      fill.style.width = `${pct}%`;
      const label = evt.stem ? evt.stem : "bus";
      flashDetail("comp-detail", `${label}: ${ratio.toFixed(1)}:1 @ ${evt.threshold_db}dB`);
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
      const center = Math.round((evt.low_hz + evt.high_hz) / 2);
      const dial = document.getElementById("deess-dial");
      dial.textContent = `${(center / 1000).toFixed(1)}kHz`;
      dial.classList.remove("pulse");
      void dial.offsetWidth; // restart animation
      dial.classList.add("pulse");
      flashDetail("deess-detail", `${evt.stem}: banda ${evt.low_hz.toFixed(0)}-${evt.high_hz.toFixed(0)}Hz`);
      reactToDeesser();
      break;
    }

    case "time_align":
      addEventChip(`\u{23F1}\u{FE0F} ${evt.stem} allineata (${evt.delay_ms > 0 ? "+" : ""}${evt.delay_ms}ms)`);
      break;

    case "denoise":
      addEventChip(`\u{1F9FC} ${evt.stem}: riduzione rumore`);
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

    case "spectral_duck":
      addEventChip(`\u{1F507} Ducking spettrale ${evt.band_low_hz}-${evt.band_high_hz}Hz (${evt.amount_db}dB)`);
      break;

    case "loudness_gain":
      addEventChip(`\u{1F50A} ${evt.current_lufs} LUFS -> ${evt.target_lufs} LUFS (${evt.gain_db}dB)`);
      break;

    case "soft_clip":
      addEventChip(`\u{2702}\u{FE0F} Soft clip a ${evt.ceiling_db}dB`);
      break;

    case "mid_side":
      addEventChip(`\u{2194}\u{FE0F} M/S: mono sotto ${evt.mono_below_hz}Hz`);
      break;

    case "limiter":
      addEventChip(`\u{1F6A7} Limiter a ${evt.ceiling_db}dB`);
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
      setAssistantLabel(evt.passed ? "tutto ok" : "corretto");
      break;
    }

    case "register_classified":
      addEventChip(`\u{1F3B5} ${evt.stem}: ${evt.fundamental_hz}Hz -> ${evt.register}`);
      break;

    case "backing_vocals_bus":
      addEventChip(`\u{1F465} Bus voci di supporto: ${evt.registers.join(", ")}`);
      break;

    case "kick_bass_sidechain":
      addEventChip(`\u{1F941} Sidechain kick/basso ${evt.amount_db}dB`);
      break;

    case "masking_cut":
      addEventChip(`\u{1F3B8} ${evt.stem}: mascheramento a ${evt.freq_hz}Hz (${evt.gain_db}dB)`);
      break;

    case "music_bus_ms":
      addEventChip(`\u{1F3B9} Bus musicale M/S: buco ${evt.mid_dip_db}dB`);
      break;

    case "multiband_compressor":
      addEventChip(`\u{1F39B}\u{FE0F} Multibanda: <${evt.low_hz}Hz / ${evt.low_hz}-${evt.high_hz}Hz / >${evt.high_hz}Hz`);
      reactToGlueCompression(evt.recipes.mid.ratio);
      break;

    case "vocal_space":
      addEventChip(`\u{1F30C} Spazio voce: riverbero+delay ${Math.round(evt.mix * 100)}%`);
      syncAssistantToBpm(evt.bpm);
      break;

    case "concurrent_take_leveling":
      addEventChip(`\u{2696}\u{FE0F} Bilanciamento prese multiple: ${evt.stems.length} tracce`);
      break;

    case "saturation":
      addEventChip(`\u{1F525} ${evt.stem}: saturazione (drive ${evt.drive})`);
      break;

    case "reverb_send":
      addEventChip(`\u{2601}\u{FE0F} ${evt.stem}: riverbero lungo ${Math.round(evt.mix * 100)}%`);
      break;

    case "reverb_bus_render":
      addEventChip(`\u{1F3DB}\u{FE0F} Bus riverbero renderizzati: ${evt.buses.join(", ")}`);
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
      showDirectorCheckpoint(evt);
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

    default:
      break;
  }
}

// Initialize Three.js avatar when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initThreeAvatar);
} else {
  initThreeAvatar();
}

function initThreeAvatar() {
  if (window.avatarAPI && document.getElementById('fx-canvas')) {
    window.avatarAPI.init('fx-canvas');
  }
}
