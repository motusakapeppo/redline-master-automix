# RedLine — automatic mix + mastering engine

Status snapshot as of **2026-07-06**. This file is kept up to date as the project moves — treat it as the current state of things, not a static intro.

## What this is

A tool that takes vocal + instrumental stems (or full multitrack stems, or a single already-mixed file) from a real song and produces an automatic mix and, optionally, an automatic master — detecting genre/BPM/key on its own, asking a few simple questions about the sound you want, and explaining what it's doing as it works, in an app you double-click (no DAW, no VST, no CLI required).

Two things live in this repo:

- **`RedLineEngine/`** — the active project.
- **`AutoMixerVST/`** — the original JUCE VST3/AU plugin attempt. **Dormant.** It had its core mastering logic silently disconnected from the actual audio (computed EQ/dynamics per genre that never touched the signal) — full findings are in project memory. Real VST/DAW integration will come back as a later phase, built on top of the RedLineEngine engine instead of restarting from this code.

## Current state of RedLineEngine

### Works today

**Input** — point it at one folder or file and it figures out the right mode: a folder with a pre-mixed instrumental + a "vocals stems" subfolder full of takes (a real production session layout), a folder of arbitrary named stems, or a single mixed file (auto-separated via Demucs). Own output files (`mix.wav`/`master.wav`) are excluded from being re-ingested as input stems even if an output folder ends up nested inside the project folder.

**Naming-aware stem recognition** — reads role (vocal/bass/drums/other), take layer (lead "Main" vs "Double"/harmony), stereo pan (`dx`/`sx`), section (verse/chorus) and register hints straight from how *you* named your files and folders, English and Italian both. Validated against a real 24-file vocal production session.

**Analysis** — BPM, musical key, genre (crest factor + measured sub-bass ratio + rhythmic transient density as a tie-breaker), integrated LUFS, spectral balance. A "bass"-named stem without real measured sub-bass content gets corrected to "other" instead of trusted blindly.

**Mixing** — lead vocals are treated as actually lead, doubles as actually support, not one generic "vocal" treatment:
- Lead ("Main") vocal: high-pass cutoff tracks its own measured fundamental (no fixed 100Hz that guts a baritone/bass voice), a presence boost, section-aware (a chorus take gets a touch more lift than a verse take).
- Vocal doubles/stacks are routed through a **Backing Vocals bus with four register sub-buses** (Low/Unison/High/Falsetto), each with its own recipe — a wall of doubles only reads as one big, defined thing if each register actually gets different treatment. Register is classified from each double's own measured pitch (YIN) relative to the lead, not trusted from the file name. Doubles are time-aligned to the lead first via cross-correlation (mass phase control — summing several takes of the same singer/mic without this causes real comb-filtering). Lows get narrow panning + heavy flat compression for weight; Unisons get pushed fully hard L/R with an aggressive de-esser (several unaligned "S"s at once is a classic amateur-mix tell); Highs get hard high-passed + a touch of saturation to cut through; Falsettos additionally get sent to a long reverb so they read as a diffuse cloud.
- Concurrent-take level compensation: when several lead takes are active at once (alternate lines/ad-libs), power-preserving gain compensation keeps them from silently stacking level.
- Adaptive resonance suppression (cuts only where a stem's own energy actually piles up, measured per stem) and an adaptive de-esser (detects each stem's real sibilance frequency instead of assuming 5-9kHz).
- Preventive masking cut: instrumental stems that structurally pile up energy in the vocal's 2-5kHz presence band get a measured static cut, sized by the actual overlap.
- Spectral (not broadband) vocal ducking — only the ~1-4kHz band the vocal occupies gets pulled back in the instrumental/drums, avoiding audible "pumping" — plus a separate, faster, broadband kick/bass sidechain (the classic low-end "pumping" trick, distinct from the vocal duck).
- Instrumental ("other") stems are grouped into a Music bus with Mid/Side EQ (mono dip in the presence band, side-channel width boost).
- A short send-style reverb + BPM-synced delay on the lead vocal (genre/aggressiveness-informed amount, more space on chorus than verse), a subtle room send on drums.
- A parallel (New York-style) compression bus for vocal+drums for weight without crushing transients, genre-informed bus EQ + glue compression, and a wizard (aggressiveness / warmth / vocal prominence / genre override / mastering on-off).

**Mastering** — platform-aware LUFS targeting (Spotify/Apple/YouTube/club), true **3-band multiband glue compression** (low/mid/high, each with its own gentle recipe), a transparent soft-clip stage before the final limiter (preserves more punch than limiting alone), Mid/Side polish (mono bass below 120Hz, side-channel air shelf for width), true-peak limiting, and an automated **QC pass** — measures LUFS/true peak/mono compatibility/spectral balance against an approximate genre reference shape, applies one bounded corrective EQ nudge if something's off, re-normalizes loudness afterward, and always reports the final numbers (never silently claims "perfect"). Reference-track matching via `matchering` is also available.

**Desktop app** (`RedLineEngine/app/`) — a pywebview window with an animated "studio rack" (EQ curve, gain-reduction meter, de-esser frequency dial, a listening/QC indicator, a scrolling event feed, and a first-pass animated assistant character) that reacts to the *actual* values the engine computes for that render, not a generic looping animation. Double-click launcher (`Avvia RedLine Engine.vbs`) starts it cleanly with no visible console.

**Packaged as a standalone `.exe`** — `build_exe.py` (PyInstaller) produces `dist/RedLineEngine/RedLineEngine.exe`, verified launching correctly standalone (no dev venv, no Python installation needed on the target machine).

**Optional local LLM stem-classification fallback** (`llm_classifier.py`) — a small, fully offline, Apache-2.0-licensed model (Qwen2.5-1.5B-Instruct, GGUF, downloaded separately into `models/`, not committed) as an *advisory* cross-check for stems the naming heuristic can't confidently place — never silently overrides the DSP path a stem gets. Verified integration is correct, but inactive on this specific development machine: its 12th-gen Intel CPU has AVX-512 fused off (known Alder Lake retail behavior) and the prebuilt llama-cpp-python wheel's kernels hit an illegal-instruction crash at load regardless of quantization — confirmed to fail as a catchable exception, so the pipeline degrades gracefully and works exactly as before with this layer simply inactive.

32 automated tests (`pytest RedLineEngine/tests/`), all green, plus multiple real bugs found and fixed via repeated full renders on a real 24-stem project (own-output-file contamination on repeat runs, a QC loudness-drift bug, a stale true-peak value in the QC report).

### Known gaps / honest limitations
- The per-genre spectral target shapes the QC pass checks against, and the vocal-register pitch-ratio classification thresholds, are approximate/heuristic — not certified references. On the real test project, some doubles' register classification looked inconsistent with their file names (e.g. a "Low"-named take classified as "falsetto") — the pitch tracker's octave estimation needs more validation against a wider range of real material.
- Third-party VST3 hosting (TDR Nova/Kotelnikov, Analog Obsession, Valhalla Supermassive) was considered and intentionally not implemented: correctly automating unfamiliar plugins' exact parameters without being able to open their GUI to verify risks silently-wrong automation, separate from the licensing question.
- The animated assistant character is a first-pass SVG/CSS build (no Rive editor access in this environment) — meant as a starting point per an explicit "I'll redo it if I don't like it" from the user, not a final design.

### Not yet done
VST/AU real-time DAW integration (deliberately deferred until the offline engine is solid).

## Running it

```
cd RedLineEngine
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python app\main.py     # desktop app (dev mode)
# or build the standalone exe:
.venv\Scripts\python build_exe.py    # produces dist/RedLineEngine/RedLineEngine.exe
# or, for development/debugging:
.venv\Scripts\python -m redline.cli --folder "path\to\project" --out "path\to\output"
```

## Repo/workflow notes

- Private remote: `github.com/motusakapeppo/redline-master-automix`. Commits are pushed here after every substantive change (local commits alone aren't considered "safe" — see project memory).
- This machine's AVG Antivirus intercepts TLS, so `pip`/`git push`/model downloads need `--cert`/`GIT_SSL_CAINFO`/`SSL_CERT_FILE` pointed at `C:\ProgramData\AVG\Antivirus\wscert.pem` rather than a system-trusted cert.
