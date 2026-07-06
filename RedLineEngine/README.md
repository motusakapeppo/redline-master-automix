# RedLineEngine

Standalone automatic mixing and mastering engine. Ingests raw multitrack
stems, classifies each one (role, register, spatial depth), applies a full
DSP mixing chain, then masters the bounce to a loudness target or a
reference track. Designed to run headless (CLI) with a pywebview GUI
planned on top.

## Safety model: feature flags

Every experimental module is **off by default**. Flags live in
`redline/config.py` and are toggled via a local `.flags.json` (gitignored,
machine-local — never committed) or `REDLINE_<FLAG>=1` environment
variables. Golden rule: disabling a flag returns the engine to its exact
pre-feature behavior — no code revert required, no silent regressions.

| Flag | Default | Unlocks |
|---|---|---|
| `ENABLE_BLUEPRINT_CHAINS` | off | Serial vocal compression (FET peak-catcher + Opto leveler), drum bus glue + tape saturation, bass 2-band + harmonic exciter |
| `ENABLE_LTAS_MATCHING` | off | FIR spectral matching (`redline/ltas.py`) against a reference track during mastering |
| `ENABLE_RT60_CALIBRATION` | off | Auto-tunes Room/Plate reverb bus decay from a reference track's onset/decay (`redline/rt60.py`) |
| `ENABLE_LLM_ADVISORY` | off | Local LLM (llama.cpp, `redline/llm_classifier.py`) fallback for low-confidence stem naming, validated through `redline/director_safety.py` |
| `ENABLE_LIVE_AUDITION` | off | Neural Monitor — real dry/wet A/B playback of the master bus glue compression through real speakers (`redline/audition.py`). Toggled live from the GUI switch (runtime-only, via `config.set_override`), not from `.flags.json` |
| `ENABLE_DIRECTOR_MODE` | off | Pauses `render_mix` after stem role/register recognition and waits for GUI approval (`redline/director.py`'s `threading.Event`-based gate) before any DSP runs |

## Architecture

- `redline/naming.py` — regex-based stem role/pan/section detection
- `redline/analyze.py`, `redline/analysis/` — pYIN pitch, VAD-gated analysis, genre detection
- `redline/depth.py` — Z-axis (foreground/midground/background) classification via Crest Factor + spectral flux
- `redline/mixengine.py` — per-stem DSP chain (HPF, resonance cut, compression, de-essing, spatial depth)
- `redline/reverbbus.py` — 3 shared reverb buses (Room/Plate/Hall) instead of per-stem instances
- `redline/masterengine.py` — multiband glue compression, soft-clip, mid/side polish, LUFS targeting, QC loop
- `redline/ltas.py` — reference-track spectral (LTAS) FIR matching, ±2.5dB clamped
- `redline/rt60.py` — reference-track RT60 estimation (onset + decay regression) to calibrate Room/Plate reverb buses
- `redline/qc.py` — automated true-peak/LUFS/mono-correlation check with correction re-render
- `redline/metrics.py` — in-memory per-stage timing (`[METRIC] stage: Xs`)
- `redline/llm_classifier.py` — offline local LLM (`models/qwen2.5-1.5b-instruct-q4_0.gguf` via llama-cpp-python), advisory-only fallback for stems `naming.py` couldn't confidently place, streams tokens for the GUI console
- `redline/director_safety.py` — validates/clamps any LLM-suggested value (stem category, or future DSP param) before it can reach the engine
- `redline/director.py` — Director Mode: `threading.Event`-based gate that pauses `render_mix` for GUI approval mid-pipeline
- `redline/audition.py` — Neural Monitor: sounddevice/PortAudio playback with peak-safety normalization + anti-click fades, and `extract_smart_chunk()` (finds the loudest window instead of comparing arbitrary/silent audio)
- `redline/elastic_align.py` — syllable-level DTW time alignment for vocal doubles (lightweight VocALign alternative). Main/Lead vocals are never warped (name-based guard). Max safe warp limited to 2% to prevent flutter artifacts.
- `redline/leveling.py` — concurrent vocal-take level compensation (power-preserving 1/√N gain for overlapping takes, skips Main/Lead vocals)
- `redline/denoise.py` — spectral noise reduction for vocal cleanup before any DSP
- `app/` — pywebview desktop shell: two-column GSAP-driven UI (`app/web/`), a 3D-shaded SVG avatar (metallic silver jewelry, autonomous idle look-around, real-time reactions to glue compression/de-esser/BPM/LLM state/live A/B audition) alongside a conversational terminal panel. Supports both folder (multitrack stems) and single-file audio selection via native OS dialogs.

## Reference document

`DSP_ENGINE_SPECS.md` is the ground-truth numeric rulebook: it reconciles
conflicting guidance across three audio engineering sources (Stavrou,
Eargle, AudioExpert/Winer) into single resolved defaults — e.g. gain
staging target (-18dBFS RMS), de-esser method (multiband 4-8kHz), the 3
distinct compressor models (VCA/FET/Opto), signal chain order, and a full
per-instrument compressor settings table (§4.1). All blueprint/DSP defaults
should trace back to this doc rather than inventing new numbers.

## Status

Actively developed. See `.omo/` for planning notes and commit history for
progress. Landed behind flags so far: Fase 0 Director Mode (human-in-the-loop
approval checkpoint, verified end-to-end across threads), Fase 2 blueprint
DSP chains, Fase 2 RT60 reverb calibration, Fase 3 LTAS spectral matching,
Fase 4 LLM advisory (verified end-to-end against the real bundled model,
including a real bug caught and fixed where the model echoed the wrong
stem name), Fase 5 GUI (two-column layout, GSAP avatar — a minimalist
line-art "stencil" design with glasses that tint/glow during LLM inference
— streaming console, cylon bar, Neural Monitor live A/B audition). Fase 6
PyInstaller packaging built and launch-tested on this machine multiple
times (`llama_cpp`, `pywebview`, `sounddevice` + the bundled model all
confirmed present and working in the frozen exe); still needs a
clean-machine test on hardware that never had Python installed.

**Recent vocal chain hardening (July 2026):**
- Vocal_Main/Vocal_Doubles bus split: doubles scaled to 50% (-6dB) so the lead keeps presence
- Makeup gain after every compressor stage to prevent cumulative level drop
- Elastic align warp limit reduced to 2% to eliminate flutter artifacts
- Main/Lead vocals are never warped or level-compensated — they are the timing grid
- Neural Monitor (live A/B audition) fixed: WASAPI sample rate mismatch resolved, makeup gain added for quiet signals

**Known external conflict, not a bug in this app:** if the desktop shortcut
(`Avvia RedLine Engine.vbs`) opens a black/blank window that never renders,
it's very likely **NVIDIA Overlay** (or a similar UI-Automation-hooking
overlay — Discord overlay, RTSS, Xbox Game Bar) intercepting the new window
and triggering an infinite recursion inside pywebview's .NET/COM bridge
(`RecursionError` walking `window.native.AccessibilityObject.Bounds.Empty...`),
which starves the WebView2 message loop badly enough that the page never
finishes loading. Confirmed by killing the NVIDIA Overlay process and
watching the app load normally within seconds. Fix: disable the in-game/
in-app overlay for the relevant software, or exclude `RedLineEngine.exe`
from it. `app/main.py` writes `%LOCALAPPDATA%\RedLineEngine\last_load.log`
the moment the page actually finishes loading — if that file is missing or
stale after a launch attempt, the page genuinely never loaded (this class
of issue); if it's fresh, the blackness has a different cause. Set
`REDLINE_DEBUG_GUI=1` to open DevTools alongside the window for further
diagnosis.
