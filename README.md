# RedLine — automatic mix + mastering engine

Status snapshot as of **2026-07-05**. This file is kept up to date as the project moves — treat it as the current state of things, not a static intro.

## What this is

A tool that takes vocal + instrumental stems (or full multitrack stems, or a single already-mixed file) from a real song and produces an automatic mix and, optionally, an automatic master — detecting genre/BPM/key on its own, asking a few simple questions about the sound you want, and explaining what it's doing as it works.

Two things live in this repo:

- **`RedLineEngine/`** — the active project. A Python engine + a standalone desktop app (no DAW, no VST needed).
- **`AutoMixerVST/`** — the original JUCE VST3/AU plugin attempt. **Dormant.** It had its core mastering logic silently disconnected from the actual audio (computed EQ/dynamics per genre that never touched the signal) — full findings are in project memory. Real VST/DAW integration will come back as a later phase, built on top of the RedLineEngine engine instead of restarting from this code.

## Current state of RedLineEngine

### Works today
- **Input**: point it at one folder or file and it figures out the right mode —
  a folder with a pre-mixed instrumental + a "vocals stems" subfolder full of takes (exactly a real production session layout), a folder of arbitrary named stems, or a single mixed file (auto-separated via Demucs).
- **Naming-aware stem recognition**: reads role (vocal/bass/drums/other), take layer (lead "Main" vs "Double"/harmony), stereo pan (`dx`/`sx`), section (verse/chorus) and register (falsetto/low/mid) straight from how *you* named your files and folders — English and Italian both. Validated against a real 24-file vocal production session, not just synthetic examples.
- **Analysis**: BPM, musical key, genre (rule-based, informed by real measured sub-bass ratio and crest factor — not a hardcoded placeholder like the old plugin), integrated LUFS, spectral balance.
- **Mixing**: per-stem high-pass/mud-carve + compression by role, band-split de-esser on vocals, sidechain ducking of the instrumental bed under the vocal, vocal doubles panned hard L/R under the lead, genre-informed bus EQ + glue compression, a wizard (aggressiveness / warmth / vocal prominence / genre override / mastering on-off).
- **Mastering**: platform-aware LUFS targeting (Spotify/Apple/YouTube/club), true-peak limiting, optional reference-track matching via `matchering`.
- **Desktop app** (`RedLineEngine/app/`): a pywebview window (dark theme, live narration log, simple animated progress) wrapping the engine — not yet packaged into a standalone `.exe`.
- 10 automated tests (`pytest RedLineEngine/tests/`), all green — covering naming edge cases, de-essing, input auto-detection, and an end-to-end pipeline smoke test that fails if a stage silently becomes a no-op (the exact class of bug the old plugin had).

### Known gaps (being worked through — see plan for order)
Honest self-assessment, not marketing: today's mix is a solid automatic rough-mix/pre-master, not yet a professional-grade one. Missing, in rough priority order:
1. No reverb/delay (no sense of space/depth)
2. No handling of multiple simultaneous vocal takes' level buildup
3. EQ de-masking is generic-per-genre, not driven by which specific stems are actually clashing in this song
4. Mastering is single-band gain + limiter, not multiband + stereo width + saturation
5. No automated post-render QC pass that measures the result and corrects it
6. Song section (verse/chorus — already parsed from file names) doesn't yet vary the treatment
7. Not yet packaged as a standalone `.exe`

### Not yet done
VST/AU real-time DAW integration (deliberately deferred until the offline engine is solid).

## Running it

```
cd RedLineEngine
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python app\main.py     # desktop app
# or, for development/debugging:
.venv\Scripts\python -m redline.cli --folder "path\to\project" --out "path\to\output"
```

## Repo/workflow notes

- Private remote: `github.com/motusakapeppo/redline-master-automix`. Commits are pushed here after every substantive change (local commits alone aren't considered "safe" — see project memory).
- This machine's AVG Antivirus intercepts TLS, so `pip`/`git push` need `--cert`/`GIT_SSL_CAINFO` pointed at `C:\ProgramData\AVG\Antivirus\wscert.pem` rather than a system-trusted cert.
