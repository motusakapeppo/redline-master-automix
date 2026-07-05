# RedLine — automatic mix + mastering engine

Status snapshot as of **2026-07-06**. This file is kept up to date as the project moves — treat it as the current state of things, not a static intro.

## What this is

A tool that takes vocal + instrumental stems (or full multitrack stems, or a single already-mixed file) from a real song and produces an automatic mix and, optionally, an automatic master — detecting genre/BPM/key on its own, asking a few simple questions about the sound you want, and explaining what it's doing as it works.

Two things live in this repo:

- **`RedLineEngine/`** — the active project. A Python engine + a standalone desktop app (no DAW, no VST needed).
- **`AutoMixerVST/`** — the original JUCE VST3/AU plugin attempt. **Dormant.** It had its core mastering logic silently disconnected from the actual audio (computed EQ/dynamics per genre that never touched the signal) — full findings are in project memory. Real VST/DAW integration will come back as a later phase, built on top of the RedLineEngine engine instead of restarting from this code.

## Current state of RedLineEngine

### Works today
- **Input**: point it at one folder or file and it figures out the right mode —
  a folder with a pre-mixed instrumental + a "vocals stems" subfolder full of takes (exactly a real production session layout), a folder of arbitrary named stems, or a single mixed file (auto-separated via Demucs). Own output files (`mix.wav`/`master.wav`) are excluded from being re-ingested as input stems even if an output folder ends up nested inside the project folder.
- **Naming-aware stem recognition**: reads role (vocal/bass/drums/other), take layer (lead "Main" vs "Double"/harmony), stereo pan (`dx`/`sx`), section (verse/chorus) and register (falsetto/low/mid) straight from how *you* named your files and folders — English and Italian both. Validated against a real 24-file vocal production session, not just synthetic examples.
- **Analysis**: BPM, musical key, genre (crest factor + real measured sub-bass ratio + rhythmic transient density as a tie-breaker), integrated LUFS, spectral balance. A "bass"-named stem without real measured sub-bass content gets corrected to "other" instead of trusted blindly.
- **Mixing** — lead vocals are treated as actually lead, doubles as actually support:
  - Lead ("Main") vocal: high-pass cutoff tracks its own measured fundamental (no fixed 100Hz that guts a baritone/bass voice) + a presence boost.
  - Doubles/harmonies: time-aligned to the lead via cross-correlation first (so they reinforce instead of smearing it), then thinned, pulled back in the air band, hard-panned per `dx`/`sx`, and gain-reduced — clearly secondary.
  - Adaptive resonance suppression (cuts only where a stem's own energy actually piles up, measured per stem — not a fixed always-on mud cut) and an adaptive de-esser (detects each stem's actual sibilance frequency instead of assuming 5-9kHz).
  - Spectral (not broadband) sidechain ducking: only the ~1-4kHz band the vocal occupies gets pulled back in the instrumental/drums, avoiding audible "pumping".
  - A parallel (New York-style) compression bus for vocal+drums for weight without crushing transients, genre-informed bus EQ + glue compression, and a wizard (aggressiveness / warmth / vocal prominence / genre override / mastering on-off).
- **Mastering**: platform-aware LUFS targeting (Spotify/Apple/YouTube/club), a transparent soft-clip stage before the final limiter (preserves more punch than limiting alone), Mid/Side polish (mono bass below 120Hz, side-channel air shelf for width), true-peak limiting, and an automated **QC pass** — measures LUFS/true peak/mono compatibility/spectral balance against an approximate genre reference shape, applies one bounded corrective EQ nudge if something's off, re-normalizes loudness afterward, and always reports the final numbers (never silently claims "perfect"). Reference-track matching via `matchering` is also available.
- **Desktop app** (`RedLineEngine/app/`): a pywebview window with an animated "studio rack" (EQ curve, gain-reduction meter, de-esser frequency dial, a "listening"/QC headphones indicator, and a scrolling event feed) that reacts to the *actual* values the engine computes for that render — not a generic looping animation. Double-click launcher (`Avvia RedLine Engine.vbs`) starts it cleanly with no visible console.
- 20 automated tests (`pytest RedLineEngine/tests/`), all green, plus two real bugs found and fixed via an actual full render on the user's real 24-stem project (own-output-file contamination on repeat runs, and a QC loudness-drift bug) — not yet packaged into a standalone `.exe`.

### Known gaps (being worked through — see plan for order)
Honest self-assessment, not marketing: still not literally "always perfect" (no automated system can promise that), but the professional-grade gaps identified after the first real render are now largely addressed. What's left:
1. Reverb/delay (no sense of space/depth) — not yet implemented.
2. The per-genre spectral target shapes the QC pass checks against are approximate, not a certified mastering-reference curve.
3. Not yet packaged as a standalone `.exe` (runs today via `python app/main.py` or the `.vbs` launcher).

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
