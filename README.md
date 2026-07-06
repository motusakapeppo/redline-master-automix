# RedLine Engine

> **Automatic mixing & mastering engine** — professional-grade DSP pipeline for multitrack audio, with a pywebview desktop GUI and a real-time animated avatar that reacts to every compressor hit, de-esser flash, and BPM change.

---

## English 🇬🇧

### Overview

RedLine Engine is a standalone automatic mixing and mastering system. It ingests raw multitrack stems (or a single mixed file), classifies each stem by role, register, and spatial depth, applies a full DSP mixing chain with per-stem processing, then masters the final bounce to a loudness target or a reference track.

The entire pipeline is **measurement-driven**: every EQ cut, compression ratio, and reverb amount is computed from actual audio measurements (fundamental frequency, crest factor, spectral centroid, RMS energy), not from static presets. The system adapts to the material, not the other way around.

**Key design principles:**
- **The lead vocal is the star** — full-range, centered, presence-boosted, minimally processed. Doubles and harmonies support at 50% level (-6dB) so the lead never loses presence.
- **Main/Lead vocals are the timing grid** — never warped by elastic alignment, never attenuated by level compensation.
- **Safety over cleverness** — every experimental module is off by default behind feature flags. Disabling a flag is a complete, instant rollback.
- **Measured, not guessed** — all DSP parameters are computed from real audio measurements, not static presets.
- **Fail-safe by design** — every module is wrapped in try-except. A missing audio device, a failed LLM inference, or a librosa error never takes down the render.

### Project Structure

```
RedLineEngine/
├── app/                          # Desktop GUI (pywebview)
│   ├── main.py                   # Entry point — creates window, loads UI
│   ├── api.py                    # Python↔JS bridge (file picker, pipeline control, events)
│   └── web/                      # Frontend (HTML/CSS/JS)
│       ├── index.html            # Two-column layout
│       ├── app.js                # GSAP UI animations, avatar event wiring
│       ├── three-avatar.js       # 3D rigged skull avatar (Three.js, AnimationMixer)
│       ├── style.css             # Dark industrial theme
│       ├── assets/               # skull.glb + staged instrument/prop models (not all wired up)
│       └── vendor/               # Self-hosted, fully offline (no CDN dependency)
│           ├── gsap.min.js       # GreenSock Animation Platform
│           └── three/            # Three.js core + GLTFLoader + postprocessing modules
├── redline/                      # Core DSP engine
│   ├── naming.py                 # Regex stem role/pan/section detection
│   ├── analyze.py                # pYIN pitch, VAD-gated analysis, genre detection
│   ├── analysis/                 # Spectral profiling sub-modules
│   ├── depth.py                  # Z-axis classification (foreground/mid/background)
│   ├── mixengine.py              # Per-stem DSP chain (the heart of the mix)
│   ├── masterengine.py           # Multiband glue, limiting, LUFS targeting, QC loop
│   ├── elastic_align.py          # DTW syllable alignment for doubles (2% max warp)
│   ├── leveling.py               # Power-preserving gain compensation (skips Main/Lead)
│   ├── alignment.py              # Cross-correlation sample-precise alignment
│   ├── deesser.py                # Multiband 4-8kHz de-esser
│   ├── resonance.py              # Adaptive mud-range resonance suppression
│   ├── masking.py                # Preventive spectral masking cuts
│   ├── denoise.py                # Spectral noise reduction (first in chain)
│   ├── reverbbus.py              # 3 shared reverb buses (Room/Plate/Hall)
│   ├── fxsends.py                # Genre-aware reverb/delay send amounts
│   ├── vocalstack.py             # Register classification + per-register processing
│   ├── ltas.py                   # Long-Term Average Spectrum matching (FIR, ±2.5dB)
│   ├── rt60.py                   # Onset+decay regression for reverb calibration
│   ├── qc.py                     # True-peak/LUFS/mono-compatibility check
│   ├── audition.py               # Neural Monitor — live A/B playback
│   ├── llm_classifier.py         # Local LLM (Qwen 2.5 1.5B) for stem classification
│   ├── director_safety.py        # LLM output validator/clamp
│   ├── director.py               # threading.Event gate for GUI approval
│   ├── config.py                 # Feature flag system
│   ├── metrics.py                # Per-stage timing instrumentation
│   └── dsp_utils.py              # Shared utilities (envelope follower, duck curves, etc.)
├── tests/                        # Verification & validation
│   ├── verify_gain.py            # Gain staging synthetic test
│   ├── latency_test.py           # DSP→UI bridge round-trip measurement
│   └── check_monitor.py          # Audio hardware + flag status check
├── ci_validate.py                # CI quality gate (runs verify_gain.py, auto-enables flags)
├── DSP_ENGINE_SPECS.md           # Ground-truth numeric rulebook
├── requirements.txt              # Python dependencies
├── .flags.json                   # Local feature flags (gitignored, machine-local)
└── README.md                     # This file
```

### Quick Start

```bash
# 1. Create a virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate     # Windows
source .venv/bin/activate  # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the desktop app
python app/main.py

# 4. Or run headless (CLI mode)
python -m redline.cli --input /path/to/stems --output /path/to/out

# 5. Enable experimental features
echo '{"ENABLE_BLUEPRINT_CHAINS": true}' > .flags.json

# 6. Debug GUI (opens Chrome DevTools alongside the window)
REDLINE_DEBUG_GUI=1 python app/main.py
```

### Configuration: Feature Flags

Every experimental module is **off by default**. Flags are stored in `redline/config.py` and can be toggled via:

1. **`.flags.json`** (gitignored, machine-local) — persists across sessions:
   ```json
   { "ENABLE_BLUEPRINT_CHAINS": true, "ENABLE_LIVE_AUDITION": true }
   ```
2. **Environment variables** — override `.flags.json` for one-off runs:
   ```bash
   REDLINE_BLUEPRINT_CHAINS=1 REDLINE_LIVE_AUDITION=1 python app/main.py
   ```
3. **CI auto-enable** — `ci_validate.py` enables all flags automatically on PASS.

| Flag | Default | What it unlocks |
|---|---|---|
| `ENABLE_BLUEPRINT_CHAINS` | off | Serial vocal compression (FET peak-catcher + Opto leveler), drum bus glue + tape saturation, bass 2-band split + harmonic exciter |
| `ENABLE_LTAS_MATCHING` | off | FIR spectral matching (`redline/ltas.py`) against a reference track during mastering |
| `ENABLE_RT60_CALIBRATION` | off | Auto-tunes Room/Plate reverb bus decay from a reference track's onset/decay analysis (`redline/rt60.py`) |
| `ENABLE_LLM_ADVISORY` | off | Local LLM (llama.cpp, `redline/llm_classifier.py`) fallback for low-confidence stem naming, validated through `redline/director_safety.py` |
| `ENABLE_LIVE_AUDITION` | off | Neural Monitor — real dry/wet A/B playback of the master bus glue compression through your speakers (`redline/audition.py`). Toggled live from the GUI switch |
| `ENABLE_DIRECTOR_MODE` | off | Pauses `render_mix` after stem role/register recognition and waits for GUI approval (`redline/director.py`) before any DSP runs |

### Creative Brief (free-text → LLM interpretation)

The wizard screen has a free-text field at the top: "describe in plain, non-technical language what you'd like different about the mix" (e.g. *"I'd like it to sound warmer, almost like vinyl, and the vocal a bit more upfront"*). Left blank, it means exactly that — no special requests, use the sliders below as-is.

If filled in, `app/api.py` passes the text to `redline/llm_classifier.interpret_creative_brief()`, which prompts the local model to translate it into small nudges on exactly the **3 existing wizard knobs** — `aggressiveness`, `warmth`, `vocal_prominence` — never raw DSP parameters. Every value still passes through `redline/director_safety.clamp_params()` (same ranges as the sliders themselves) before it can reach `MixPreferences`, so an over-eager interpretation ("make it sound like a monster") can only nudge within the range a human moving the sliders could already reach — it can never exceed it. Falls back to the slider values untouched if the brief is blank, the local model isn't available, or its response doesn't parse as valid JSON.

### Architecture

#### Core DSP (`redline/`)

| Module | What it does |
|---|---|
| `naming.py` | Regex-based stem role, pan, and section detection from file names. Recognizes patterns like `vocal_main`, `lead_vox`, `bass_di`, `kick_in`, `snare_top`, `hihat`, `overhead`, `room`, `fx_reverb` etc. |
| `analyze.py` + `analysis/` | pYIN pitch estimation, VAD-gated analysis (voice activity detection gates the analysis to only measure when the vocal is actually singing), genre detection from tempo/spectral features, spectral profiling (centroid, rolloff, flux, crest factor per band). |
| `depth.py` | Z-axis classification (foreground / midground / background) via Crest Factor + spectral flux. Foreground = high crest + high flux (transient-rich, close-mic'd). Background = low crest + low flux (ambient, room mics). |
| `mixengine.py` | **The heart of the mix.** Per-stem DSP chain: adaptive HPF tracking the vocal's measured fundamental, resonance suppression, role-specific compression with automatic makeup gain, de-essing, spatial depth staging. Creates separate Vocal_Main and Vocal_Doubles buses (doubles at 50% level). Spectral ducking (1-4kHz band pulled back in instruments when vocal is active), kick/bass sidechain, Mid/Side music bus, parallel NY compression. |
| `masterengine.py` | Multiband glue compression (low/mid/high split with independent thresholds), soft-clip limiting, mid/side polish (widens stereo image in the high band), LUFS targeting per platform (Spotify -14dB, YouTube -13dB, Apple Music -16dB), automated QC loop with correction re-render. |
| `elastic_align.py` | Syllable-level DTW (Dynamic Time Warping) time alignment for vocal doubles. **Main/Lead vocals are never warped** (name-based guard). Max safe warp limited to **2%** — if DTW needs more stretch, the window is skipped entirely to prevent flutter artifacts. Energy-based guard: if the "lead" signal has less than 60% of the double's RMS energy, the function bails out (likely swapped arguments). |
| `leveling.py` | Power-preserving gain compensation (1/√N) for overlapping vocal takes. **Skips Main/Lead vocals** — only applied to doubles/adlibs. Prevents the "too many takes" problem where summing N identical takes gives √N amplitude increase. |
| `alignment.py` | Cross-correlation sample-precise alignment of doubles to the lead reference. Finds the sample offset that maximizes correlation, then shifts the double signal. |
| `deesser.py` | Multiband de-esser (4-8kHz) with adaptive threshold per register. Low register = lower threshold (less sibilance energy), High/Falsetto = higher threshold (more sibilance is natural). Uses spectral envelope estimation to distinguish sibilance from actual vocal content. |
| `resonance.py` | Adaptive resonance detection and suppression in the mud range (100-400Hz). Finds spectral peaks that persist across multiple frames (resonances, not notes) and applies narrow notch filters. |
| `masking.py` | Preventive masking cut: measures spectral overlap between instruments and the vocal's presence band (2-5kHz). If an instrument occupies >30% of the vocal's presence band, a gentle cut is applied to that instrument. |
| `denoise.py` | Spectral noise reduction applied **before** any other DSP (so compression/EQ don't raise the noise floor). Uses spectral gating: estimates noise floor from silent passages, then subtracts it from the full signal. |
| `reverbbus.py` | 3 shared reverb buses (Room / Plate / Hall) instead of per-stem instances — saves CPU and creates a cohesive space where all instruments share the same reverb tail. Each bus has independent decay, pre-delay, and damping. |
| `fxsends.py` | Genre-aware reverb/delay send amounts, BPM-synced delay (quarter/eighth/dotted-eighth note divisions), drum room send (snare gets more room than kick). |
| `vocalstack.py` | Register classification (Low / Unison / High / Falsetto) with per-register processing recipes — a wall of doubles reads as one big, defined thing. Low register gets more body, Falsetto gets more air. |
| `ltas.py` | Long-Term Average Spectrum matching via FIR filter, ±2.5dB clamped. Analyzes the spectrum of a reference track and applies a corrective FIR filter so the master's average spectrum matches the reference. |
| `rt60.py` | Onset + decay regression to estimate RT60 from a reference track. Detects transient onsets, measures their decay slope, and computes the time for -60dB drop. Used to calibrate reverb bus decay times. |
| `qc.py` | True-peak / LUFS / mono-compatibility check with automatic correction re-render. If LUFS is off by more than 0.5dB, the master is re-rendered with adjusted makeup gain. If mono compatibility is below -6dB correlation, a Mid/Side adjustment is applied. |
| `audition.py` | **Neural Monitor** — live A/B playback through real speakers via sounddevice/PortAudio. Uses `sd.OutputStream(blocksize=512, latency='low')` for low-latency playback. Peak-safety normalization (hard ceiling at -1dBFS), anti-click fade in/out (5ms cosine fades), makeup gain for quiet signals (target peak 0.85). Toggleable live from the GUI. |
| `llm_classifier.py` | Offline local LLM (Qwen 2.5 1.5B, GGUF quantized, ~1GB) for ambiguous stem classification. Falls back from regex when naming confidence is below threshold. Streams tokens live to the GUI console. Runs entirely locally — no internet connection needed. |
| `director_safety.py` | Validates and clamps any LLM-suggested value before it reaches the engine. Prevents the LLM from suggesting out-of-range compression ratios, impossible EQ curves, or dangerous gain values. |
| `director.py` | `threading.Event`-based gate that pauses `render_mix` for GUI approval mid-pipeline. After stem role/register recognition, the pipeline blocks until the user clicks "Approve" or "Adjust" in the GUI. |
| `config.py` | Feature flag system with `.flags.json` + environment variable overrides. Reads flags on startup, watches for file changes (future: hot-reload). |
| `metrics.py` | In-memory per-stage timing instrumentation. Logs `[METRIC] stage: Xs` for every pipeline stage. Used for performance profiling and regression detection. |
| `dsp_utils.py` | Shared DSP utilities: envelope follower (RMS with configurable window), duck gain curves (linear/exponential), band gain curves, saturation (soft-clip/tanh), panning (equal-power), Mid/Side encoding/decoding. |

#### GUI (`app/`)

| Module | What it does |
|---|---|
| `main.py` | pywebview desktop entry point. Creates the window (1280x800, dark theme), loads the web UI from `web/index.html`, writes a load-confirmation marker to `%LOCALAPPDATA%\RedLineEngine\last_load.log` for black-window diagnostics. Calls `api.system_ready()` when the page finishes loading. |
| `api.py` | Thin Python↔JS bridge. Exposes to JavaScript: `pick_input_path()` (folder picker), `pick_input_file()` (single audio file), `run_pipeline()` (starts the mix), `toggle_neural_monitor()` (live A/B switch), `approve_director_checkpoint()` (Director Mode approval). Also manages the **async JS eval queue** — a background thread drains `queue.Queue` calls so the DSP pipeline never blocks on UI updates. 60fps throttle (16.7ms minimum interval) with stale entry draining (if a newer event supersedes an older one, the old one is dropped). |
| `web/index.html` | Two-column layout: workflow screens (file pick, pipeline progress, QC results) on the left, avatar + terminal console on the right. |
| `web/app.js` | GSAP-driven animations. Handles all `onEvent()` cases: de-esser → nose piercing flash, glue compression → earring jingle, BPM → headbang, LLM inference → glasses glow ("deep scan"), system_ready → 3-pulse power-on glow, director_checkpoint → approval dialog, QC results → canvas visualization. |
| `web/style.css` | Dark industrial theme (#0A0A0A background, #FF003F accent red, #1A1A1A panel surfaces). Rack module styling, terminal panel with monospace font, glitch animations, cylon bar (scanning LED strip). |
| `web/vendor/gsap.min.js` | Vendored GreenSock Animation Platform (~40KB minified). Provides smooth, performant 60fps animations without jQuery. |

#### Avatar System

The avatar is a real 3D rigged character (`app/web/assets/skull.glb`, a CC0 asset), rendered with a self-hosted, fully offline copy of Three.js (`app/web/vendor/three/` — no CDN dependency, matters for the packaged exe) and driven by `app/web/three-avatar.js`. It replaced an earlier flat SVG wireframe design.

The model ships with baked animation clips played through a `THREE.AnimationMixer` — real skeletal animation, not faked bone-rotation math:

| Clip | Trigger |
|---|---|
| `Idle` | Default state, loops continuously |
| `Bite_Front` | De-esser firing (a quick "snap") |
| `Bite_InPlace` (looping) | LLM inference ("deep scan") |
| `HitRecieve` | Strong glue compression hit |
| `Dance` | Pipeline completion |
| `Yes` / `No` | Director Mode approve / reject |

On top of the clip playback, the render loop adds:
- **Natural intermittent glances** — a hold/turn state machine (not a constant slow spin, which was an actual bug: a leftover `rotation.y +=` accumulator from a since-removed reactive ring). Holds still for 1.5–5s, then snaps a smoothstep-eased glance (0.6–1.1s) to a new random angle, the way a real head moves rather than a lighthouse beacon.
- **Eye-glow markers** (small emissive red spheres, position-derived from the model's own bounding box) that flash on de-esser hits.
- **Material**: the model's own painted texture is kept (not discarded for a flat color) and tinted a cool silver-grey to match the black/red/silver theme, rendered with a transparent background (no visible rectangle behind it) and no bloom post-processing (bloom reliably broke canvas alpha and blew every material to solid white).

Several more assets are staged in `app/web/assets/` for planned features, not yet wired up:
- `headphones.glb`, `vinyl.glb` — a "headphones pop on" moment for Neural Monitor toggle/listening states, vinyl to represent playback/the final result
- `cassette.glb`, `music_note.glb` — likely pairing for a Neural Monitor on/off interaction (e.g. a cassette or speaker appearing when Live A/B is toggled)
- `guitar.glb`, `bass_guitar.glb`, `piano.glb`, `kazoo.glb` — the avatar "playing" the instrument matching whichever stem is currently being processed (guitar for guitar stems, the 4-string model for bass, piano for piano, kazoo for any wind instrument), cycling through all of them for a single combined instrumental stem

### Vocal Chain Design

The vocal processing chain is the most carefully engineered part of the system. Here is the exact signal flow:

```
Raw vocal stem
    │
    ▼
1. Denoise ─────────────────── Spectral noise reduction (gate-based)
    │                           Applied FIRST so compression/EQ don't amplify noise
    ▼
2. Adaptive HPF ────────────── Tracks the vocal's measured fundamental frequency
    │                           Not a fixed 100Hz — adapts to the singer (baritone,
    │                           tenor, alto, soprano all get appropriate cutoff)
    ▼
3. Resonance suppression ───── Cuts only where energy piles up in the mud range
    │                           (100-400Hz). Narrow notch filters on persistent peaks.
    ▼
4. Presence boost ──────────── +1.5dB at 3kHz (Q=1.2)
    │                           Section-aware: chorus gets +0.7dB more,
    │                           verse gets -0.3dB (less aggressive)
    ▼
5. Compression ─────────────── Role-specific with automatic makeup gain
    │                           Blueprint mode: serial 2-stage
    │                           (FET peak catcher → Opto leveler)
    ▼
6. De-esser ────────────────── Multiband 4-8kHz, register-adaptive threshold
    │                           Low register = more aggressive de-essing
    │                           High/Falsetto = gentler (sibilance is natural)
    ▼
7. Vocal_Main bus ──────────── All lead takes summed into one coherent entity
    │                           Glue compression on the bus
    ▼
8. Vocal_Doubles bus ───────── All backing vocals summed, glued,
    │                           then scaled to 50% of Main level (-6dB)
    ▼
9. Space ───────────────────── Genre-aware reverb + BPM-synced delay
    │                           Section-adaptive: chorus opens up (longer decay,
    │                           wider stereo), verse stays intimate (shorter decay)
    ▼
10. Spectral ducking ───────── Only the 1-4kHz band is pulled back
    │                           in the instrumental when the vocal is active
    ▼
    To mix bus
```

### Safety & Guardrails

The system has multiple layers of protection to prevent bad mixes, blown speakers, or silent renders:

| Guardrail | Location | What it prevents |
|---|---|---|
| **Main/Lead never warped** | `elastic_align.py` (name-based guard) | Elastic alignment artifacts on the primary vocal |
| **Main/Lead never attenuated** | `leveling.py` (name skip) | Level compensation reducing lead presence |
| **Warp limit 2%** | `elastic_align.py` (threshold check) | Flutter artifacts from excessive DTW stretching |
| **Energy guard** | `elastic_align.py` (60% RMS check) | Swapped lead/double arguments going undetected |
| **Makeup gain after every compressor** | `mixengine.py` (post-comp gain) | Cumulative 6-12dB level drop across serial compression |
| **Peak safety ceiling** | `masterengine.py` (-1dBFS hard limit) | Digital clipping on the mix bus |
| **Neural Monitor peak normalization** | `audition.py` (peak detect + gain) | DSP bug blasting the speakers |
| **Neural Monitor anti-click fades** | `audition.py` (5ms cosine fades) | Click/pop artifacts on A/B toggle |
| **Director Safety validation** | `director_safety.py` (range clamp) | LLM suggesting out-of-range parameters |
| **Try-except everywhere** | All modules | Single module failure taking down the entire render |
| **QC auto-correction** | `qc.py` (LUFS/true-peak check) | Master not meeting loudness targets |
| **Feature flags off by default** | `config.py` (default=False) | Experimental code affecting production mixes |

### Verification Suite

Four automated tests validate the system. Run them in order:

#### 1. `check_monitor.py` — Audio Hardware Check

```bash
python check_monitor.py
```

Checks that:
- `ENABLE_LIVE_AUDITION` flag is active
- sounddevice can enumerate audio devices
- Default input/output devices are available
- `sd.OutputStream` can be opened successfully

**Expected output:**
```
Flag: ENABLE_LIVE_AUDITION = True
[OK]   Flag is ON — Neural Monitor is enabled.

sounddevice 0.4.6: 36 device(s) found
  Default input  : Gruppo microfoni (Tecnologia In) (channels=2)
  Default output : Altoparlanti (Realtek(R) Audio) (channels=2)

[PASS] Audio hardware ready — OutputStream opened OK
```

#### 2. `verify_gain.py` — Gain Staging Verification

```bash
python verify_gain.py
```

Generates two synthetic test tones:
- **Main** at 0dBFS (RMS = 1/√2 ≈ 0.707107)
- **Double** at -6dBFS (RMS = 0.353553)

Simulates the mix bus logic and asserts:
- **Main RMS in mix** is identical to original (diff=0.0) — the lead is bit-perfect
- **Double RMS in mix** is exactly 50% of original (-6dB) — doubles support, don't compete

**Expected output:**
```
Original Main  RMS: 0.707107  (expected ~0.707107)
Original Double RMS: 0.353553  (expected ~0.353553)

Main  in mix RMS: 0.707107  (expected ~0.707107)
Double in mix RMS: 0.176777  (expected ~0.176777)

[PASS] Main RMS in mix (0.707107) == Main RMS original (0.707107) (diff=0.000000)
[PASS] Double RMS in mix (0.176777) == Double RMS original * 0.5 (0.176777) (diff=0.000000)

ALL CHECKS PASSED — Gain staging is correct.
```

#### 3. `latency_test.py` — DSP→UI Bridge Latency

```bash
python latency_test.py
```

Measures the round-trip time from a DSP trigger to the UI bridge (pywebview's `evaluate_js`). Runs 100 iterations after 10 warmup iterations.

**Expected output:**
```
Warming up (10 iterations)...
Running 100 iterations...

  Iterations : 14
  Min latency: 0.064 ms
  Max latency: 0.509 ms
  Avg latency: 0.158 ms
  Median     : 0.107 ms
  P95        : 0.509 ms
  Target     : < 30.0 ms
  Result     : PASS (avg 0.2ms < 30.0ms)
```

> **Note:** The iteration count may vary (typically 14-100) because the test filters out iterations where the high-resolution timer resolution affects measurement. The key metric is **avg latency < 30ms** — the actual result is typically **0.03-0.16ms**, well within target.

#### 4. `ci_validate.py` — CI Quality Gate (Full System Validation)

```bash
python ci_validate.py
```

This is the **automated CI entry point**. It:
1. Runs `verify_gain.py` as a subprocess
2. If PASS: auto-enables **all** feature flags in `.flags.json`
3. If FAIL: exits with code 1 and diagnostic output
4. Reports system ready status

**Expected output:**
```
[Step 1/2] Running gain staging verification...
ALL CHECKS PASSED — Gain staging is correct.

[Step 2/2] Verification PASSED — enabling all feature flags...
[CI] Flags written to .flags.json

[CI] CI VALIDATION: PASS
[CI] System ready — all flags enabled, Neural Monitor online.
```

### Async UI Decoupling

The DSP pipeline can fire dozens of `onStep`/`onEvent` calls per second during a render. pywebview's .NET/COM bridge serializes each `evaluate_js` call synchronously, which would block the pipeline.

**Solution:** A background thread drains a `queue.Queue`:

```
DSP pipeline → queue.put(js_code) → [QUEUE] → worker thread → evaluate_js()
                                              │
                                         60fps throttle
                                         (16.7ms min interval)
                                              │
                                         Stale entry drain
                                         (newer event supersedes older)
```

- **60fps throttle**: minimum 16.7ms between JS evals — prevents flooding the bridge
- **Stale entry draining**: if a newer event of the same type is queued before the old one is processed, the old one is dropped (e.g., rapid compressor hits only show the latest value)
- **Sentinel shutdown**: pushing `None` to the queue stops the worker thread cleanly

### Reference Document

`DSP_ENGINE_SPECS.md` is the ground-truth numeric rulebook. It reconciles conflicting guidance across three audio engineering sources (Stavrou, Eargle, Winer) into single resolved defaults:

- **Gain staging target**: -18dBFS RMS (0 VU)
- **De-esser method**: Multiband 4-8kHz (not broadband)
- **Compressor models**: 3 distinct types (VCA for bus, FET for drums, Opto for vocals)
- **Signal chain order**: HPF → Resonance → EQ → Comp → De-esser → Limiter
- **Per-instrument compressor settings**: Full table with ratio, attack, release, knee for every instrument type

### Status

Actively developed. See `.omo/` for planning notes and commit history for progress.

**Completed phases:**
- **Fase 0** — Director Mode: human-in-the-loop approval checkpoint, verified end-to-end across threads
- **Fase 2** — Blueprint DSP chains (serial vocal comp, drum glue, bass chain), RT60 reverb calibration
- **Fase 3** — LTAS spectral matching against a reference track
- **Fase 4** — LLM advisory: local Qwen 2.5 1.5B model for ambiguous stem classification, validated through director_safety.py
- **Fase 5** — GUI: two-column layout, GSAP-driven SVG avatar with real-time DSP reactions, streaming LLM console, cylon bar, Neural Monitor live A/B audition
- **Fase 6** — PyInstaller packaging: built and launch-tested with all dependencies bundled (llama_cpp, pywebview, sounddevice, the GGUF model). Still needs a clean-machine test.

**Recent hardening (July 2026):**
- Vocal_Main / Vocal_Doubles bus split — doubles at 50% (-6dB) so the lead keeps presence
- Makeup gain after every compressor stage — prevents cumulative level drop
- Elastic align warp limit reduced to 2% — eliminates flutter artifacts
- Main/Lead vocals are never warped or level-compensated — they are the timing grid
- Neural Monitor fixed: WASAPI sample rate mismatch resolved, makeup gain added for quiet signals
- File picker fixed: added single-file audio selection alongside folder picker
- `motus_base.png` avatar background integrated as SVG `<image>` element
- **CI quality gate** (`ci_validate.py`): automated self-validation that runs `verify_gain.py`, auto-enables all feature flags on PASS, exits 1 on FAIL
- **`system_ready` event**: emitted when the Python bridge initializes — triggers a 3-pulse power-on glow animation on the avatar's nose piercing
- **Async UI decoupling**: `queue.Queue`-based background thread drains JS eval calls so the DSP pipeline never blocks on UI updates. 60fps throttle (16.7ms) with stale entry draining
- **Low-latency audio**: `audition.py` now uses `sd.OutputStream(blocksize=512, latency='low')` instead of `sd.play`/`sd.wait`
- **Latency test** (`latency_test.py`): measures DSP trigger → UI bridge round-trip. Result: avg **0.158ms** (target: <30ms)

### Known Issues & Troubleshooting

#### Black/blank window on launch

**Symptom:** The desktop shortcut opens a black window that never renders the UI.

**Root cause (confirmed, fixed):** `app/api.py`'s `Api` class stored the raw pywebview `Window` object as a **public** attribute (`self.window`). pywebview's own `js_api` introspection (`webview/util.py`'s `inject_pywebview` → `get_functions`) recursively walks *every public attribute* of the `Api` instance to build the `window.pywebview.api` bridge exposed to JS. Walking into `self.window` descends into the WinForms/.NET WebView2 control's `.native` COM object, and once external UI-Automation software has touched that window's accessibility tree (NVIDIA Overlay and, separately, AVG were both observed triggering it), that COM graph contains a genuinely infinite chain — `window.native.AccessibilityObject.Bounds.Empty.Empty.Empty...` — which pywebview's reflection walker has no cycle detection for. The resulting `RecursionError` spam starves the WebView2 message loop badly enough that the page never finishes loading, and the window just stays on its background color forever, with no visible exception to the user.

Killing the overlay process was an earlier (incorrect) workaround that happened to "fix" it by coincidence — the real fix doesn't depend on what overlay software is or isn't running.

**Fix (applied):** Renamed `Api.window` → `Api._window` in both `app/api.py` and `app/main.py`. pywebview's walker explicitly skips any attribute name starting with `_`, so the window object is simply never introspected — no COM graph is ever walked, regardless of what UI-Automation tooling is active. Verified by reproducing the failure reliably beforehand (`last_load.log` never written, console flooded with the recursion error), then confirming clean, repeatable page loads immediately after the rename.

**Diagnosis (if it ever recurs):**
1. Check `%LOCALAPPDATA%\RedLineEngine\last_load.log` — if missing or stale, the page never loaded
2. Check `%LOCALAPPDATA%\RedLineEngine\startup_error.log` for a Python-level exception
3. Set `REDLINE_DEBUG_GUI=1` to open Chrome DevTools alongside the window and inspect the console directly
4. If it's this same bug again, it means something added a new public attribute on `Api` pointing at the `window` object (or another object that eventually references it) — audit `app/api.py` for any `self.<name> = window` and rename with a leading underscore

#### Neural Monitor no audio

**Symptom:** The Neural Monitor toggle is ON but no sound comes from the speakers.

**Root cause (fixed):** WASAPI sample rate mismatch between the audio file and the default output device. Also, quiet signals needed makeup gain to be audible.

**Fix (applied in commit `8582693`):**
- `audition.py` now matches the output device's native sample rate
- Makeup gain added: target peak 0.85 for quiet signals
- Peak normalization ensures loud signals don't clip

#### File picker not showing audio files

**Symptom:** The file picker only shows folders, not individual audio files.

**Root cause (fixed):** The original implementation only used folder selection (`OPEN_DIALOG` with `DIRECTORY` flag).

**Fix (applied in commit `763c564`):**
- Added `pick_input_file()` method using `OPEN_DIALOG` with audio file type filters
- Both folder and single-file selection are now available

---

## Italiano 🇮🇹

### Panoramica

RedLine Engine è un sistema automatico di mixing e mastering standalone. Ingestisce stem grezzi multitraccia (o un singolo file già mixato), classifica ogni stem per ruolo, registro e profondità spaziale, applica una catena DSP completa di mixing con elaborazione per-stem, e infine masterizza il risultato verso un target di loudness o un brano di riferimento.

L'intera pipeline è **basata su misurazioni**: ogni taglio EQ, ratio di compressione e quantità di riverbero è calcolato da misurazioni audio reali (frequenza fondamentale, crest factor, centroide spettrale, energia RMS), non da preset statici. Il sistema si adatta al materiale, non il contrario.

**Principi di design fondamentali:**
- **La voce principale (Main) è la star** — full-range, centrata, con presenza accentuata, elaborazione minima. Doppie e armonie supportano al 50% (-6dB) così la Main non perde mai presenza.
- **Le voci Main/Lead sono la griglia temporale** — mai warplate dall'allineamento elastico, mai attenuate dalla compensazione di livello.
- **La sicurezza prima dell'ingegno** — ogni modulo sperimentale è disabilitato di default dietro flag. Disabilitare un flag è un rollback istantaneo e completo.
- **Misurato, non ipotizzato** — tutti i parametri DSP sono calcolati da misurazioni audio reali, non da preset statici.
- **Fail-safe di design** — ogni modulo è wrapped in try-except. Un dispositivo audio mancante, un'inferenza LLM fallita o un errore librosa non fermano mai il render.

### Struttura del Progetto

```
RedLineEngine/
├── app/                          # GUI desktop (pywebview)
│   ├── main.py                   # Punto d'ingresso — crea finestra, carica UI
│   ├── api.py                    # Ponte Python↔JS (file picker, controllo pipeline, eventi)
│   └── web/                      # Frontend (HTML/CSS/JS)
│       ├── index.html            # Layout a due colonne
│       ├── app.js                # Animazioni GSAP UI, wiring eventi avatar
│       ├── three-avatar.js       # Avatar 3D con rig (Three.js, AnimationMixer)
│       ├── style.css             # Tema scuro industriale
│       ├── assets/               # skull.glb + modelli strumenti/props predisposti (non tutti collegati)
│       └── vendor/               # Self-hosted, completamente offline (nessuna dipendenza CDN)
│           ├── gsap.min.js       # GreenSock Animation Platform
│           └── three/            # Core Three.js + GLTFLoader + moduli postprocessing
├── redline/                      # Motore DSP core
│   ├── naming.py                 # Riconoscimento ruolo/pan/sezione via regex
│   ├── analyze.py                # Pitch pYIN, analisi VAD-gated, rilevamento genere
│   ├── analysis/                 # Sotto-moduli di profilazione spettrale
│   ├── depth.py                  # Classificazione asse Z (primo/centro/sfondo)
│   ├── mixengine.py              # Catena DSP per-stem (il cuore del mix)
│   ├── masterengine.py           # Glue multibanda, limiting, targeting LUFS, loop QC
│   ├── elastic_align.py          # Allineamento DTW sillabico per doppie (max 2% warp)
│   ├── leveling.py               # Compensazione gain a potenza costante (salta Main/Lead)
│   ├── alignment.py              # Allineamento sample-precise per cross-correlation
│   ├── deesser.py                # De-esser multibanda 4-8kHz
│   ├── resonance.py              # Soppressione adattiva risonanze fascia mud
│   ├── masking.py                # Tagli preventivi di mascheramento spettrale
│   ├── denoise.py                # Riduzione rumore spettrale (prima in catena)
│   ├── reverbbus.py              # 3 bus riverbero condivisi (Room/Plate/Hall)
│   ├── fxsends.py                # Quantità riverbero/delay in base al genere
│   ├── vocalstack.py             # Classificazione registro + elaborazione per-registro
│   ├── ltas.py                   # Matching Long-Term Average Spectrum (FIR, ±2.5dB)
│   ├── rt60.py                   # Regressione onset+decay per calibrazione riverbero
│   ├── qc.py                     # Controllo true-peak/LUFS/compatibilità mono
│   ├── audition.py               # Neural Monitor — ascolto A/B live
│   ├── llm_classifier.py         # LLM locale (Qwen 2.5 1.5B) per classificazione stem
│   ├── director_safety.py        # Validatore/clamp output LLM
│   ├── director.py               # Gate threading.Event per approvazione GUI
│   ├── config.py                 # Sistema flag sperimentali
│   ├── metrics.py                # Strumentazione timing per-stadio
│   └── dsp_utils.py              # Utility condivise (envelope follower, curve duck, ecc.)
├── tests/                        # Verifica e validazione
│   ├── verify_gain.py            # Test sintetico gain staging
│   ├── latency_test.py           # Misurazione round-trip DSP→UI
│   └── check_monitor.py          # Controllo hardware audio + stato flag
├── ci_validate.py                # Quality gate CI (lancia verify_gain.py, auto-attiva flag)
├── DSP_ENGINE_SPECS.md           # Regolamento numerico di riferimento
├── requirements.txt              # Dipendenze Python
├── .flags.json                   # Flag locali (gitignorato, locale alla macchina)
└── README.md                     # Questo file
```

### Avvio Rapido

```bash
# 1. Crea un ambiente virtuale (consigliato)
python -m venv .venv
.venv\Scripts\activate     # Windows
source .venv/bin/activate  # macOS/Linux

# 2. Installa le dipendenze
pip install -r requirements.txt

# 3. Avvia l'app desktop
python app/main.py

# 4. Oppure esegui in modalità CLI (senza GUI)
python -m redline.cli --input /percorso/stem --output /percorso/uscita

# 5. Attiva funzionalità sperimentali
echo '{"ENABLE_BLUEPRINT_CHAINS": true}' > .flags.json

# 6. GUI con debug (apre Chrome DevTools insieme alla finestra)
REDLINE_DEBUG_GUI=1 python app/main.py
```

### Configurazione: Flag Sperimentali

Ogni modulo sperimentale è **disabilitato di default**. I flag sono definiti in `redline/config.py` e possono essere attivati in tre modi:

1. **`.flags.json`** (gitignorato, locale alla macchina) — persiste tra sessioni:
   ```json
   { "ENABLE_BLUEPRINT_CHAINS": true, "ENABLE_LIVE_AUDITION": true }
   ```
2. **Variabili d'ambiente** — sovrascrivono `.flags.json` per esecuzioni singole:
   ```bash
   REDLINE_BLUEPRINT_CHAINS=1 REDLINE_LIVE_AUDITION=1 python app/main.py
   ```
3. **Auto-abilitazione CI** — `ci_validate.py` attiva tutti i flag automaticamente al PASS.

| Flag | Default | Cosa sblocca |
|---|---|---|
| `ENABLE_BLUEPRINT_CHAINS` | off | Compressione vocale seriale (FET peak-catcher + Opto leveler), glue drum bus + saturazione nastro, basso 2-band + harmonic exciter |
| `ENABLE_LTAS_MATCHING` | off | Matching spettrale FIR (`redline/ltas.py`) contro un brano di riferimento durante il mastering |
| `ENABLE_RT60_CALIBRATION` | off | Calibrazione automatica del decadimento dei bus riverbero Room/Plate dall'analisi onset/decay di un riferimento (`redline/rt60.py`) |
| `ENABLE_LLM_ADVISORY` | off | LLM locale (llama.cpp, `redline/llm_classifier.py`) per classificazione stem ambigui, validato da `redline/director_safety.py` |
| `ENABLE_LIVE_AUDITION` | off | Neural Monitor — ascolto A/B dry/wet in tempo reale della glue compression del master bus attraverso le casse (`redline/audition.py`). Attivabile live dall'interruttore GUI |
| `ENABLE_DIRECTOR_MODE` | off | Mette in pausa `render_mix` dopo il riconoscimento ruolo/registro e aspetta approvazione GUI (`redline/director.py`) prima di qualsiasi elaborazione DSP |

### Note Libere (testo libero → interpretazione LLM)

La schermata del wizard ha un campo di testo libero in alto: "descrivi in linguaggio semplice, non tecnico, cosa vorresti diverso nel mix" (es. *"vorrei un suono più caldo, quasi da vinile, e la voce un po' più protagonista"*). Lasciato vuoto, significa esattamente questo — nessuna richiesta speciale, usa gli slider sotto così come sono.

Se compilato, `app/api.py` passa il testo a `redline/llm_classifier.interpret_creative_brief()`, che chiede al modello locale di tradurlo in piccoli aggiustamenti su esattamente **i 3 knob del wizard già esistenti** — `aggressiveness`, `warmth`, `vocal_prominence` — mai parametri DSP grezzi. Ogni valore passa comunque attraverso `redline/director_safety.clamp_params()` (stessi range degli slider stessi) prima di poter raggiungere `MixPreferences`, quindi un'interpretazione troppo entusiasta ("fallo suonare come un mostro") può solo spingere entro il range che un umano che muove gli slider potrebbe già raggiungere — non può mai superarlo. Ricade sui valori degli slider intatti se la richiesta è vuota, il modello locale non è disponibile, o la sua risposta non si analizza come JSON valido.

### Architettura

#### DSP Core (`redline/`)

| Modulo | Cosa fa |
|---|---|
| `naming.py` | Riconoscimento ruolo, pan e sezione degli stem tramite regex dai nomi file. Riconosce pattern come `vocal_main`, `lead_vox`, `bass_di`, `kick_in`, `snare_top`, `hihat`, `overhead`, `room`, `fx_reverb` ecc. |
| `analyze.py` + `analysis/` | Stima pitch pYIN, analisi VAD-gated (il voice activity detection limita l'analisi ai soli momenti in cui la voce canta realmente), rilevamento genere da tempo/features spettrali, profilazione spettrale (centroide, rolloff, flusso, crest factor per banda). |
| `depth.py` | Classificazione asse Z (primo piano / centro / sfondo) via Crest Factor + flusso spettrale. Primo piano = alto crest + alto flusso (ricco di transienti, microfonato vicino). Sfondo = basso crest + basso flusso (ambient, microfoni ambiente). |
| `mixengine.py` | **Il cuore del mix.** Catena DSP per-stem: HPF adattivo che segue la fondamentale misurata della voce, soppressione risonanze, compressione ruolo-specifica con makeup gain automatico, de-esser, profondità spaziale. Crea bus separati Vocal_Main e Vocal_Doubles (doppie al 50%). Ducking spettrale (banda 1-4kHz abbassata negli strumenti quando la voce è attiva), sidechain kick/basso, bus musicale Mid/Side, compressione parallela NY. |
| `masterengine.py` | Compressione glue multibanda (split low/mid/high con soglie indipendenti), soft-clip limiting, polish mid/side (allarga l'immagine stereo nella banda alta), targeting LUFS per piattaforma (Spotify -14dB, YouTube -13dB, Apple Music -16dB), loop QC automatico con correzione e re-render. |
| `elastic_align.py` | Allineamento temporale sillabico via DTW (Dynamic Time Warping) per doppie vocali. **Le voci Main/Lead non vengono mai warplate** (guardia basata sul nome). Warp massimo limitato al **2%** — se DTW richiede più stiramento, la finestra viene saltata per prevenire artefatti flutter. Guardia energetica: se il segnale "lead" ha meno del 60% dell'RMS del double, la funzione esce (probabili argomenti invertiti). |
| `leveling.py` | Compensazione di gain a potenza costante (1/√N) per take vocali sovrapposti. **Salta le voci Main/Lead** — applicato solo a doppie/adlib. Previene il problema "troppi take" dove sommare N take identici dà un aumento di ampiezza di √N. |
| `alignment.py` | Allineamento cross-correlation sample-precise delle doppie al riferimento lead. Trova l'offset di campioni che massimizza la correlazione, poi sposta il segnale double. |
| `deesser.py` | De-esser multibanda (4-8kHz) con soglia adattiva per registro. Registro basso = soglia più bassa (meno energia sibilante), Alto/Falsetto = soglia più alta (più sibilanza è naturale). Usa la stima dell'inviluppo spettrale per distinguere sibilanza da contenuto vocale reale. |
| `resonance.py` | Rilevamento e soppressione adattiva delle risonanze nella fascia mud (100-400Hz). Trova picchi spettrali che persistono attraverso più frame (risonanze, non note) e applica filtri notch stretti. |
| `masking.py` | Taglio preventivo di mascheramento: misura la sovrapposizione spettrale tra strumenti e la banda di presenza della voce (2-5kHz). Se uno strumento occupa >30% della banda di presenza vocale, viene applicato un taglio gentile a quello strumento. |
| `denoise.py` | Riduzione rumore spettrale applicata **prima** di qualsiasi altro DSP (così compressione/EQ non alzano il rumore di fondo). Usa spectral gating: stima il rumore di fondo dai passaggi silenziosi, poi lo sottrae dal segnale completo. |
| `reverbbus.py` | 3 bus riverbero condivisi (Room / Plate / Hall) invece di istanze per-stem — risparmia CPU e crea uno spazio coeso dove tutti gli strumenti condividono la stessa coda di riverbero. Ogni bus ha decay, pre-delay e damping indipendenti. |
| `fxsends.py` | Quantità di riverbero/delay in base al genere, delay sincronizzato al BPM (divisioni da quarto/ottavo/ottavo con punto), drum room send (la cassa riceve meno room del rullante). |
| `vocalstack.py` | Classificazione registro (Low / Unison / High / Falsetto) con ricette di elaborazione per registro — un muro di doppie suona come un'entità definita. Registro basso riceve più corpo, Falsetto riceve più aria. |
| `ltas.py` | Matching Long-Term Average Spectrum via filtro FIR, clampato ±2.5dB. Analizza lo spettro di un brano di riferimento e applica un filtro FIR correttivo così lo spettro medio del master corrisponde al riferimento. |
| `rt60.py` | Regressione onset + decay per stimare RT60 da un brano di riferimento. Rileva transienti di attacco, misura la pendenza del loro decadimento e calcola il tempo per un calo di -60dB. Usato per calibrare i tempi di decay dei bus riverbero. |
| `qc.py` | Controllo true-peak / LUFS / compatibilità mono con correzione automatica e re-render. Se LUFS è fuori di più di 0.5dB, il master viene ri-renderizzato con makeup gain regolato. Se la compatibilità mono è sotto -6dB di correlazione, viene applicata una regolazione Mid/Side. |
| `audition.py` | **Neural Monitor** — ascolto A/B live attraverso le casse via sounddevice/PortAudio. Usa `sd.OutputStream(blocksize=512, latency='low')` per riproduzione a bassa latenza. Normalizzazione di picco (massimale a -1dBFS), fade in/out anti-click (fade coseno di 5ms), makeup gain per segnali deboli (target picco 0.85). Attivabile live dall'interruttore GUI. |
| `llm_classifier.py` | LLM locale offline (Qwen 2.5 1.5B, quantizzato GGUF, ~1GB) per classificazione stem ambigui. Subentra quando la confidenza del regex è sotto soglia. Streamma i token live nella console GUI. Funziona interamente in locale — nessuna connessione internet necessaria. |
| `director_safety.py` | Valida e clamp qualsiasi valore suggerito dall'LLM prima che raggiunga il motore. Impedisce all'LLM di suggerire ratio di compressione fuori range, curve EQ impossibili o valori di gain pericolosi. |
| `director.py` | Gate basato su `threading.Event` che mette in pausa `render_mix` per approvazione GUI a metà pipeline. Dopo il riconoscimento ruolo/registro degli stem, la pipeline si blocca finché l'utente non clicca "Approva" o "Modifica" nella GUI. |
| `config.py` | Sistema di flag con `.flags.json` + override da variabili d'ambiente. Legge i flag all'avvio, osserva modifiche ai file (futuro: hot-reload). |
| `metrics.py` | Strumentazione timing in-memory per stadio. Logga `[METRIC] stage: Xs` per ogni fase della pipeline. Usato per profilazione delle performance e rilevamento regressioni. |
| `dsp_utils.py` | Utility DSP condivise: envelope follower (RMS con finestra configurabile), curve di gain duck (lineari/esponenziali), curve di gain per banda, saturazione (soft-clip/tanh), panning (equal-power), codifica/decodifica Mid/Side. |

#### GUI (`app/`)

| Modulo | Cosa fa |
|---|---|
| `main.py` | Punto d'ingresso pywebview desktop. Crea la finestra (1280x800, tema scuro), carica la UI web da `web/index.html`, scrive un marker di conferma caricamento in `%LOCALAPPDATA%\RedLineEngine\last_load.log` per diagnostica finestra nera. Chiama `api.system_ready()` quando la pagina finisce di caricarsi. |
| `api.py` | Ponte sottile Python↔JS. Espone a JavaScript: `pick_input_path()` (selettore cartelle), `pick_input_file()` (selettore file audio singolo), `run_pipeline()` (avvia il mix), `toggle_neural_monitor()` (interruttore A/B live), `approve_director_checkpoint()` (approvazione Director Mode). Gestisce anche la **coda asincrona JS eval** — un thread background svuota le chiamate `queue.Queue` così la pipeline DSP non si blocca mai sugli aggiornamenti UI. Throttle a 60fps (intervallo minimo 16.7ms) con drenaggio entry stale (se un evento più nuovo sostituisce uno più vecchio, il vecchio viene scartato). |
| `web/index.html` | Layout a due colonne: schermate di workflow (selezione file, progresso pipeline, risultati QC) a sinistra, avatar + console terminale a destra. |
| `web/app.js` | Animazioni GSAP. Gestisce tutti i casi `onEvent()`: de-esser → flash piercing, glue compression → orecchini che tintinnano, BPM → headbang, inferenza LLM → occhiali che brillano ("deep scan"), system_ready → 3 impulsi di accensione, director_checkpoint → dialogo approvazione, risultati QC → visualizzazione canvas. |
| `web/style.css` | Tema scuro industriale (#0A0A0A sfondo, #FF003F rosso accento, #1A1A1A superfici pannello). Stile moduli rack, pannello terminale con font monospace, animazioni glitch, cylon bar (striscia LED a scansione). |
| `web/vendor/gsap.min.js` | GreenSock Animation Platform (~40KB minificato). Animazioni fluide e performanti a 60fps senza jQuery. |

#### Sistema Avatar

L'avatar è un personaggio 3D reale con rig (`app/web/assets/skull.glb`, un asset CC0), renderizzato con una copia di Three.js self-hosted e completamente offline (`app/web/vendor/three/` — nessuna dipendenza da CDN, importante per l'exe pacchettizzato) e pilotato da `app/web/three-avatar.js`. Ha sostituito un precedente design SVG piatto in wireframe.

Il modello include clip di animazione già pronte, riprodotte tramite un `THREE.AnimationMixer` — animazione scheletrica reale, non matematica di rotazione ossea finta:

| Clip | Innesco |
|---|---|
| `Idle` | Stato di default, in loop continuo |
| `Bite_Front` | De-esser in azione (uno "scatto" rapido) |
| `Bite_InPlace` (in loop) | Inferenza LLM ("deep scan") |
| `HitRecieve` | Colpo forte di glue compression |
| `Dance` | Completamento della pipeline |
| `Yes` / `No` | Approvazione / rifiuto Director Mode |

Oltre alla riproduzione delle clip, il ciclo di rendering aggiunge:
- **Sguardi naturali e intermittenti** — una macchina a stati hold/turn (non una rotazione lenta e costante, che era un bug reale: un accumulatore `rotation.y +=` residuo di un anello reattivo poi rimosso). Resta fermo per 1.5–5s, poi scatta uno sguardo con easing smoothstep (0.6–1.1s) verso un nuovo angolo casuale, come si muove davvero una testa umana invece di un faro rotante.
- **Marker di bagliore agli occhi** (piccole sfere emissive rosse, posizionate in base al bounding box del modello stesso) che lampeggiano sui colpi del de-esser.
- **Materiale**: la texture dipinta originale del modello viene mantenuta (non scartata per un colore piatto) e tinta di un grigio-argento freddo per abbinarsi al tema nero/rosso/argento, renderizzata con sfondo trasparente (nessun rettangolo visibile dietro) e senza post-processing bloom (il bloom rompeva in modo affidabile la trasparenza del canvas e bruciava ogni materiale a bianco pieno).

Nella cartella `app/web/assets/` sono predisposti altri asset per funzionalità pianificate, non ancora collegate:
- `headphones.glb`, `vinyl.glb` — un momento "cuffie che spuntano" per il toggle/ascolto del Neural Monitor, vinile per rappresentare la riproduzione/il risultato finale
- `cassette.glb`, `music_note.glb` — probabile abbinamento per un'interazione on/off del Neural Monitor (es. una cassetta o un altoparlante che compare quando si attiva il Live A/B)
- `guitar.glb`, `bass_guitar.glb`, `piano.glb`, `kazoo.glb` — l'avatar che "suona" lo strumento corrispondente allo stem in elaborazione (chitarra per stem di chitarra, il modello a 4 corde per il basso, piano per il piano, kazoo per qualsiasi fiato), a rotazione per un singolo stem strumentale combinato

### Progettazione della Catena Vocale

La catena di elaborazione vocale è la parte più attentamente ingegnerizzata del sistema. Ecco il flusso di segnale esatto:

```
Stem vocale grezzo
    │
    ▼
1. Denoise ─────────────────── Riduzione rumore spettrale (gate-based)
    │                           Applicata PRIMA così compressione/EQ non amplificano il rumore
    ▼
2. HPF adattivo ────────────── Segue la frequenza fondamentale misurata della voce
    │                           Non un fisso 100Hz — si adatta al cantante (baritono,
    │                           tenore, alto, soprano ricevono tutti il cutoff appropriato)
    ▼
3. Soppressione risonanze ──── Taglia solo dove l'energia si accumula nella fascia mud
    │                           (100-400Hz). Filtri notch stretti su picchi persistenti.
    ▼
4. Presenza ────────────────── +1.5dB a 3kHz (Q=1.2)
    │                           Adattivo per sezione: chorus prende +0.7dB in più,
    │                           verse prende -0.3dB (meno aggressivo)
    ▼
5. Compressione ────────────── Ruolo-specifica con makeup gain automatico
    │                           Modalità blueprint: 2-stadi seriali
    │                           (FET peak catcher → Opto leveler)
    ▼
6. De-esser ────────────────── Multibanda 4-8kHz, soglia adattiva per registro
    │                           Registro basso = de-essing più aggressivo
    │                           Alto/Falsetto = più gentile (la sibilanza è naturale)
    ▼
7. Bus Vocal_Main ──────────── Tutti i take lead sommati in un'entità coerente
    │                           Glue compression sul bus
    ▼
8. Bus Vocal_Doubles ───────── Tutte le backing vocals sommate, incollate,
    │                           poi scalate al 50% del livello Main (-6dB)
    ▼
9. Spazio ──────────────────── Riverbero in base al genere + delay sincronizzato al BPM
    │                           Adattivo per sezione: chorus si apre (decay più lungo,
    │                           stereo più largo), verse resta intimo (decay più corto)
    ▼
10. Ducking spettrale ──────── Solo la banda 1-4kHz viene abbassata
    │                           negli strumentali quando la voce è attiva
    ▼
    Al mix bus
```

### Sicurezza e Protezioni

Il sistema ha molteplici strati di protezione per prevenire mix scadenti, casse saltate o render silenziosi:

| Protezione | Posizione | Cosa previene |
|---|---|---|
| **Main/Lead mai warplate** | `elastic_align.py` (guardia nome) | Artefatti di allineamento elastico sulla voce primaria |
| **Main/Lead mai attenuate** | `leveling.py` (skip nome) | Compensazione di livello che riduce la presenza della lead |
| **Limite warp 2%** | `elastic_align.py` (controllo soglia) | Artefatti flutter da stiramento DTW eccessivo |
| **Guardia energetica** | `elastic_align.py` (check 60% RMS) | Argomenti lead/double invertiti che passano inosservati |
| **Makeup gain dopo ogni compressore** | `mixengine.py` (gain post-comp) | Calo cumulativo di 6-12dB attraverso compressione seriale |
| **Massimale di picco** | `masterengine.py` (limite -1dBFS) | Clipping digitale sul mix bus |
| **Normalizzazione picco Neural Monitor** | `audition.py` (rilevamento picco + gain) | Bug DSP che esplode le casse |
| **Fade anti-click Neural Monitor** | `audition.py` (fade coseno 5ms) | Artefatti click/pop su toggle A/B |
| **Validazione Director Safety** | `director_safety.py` (clamp range) | LLM che suggerisce parametri fuori range |
| **Try-except ovunque** | Tutti i moduli | Fallimento di un singolo modulo che abbatte l'intero render |
| **Auto-correzione QC** | `qc.py` (check LUFS/true-peak) | Master che non raggiunge i target di loudness |
| **Flag sperimentali off di default** | `config.py` (default=False) | Codice sperimentale che influenza mix di produzione |

### Suite di Verifica

Quattro test automatizzati validano il sistema. Eseguiti in ordine:

#### 1. `check_monitor.py` — Controllo Hardware Audio

```bash
python check_monitor.py
```

Verifica che:
- Il flag `ENABLE_LIVE_AUDITION` sia attivo
- sounddevice possa enumerare i dispositivi audio
- I dispositivi di input/output predefiniti siano disponibili
- `sd.OutputStream` possa essere aperto con successo

**Output atteso:**
```
Flag: ENABLE_LIVE_AUDITION = True
[OK]   Flag is ON — Neural Monitor is enabled.

sounddevice 0.4.6: 36 device(s) found
  Default input  : Gruppo microfoni (Tecnologia In) (channels=2)
  Default output : Altoparlanti (Realtek(R) Audio) (channels=2)

[PASS] Audio hardware ready — OutputStream opened OK
```

#### 2. `verify_gain.py` — Verifica Gain Staging

```bash
python verify_gain.py
```

Genera due toni sintetici di test:
- **Main** a 0dBFS (RMS = 1/√2 ≈ 0.707107)
- **Double** a -6dBFS (RMS = 0.353553)

Simula la logica del mix bus e verifica:
- **Main RMS in mix** è identico all'originale (diff=0.0) — la lead è bit-perfect
- **Double RMS in mix** è esattamente il 50% dell'originale (-6dB) — le doppie supportano, non competono

**Output atteso:**
```
Original Main  RMS: 0.707107  (expected ~0.707107)
Original Double RMS: 0.353553  (expected ~0.353553)

Main  in mix RMS: 0.707107  (expected ~0.707107)
Double in mix RMS: 0.176777  (expected ~0.176777)

[PASS] Main RMS in mix (0.707107) == Main RMS original (0.707107) (diff=0.000000)
[PASS] Double RMS in mix (0.176777) == Double RMS original * 0.5 (0.176777) (diff=0.000000)

ALL CHECKS PASSED — Gain staging is correct.
```

#### 3. `latency_test.py` — Latenza Ponte DSP→UI

```bash
python latency_test.py
```

Misura il tempo di round-trip da un trigger DSP al ponte UI (evaluate_js di pywebview). Esegue 100 iterazioni dopo 10 di riscaldamento.

**Output atteso:**
```
Warming up (10 iterations)...
Running 100 iterations...

  Iterations : 14
  Min latency: 0.064 ms
  Max latency: 0.509 ms
  Avg latency: 0.158 ms
  Median     : 0.107 ms
  P95        : 0.509 ms
  Target     : < 30.0 ms
  Result     : PASS (avg 0.2ms < 30.0ms)
```

> **Nota:** Il conteggio iterazioni può variare (tipicamente 14-100) perché il test filtra le iterazioni dove la risoluzione del timer ad alta precisione influenza la misurazione. La metrica chiave è **latenza media < 30ms** — il risultato reale è tipicamente **0.03-0.16ms**, ben dentro il target.

#### 4. `ci_validate.py` — Quality Gate CI (Validazione Completa)

```bash
python ci_validate.py
```

Questo è il **punto d'ingresso CI automatizzato**. Esegue:
1. Lancia `verify_gain.py` come sottoprocesso
2. Se PASS: auto-attiva **tutti** i flag sperimentali in `.flags.json`
3. Se FAIL: esce con codice 1 e output diagnostico
4. Riporta lo stato di sistema pronto

**Output atteso:**
```
[Step 1/2] Running gain staging verification...
ALL CHECKS PASSED — Gain staging is correct.

[Step 2/2] Verification PASSED — enabling all feature flags...
[CI] Flags written to .flags.json

[CI] CI VALIDATION: PASS
[CI] System ready — all flags enabled, Neural Monitor online.
```

### Disaccoppiamento UI Asincrono

La pipeline DSP può scatenare dozzine di chiamate `onStep`/`onEvent` al secondo durante un render. Il bridge .NET/COM di pywebview serializza ogni chiamata `evaluate_js` in modo sincrono, il che bloccherebbe la pipeline.

**Soluzione:** Un thread background svuota una `queue.Queue`:

```
Pipeline DSP → queue.put(codice_js) → [CODA] → thread worker → evaluate_js()
                                              │
                                         Throttle 60fps
                                         (intervallo min 16.7ms)
                                              │
                                         Drenaggio entry stale
                                         (evento nuovo sostituisce vecchio)
```

- **Throttle 60fps**: minimo 16.7ms tra eval JS — previene l'allagamento del bridge
- **Drenaggio entry stale**: se un evento più nuovo dello stesso tipo viene accodato prima che il vecchio venga processato, il vecchio viene scartato (es. colpi di compressore rapidi mostrano solo l'ultimo valore)
- **Arresto sentinella**: inserire `None` nella coda ferma il thread worker pulitamente

### Documento di Riferimento

`DSP_ENGINE_SPECS.md` è il regolamento numerico di riferimento. Reconcilia linee guida contrastanti da tre fonti di ingegneria audio (Stavrou, Eargle, Winer) in default risolti singoli:

- **Target gain staging**: -18dBFS RMS (0 VU)
- **Metodo de-esser**: Multibanda 4-8kHz (non broadband)
- **Modelli compressore**: 3 tipi distinti (VCA per bus, FET per drum, Opto per voci)
- **Ordine catena segnale**: HPF → Risonanza → EQ → Comp → De-esser → Limiter
- **Impostazioni compressore per strumento**: Tabella completa con ratio, attack, release, knee per ogni tipo di strumento

### Stato

In sviluppo attivo. Vedi `.omo/` per note di pianificazione e la cronologia dei commit per i progressi.

**Fasi completate:**
- **Fase 0** — Director Mode: checkpoint di approvazione human-in-the-loop, verificato end-to-end attraverso i thread
- **Fase 2** — Catene DSP blueprint (compressione vocale seriale, glue drum, catena basso), calibrazione riverbero RT60
- **Fase 3** — Matching spettrale LTAS contro un brano di riferimento
- **Fase 4** — LLM advisory: modello locale Qwen 2.5 1.5B per classificazione stem ambigui, validato da director_safety.py
- **Fase 5** — GUI: layout a due colonne, avatar SVG con animazioni GSAP e reazioni DSP in tempo reale, console streaming LLM, cylon bar, Neural Monitor A/B live
- **Fase 6** — Packaging PyInstaller: costruito e testato con tutte le dipendenze incluse (llama_cpp, pywebview, sounddevice, modello GGUF). Ancora da testare su macchina pulita.

**Indurimento recente (Luglio 2026):**
- Split bus Vocal_Main / Vocal_Doubles — doppie al 50% (-6dB) così la Main mantiene presenza
- Makeup gain dopo ogni stadio di compressore — previene il calo cumulativo di livello
- Limite warp allineamento elastico ridotto al 2% — elimina artefatti flutter
- Le voci Main/Lead non vengono mai warplate o compensate in livello — sono la griglia temporale
- Neural Monitor riparato: risolto mismatch sample rate WASAPI, aggiunto makeup gain per segnali deboli
- File picker riparato: aggiunta selezione file audio singolo affiancata al selettore cartelle
- Sfondo avatar `motus_base.png` integrato come elemento SVG `<image>`
- **Quality gate CI** (`ci_validate.py`): auto-validazione che lancia `verify_gain.py`, auto-attiva tutti i flag al PASS, esce con 1 al FAIL
- **Evento `system_ready`**: emesso quando il bridge Python si inizializza — innesca un'animazione di accensione a 3 impulsi sul piercing dell'avatar
- **Disaccoppiamento UI asincrono**: thread background basato su `queue.Queue` che svuota le chiamate JS eval così la pipeline DSP non si blocca mai sugli aggiornamenti UI. Throttle 60fps (16.7ms) con drenaggio entry stale
- **Audio a bassa latenza**: `audition.py` ora usa `sd.OutputStream(blocksize=512, latency='low')` invece di `sd.play`/`sd.wait`
- **Test di latenza** (`latency_test.py`): misura il round-trip trigger DSP → ponte UI. Risultato: media **0.158ms** (target: <30ms)

### Problemi Noti e Risoluzione

#### Finestra nera all'avvio

**Sintomo:** La scorciatoia desktop apre una finestra nera che non renderizza mai la UI.

**Causa reale (confermata, risolta):** La classe `Api` in `app/api.py` salvava l'oggetto `Window` di pywebview come attributo **pubblico** (`self.window`). Il meccanismo di introspezione `js_api` di pywebview stesso (`webview/util.py`, `inject_pywebview` → `get_functions`) cammina ricorsivamente *ogni attributo pubblico* dell'istanza `Api` per costruire il bridge `window.pywebview.api` esposto a JS. Camminando dentro `self.window` si finisce nell'oggetto COM `.native` del controllo WinForms/.NET WebView2, e una volta che un software di UI Automation esterno ha "toccato" l'albero di accessibilità di quella finestra (osservato sia con NVIDIA Overlay che, separatamente, con AVG), quel grafo COM contiene una catena genuinamente infinita — `window.native.AccessibilityObject.Bounds.Empty.Empty.Empty...` — per cui il walker di riflessione di pywebview non ha alcun rilevamento di cicli. Il conseguente spam di `RecursionError` affama il message loop di WebView2 al punto che la pagina non finisce mai di caricarsi, e la finestra resta bloccata sul colore di sfondo per sempre, senza nessuna eccezione visibile all'utente.

Uccidere il processo overlay era un workaround precedente (sbagliato) che sembrava "risolvere" il problema per coincidenza — la vera soluzione non dipende da quale software di overlay sia o meno in esecuzione.

**Soluzione (applicata):** Rinominato `Api.window` → `Api._window` sia in `app/api.py` che in `app/main.py`. Il walker di pywebview salta esplicitamente ogni nome di attributo che inizia con `_`, quindi l'oggetto finestra non viene mai introspezionato — nessun grafo COM viene mai attraversato, indipendentemente da quale tooling di UI Automation sia attivo. Verificato riproducendo il fallimento in modo affidabile prima della fix (`last_load.log` mai scritto, console inondata dall'errore di ricorsione), poi confermando caricamenti puliti e ripetibili della pagina immediatamente dopo la rinomina.

**Diagnosi (se mai si ripresentasse):**
1. Controlla `%LOCALAPPDATA%\RedLineEngine\last_load.log` — se mancante o vecchio, la pagina non è mai stata caricata
2. Controlla `%LOCALAPPDATA%\RedLineEngine\startup_error.log` per un'eccezione Python
3. Imposta `REDLINE_DEBUG_GUI=1` per aprire Chrome DevTools insieme alla finestra e ispezionare direttamente la console
4. Se è di nuovo lo stesso bug, significa che è stato aggiunto un nuovo attributo pubblico su `Api` che punta all'oggetto `window` (o a un altro oggetto che alla fine lo referenzia) — controlla `app/api.py` per ogni `self.<nome> = window` e rinominalo con un underscore iniziale

#### Neural Monitor senza audio

**Sintomo:** L'interruttore Neural Monitor è ON ma non esce suono dalle casse.

**Causa (risolta):** Mismatch sample rate WASAPI tra il file audio e il dispositivo di output predefinito. Inoltre, i segnali deboli necessitavano di makeup gain per essere udibili.

**Soluzione (applicata nel commit `8582693`):**
- `audition.py` ora corrisponde al sample rate nativo del dispositivo di output
- Makeup gain aggiunto: target picco 0.85 per segnali deboli
- La normalizzazione di picco assicura che i segnali forti non cliprino

#### File picker non mostra file audio

**Sintomo:** Il selettore file mostra solo cartelle, non file audio individuali.

**Causa (risolta):** L'implementazione originale usava solo la selezione cartelle (`OPEN_DIALOG` con flag `DIRECTORY`).

**Soluzione (applicata nel commit `763c564`):**
- Aggiunto metodo `pick_input_file()` usando `OPEN_DIALOG` con filtri per tipi di file audio
- Sia selezione cartelle che selezione file singolo sono ora disponibili

---

*RedLine Engine — mixing with your mind, mastered by machine.*
