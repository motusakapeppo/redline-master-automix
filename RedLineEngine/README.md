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
| `ENABLE_LLM_ADVISORY` | off | *(planned)* local LLM (llama.cpp) fallback for low-confidence stem naming |
| `ENABLE_DIRECTOR_MODE` | off | *(planned)* human-in-the-loop pause between pipeline stages |

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
- `app/` — pywebview desktop shell (API + web UI)

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
progress. Landed behind flags so far: Fase 2 blueprint DSP chains, Fase 2
RT60 reverb calibration, Fase 3 LTAS spectral matching. Next: LLM advisory
(llama.cpp, local-only), GUI polish, and PyInstaller packaging.
