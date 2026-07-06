# RedLine Engine

> **Automatic mixing & mastering engine** — professional-grade DSP pipeline for multitrack audio, with a pywebview desktop GUI and a real-time animated avatar that reacts to every compressor hit, de-esser flash, and BPM change.

---

## English 🇬🇧

### Overview

RedLine Engine is a standalone automatic mixing and mastering system. It ingests raw multitrack stems (or a single mixed file), classifies each stem by role, register, and spatial depth, applies a full DSP mixing chain with per-stem processing, then masters the final bounce to a loudness target or a reference track.

**Key design principles:**
- **The lead vocal is the star** — full-range, centered, presence-boosted, minimally processed. Doubles and harmonies support at 50% level (-6dB) so the lead never loses presence.
- **Main/Lead vocals are the timing grid** — never warped by elastic alignment, never attenuated by level compensation.
- **Safety over cleverness** — every experimental module is off by default behind feature flags. Disabling a flag is a complete, instant rollback.
- **Measured, not guessed** — EQ cuts, compression ratios, reverb amounts are all computed from actual audio measurements (fundamental frequency, crest factor, spectral centroid, RMS energy), not from static presets.

### Feature Flags

Every experimental module is **off by default**. Flags are stored in `redline/config.py` and toggled via a local `.flags.json` file (gitignored, machine-local) or `REDLINE_<FLAG>=1` environment variables.

| Flag | Default | What it unlocks |
|---|---|---|
| `ENABLE_BLUEPRINT_CHAINS` | off | Serial vocal compression (FET peak-catcher + Opto leveler), drum bus glue + tape saturation, bass 2-band split + harmonic exciter |
| `ENABLE_LTAS_MATCHING` | off | FIR spectral matching (`redline/ltas.py`) against a reference track during mastering |
| `ENABLE_RT60_CALIBRATION` | off | Auto-tunes Room/Plate reverb bus decay from a reference track's onset/decay analysis (`redline/rt60.py`) |
| `ENABLE_LLM_ADVISORY` | off | Local LLM (llama.cpp, `redline/llm_classifier.py`) fallback for low-confidence stem naming, validated through `redline/director_safety.py` |
| `ENABLE_LIVE_AUDITION` | off | Neural Monitor — real dry/wet A/B playback of the master bus glue compression through your speakers (`redline/audition.py`). Toggled live from the GUI switch |
| `ENABLE_DIRECTOR_MODE` | off | Pauses `render_mix` after stem role/register recognition and waits for GUI approval (`redline/director.py`) before any DSP runs |

### Architecture

#### Core DSP (`redline/`)

| Module | What it does |
|---|---|
| `naming.py` | Regex-based stem role, pan, and section detection from file names |
| `analyze.py` + `analysis/` | pYIN pitch estimation, VAD-gated analysis, genre detection, spectral profiling |
| `depth.py` | Z-axis classification (foreground / midground / background) via Crest Factor + spectral flux |
| `mixengine.py` | **The heart of the mix.** Per-stem DSP chain: adaptive HPF tracking the vocal's measured fundamental, resonance suppression, role-specific compression with automatic makeup gain, de-essing, spatial depth staging. Creates separate Vocal_Main and Vocal_Doubles buses (doubles at 50% level). Spectral ducking, kick/bass sidechain, Mid/Side music bus, parallel NY compression. |
| `masterengine.py` | Multiband glue compression (low/mid/high split), soft-clip limiting, mid/side polish, LUFS targeting per platform, automated QC loop with correction re-render |
| `elastic_align.py` | Syllable-level DTW time alignment for vocal doubles. **Main/Lead vocals are never warped** (name-based guard). Max safe warp limited to **2%** — if DTW needs more stretch, the window is skipped entirely to prevent flutter artifacts. |
| `leveling.py` | Power-preserving gain compensation (1/√N) for overlapping vocal takes. **Skips Main/Lead vocals** — only applied to doubles/adlibs. |
| `alignment.py` | Cross-correlation sample-precise alignment of doubles to the lead reference |
| `deesser.py` | Multiband de-esser (4-8kHz) with adaptive threshold per register |
| `resonance.py` | Adaptive resonance detection and suppression in the mud range |
| `masking.py` | Preventive masking cut: measures spectral overlap between instruments and the vocal's presence band |
| `denoise.py` | Spectral noise reduction applied before any other DSP (so compression/EQ don't raise the noise floor) |
| `reverbbus.py` | 3 shared reverb buses (Room / Plate / Hall) instead of per-stem instances — saves CPU and creates a cohesive space |
| `fxsends.py` | Genre-aware reverb/delay send amounts, BPM-synced delay, drum room send |
| `vocalstack.py` | Register classification (Low / Unison / High / Falsetto) with per-register processing recipes — a wall of doubles reads as one big, defined thing |
| `ltas.py` | Long-Term Average Spectrum matching via FIR filter, ±2.5dB clamped |
| `rt60.py` | Onset + decay regression to estimate RT60 from a reference track |
| `qc.py` | True-peak / LUFS / mono-compatibility check with automatic correction re-render |
| `audition.py` | **Neural Monitor** — live A/B playback through real speakers via sounddevice/PortAudio. Peak-safety normalization, anti-click fade in/out, makeup gain for quiet signals. |
| `llm_classifier.py` | Offline local LLM (Qwen 2.5 1.5B, GGUF quantized) for ambiguous stem classification, streams tokens live to the GUI |
| `director_safety.py` | Validates and clamps any LLM-suggested value before it reaches the engine |
| `director.py` | `threading.Event`-based gate that pauses `render_mix` for GUI approval mid-pipeline |
| `config.py` | Feature flag system with `.flags.json` + environment variable overrides |
| `metrics.py` | In-memory per-stage timing instrumentation (`[METRIC] stage: Xs`) |
| `dsp_utils.py` | Shared DSP utilities: envelope follower, duck gain curves, band gain curves, saturation, panning, Mid/Side encoding/decoding |

#### GUI (`app/`)

| Module | What it does |
|---|---|
| `main.py` | pywebview desktop entry point. Creates the window, loads the web UI, writes a load-confirmation marker for black-window diagnostics |
| `api.py` | Thin bridge between the web UI and the engine. Exposes `pick_input_path()`, `pick_input_file()`, `run_pipeline()`, `toggle_neural_monitor()`, `approve_director_checkpoint()` to JavaScript |
| `web/index.html` | Two-column layout: workflow screens on the left, avatar + terminal on the right |
| `web/app.js` | GSAP-driven animations, avatar reactions (de-esser → nose piercing flash, glue compression → earring jingle, BPM → headbang), QC canvas, cylon bar, Director Mode checkpoint, LLM streaming console |
| `web/style.css` | Dark industrial theme (#0A0A0A background, #FF003F accent), rack modules, terminal panel, glitch animations |
| `web/vendor/gsap.min.js` | Vendored GreenSock Animation Platform for smooth, performant UI animations |

The avatar is a minimalist SVG wireframe with:
- **Glasses** that tint and glow during LLM inference ("deep scan" mode)
- **Nose piercing** that flashes red when the de-esser fires
- **Earrings** that jingle on every compressor hit, with extra kick from glue compression
- **Headphones** that fade in during "listening" moments (denoise, LTAS matching, QC)
- **Idle breathing** and autonomous random look-around (GSAP-driven 3D head turns)
- **BPM-synced headbang** once the engine has analyzed the tempo

### Vocal Chain Design

The vocal processing chain is the most carefully engineered part of the system:

1. **Denoise** — spectral noise reduction first, before any other processing
2. **Adaptive HPF** — tracks the vocal's measured fundamental frequency (not a fixed 100Hz that would gut a baritone)
3. **Resonance suppression** — cuts only where energy actually piles up in the mud range
4. **Presence boost** — +1.5dB at 3kHz, with section-aware variation (chorus gets +0.7dB more, verse gets -0.3dB)
5. **Compression** — role-specific with automatic makeup gain. Blueprint mode enables serial 2-stage (FET peak catcher + Opto leveler)
6. **De-esser** — multiband 4-8kHz, register-adaptive threshold
7. **Vocal_Main bus** — all lead takes summed into one coherent entity
8. **Vocal_Doubles bus** — all backing vocals summed, glued, then scaled to **50%** of Main level
9. **Space** — genre-aware reverb + BPM-synced delay, section-adaptive (chorus opens up, verse stays intimate)
10. **Spectral ducking** — only the 1-4kHz band is pulled back in the instrumental when the vocal is active

### Safety & Guardrails

- **Main/Lead vocals are never warped** by elastic alignment (name-based guard in `elastic_align.py`)
- **Main/Lead vocals are never attenuated** by level compensation (skipped in `leveling.py`)
- **Elastic warp limited to 2%** — if DTW needs more stretch, the window is skipped
- **Energy-based guard** in elastic align: if the "lead" signal has less than 60% of the double's RMS energy, the function bails out (likely swapped arguments)
- **Makeup gain after every compressor** — prevents cumulative 6-12dB level drop across serial compression stages
- **Peak safety ceiling** at -1dBFS on the mix bus
- **Neural Monitor** has peak normalization and anti-click fades so a DSP bug can never blast the speakers
- **All try-except wrapped** — a missing audio device, a failed LLM inference, or a librosa error never takes down the render

### Reference Document

`DSP_ENGINE_SPECS.md` is the ground-truth numeric rulebook. It reconciles conflicting guidance across three audio engineering sources (Stavrou, Eargle, Winer) into single resolved defaults — gain staging target (-18dBFS RMS), de-esser method (multiband 4-8kHz), the 3 distinct compressor models (VCA/FET/Opto), signal chain order, and a full per-instrument compressor settings table.

### Status

Actively developed. See `.omo/` for planning notes and commit history for progress.

**Completed phases:**
- **Fase 0** — Director Mode: human-in-the-loop approval checkpoint, verified end-to-end across threads
- **Fase 2** — Blueprint DSP chains (serial vocal comp, drum glue, bass chain), RT60 reverb calibration
- **Fase 3** — LTAS spectral matching against a reference track
- **Fase 4** — LLM advisory: local Qwen 2.5 1.5B model for ambiguous stem classification, validated through director_safety.py
- **Fase 5** — GUI: two-column layout, GSAP-driven SVG avatar with real-time DSP reactions, streaming LLM console, cylon bar, Neural Monitor live A/B audition
- **Fase 6** — PyInstaller packaging: built and launch-tested with all dependencies bundled (llama_cpp, pywebview, sounddevice, the GGUF model). Still needs a clean-machine test.

**Recent vocal chain hardening (July 2026):**
- Vocal_Main / Vocal_Doubles bus split — doubles at 50% (-6dB) so the lead keeps presence
- Makeup gain after every compressor stage — prevents cumulative level drop
- Elastic align warp limit reduced to 2% — eliminates flutter artifacts
- Main/Lead vocals are never warped or level-compensated — they are the timing grid
- Neural Monitor fixed: WASAPI sample rate mismatch resolved, makeup gain added for quiet signals
- File picker fixed: added single-file audio selection alongside folder picker
- `motus_base.png` avatar background integrated as SVG `<image>` element

### Known Issues

**Black/blank window on launch:** If the desktop shortcut opens a black window that never renders, it's very likely **NVIDIA Overlay** (or a similar UI-Automation-hooking overlay — Discord overlay, RTSS, Xbox Game Bar) intercepting the new window and triggering an infinite recursion inside pywebview's .NET/COM bridge. Confirmed by killing the NVIDIA Overlay process and watching the app load normally within seconds.

**Diagnosis:** `app/main.py` writes `%LOCALAPPDATA%\RedLineEngine\last_load.log` the moment the page finishes loading. If that file is missing or stale after a launch attempt, the page genuinely never loaded. If it's fresh, the blackness has a different cause. Set `REDLINE_DEBUG_GUI=1` to open DevTools alongside the window.

**Fix:** Disable the in-game/in-app overlay for the relevant software, or exclude `RedLineEngine.exe` from it.

---

## Italiano 🇮🇹

### Panoramica

RedLine Engine è un sistema automatico di mixing e mastering standalone. Ingestisce stem grezzi multitraccia (o un singolo file già mixato), classifica ogni stem per ruolo, registro e profondità spaziale, applica una catena DSP completa di mixing con elaborazione per-stem, e infine masterizza il risultato verso un target di loudness o un brano di riferimento.

**Principi di design fondamentali:**
- **La voce principale (Main) è la star** — full-range, centrata, con presenza accentuata, elaborazione minima. Doppie e armonie supportano al 50% (-6dB) così la Main non perde mai presenza.
- **Le voci Main/Lead sono la griglia temporale** — mai warplate dall'allineamento elastico, mai attenuate dalla compensazione di livello.
- **La sicurezza prima dell'ingegno** — ogni modulo sperimentale è disabilitato di default dietro flag. Disabilitare un flag è un rollback istantaneo e completo.
- **Misurato, non ipotizzato** — tagli EQ, ratio di compressione, quantità di riverbero sono calcolati da misurazioni audio reali (frequenza fondamentale, crest factor, centroide spettrale, RMS), non da preset statici.

### Flag Sperimentali

Ogni modulo sperimentale è **disabilitato di default**. I flag sono in `redline/config.py` e si attivano via `.flags.json` (gitignorato, locale alla macchina) o variabili d'ambiente `REDLINE_<FLAG>=1`.

| Flag | Default | Cosa sblocca |
|---|---|---|
| `ENABLE_BLUEPRINT_CHAINS` | off | Compressione vocale seriale (FET peak-catcher + Opto leveler), glue drum bus + saturazione nastro, basso 2-band + harmonic exciter |
| `ENABLE_LTAS_MATCHING` | off | Matching spettrale FIR (`redline/ltas.py`) contro un brano di riferimento durante il mastering |
| `ENABLE_RT60_CALIBRATION` | off | Calibrazione automatica del decadimento dei bus Riverbero Room/Plate dall'analisi onset/decay di un riferimento (`redline/rt60.py`) |
| `ENABLE_LLM_ADVISORY` | off | LLM locale (llama.cpp, `redline/llm_classifier.py`) per classificazione stem ambigui, validato da `redline/director_safety.py` |
| `ENABLE_LIVE_AUDITION` | off | Neural Monitor — ascolto A/B dry/wet in tempo reale della glue compression del master bus attraverso le casse (`redline/audition.py`). Attivabile live dall'interruttore GUI |
| `ENABLE_DIRECTOR_MODE` | off | Mette in pausa `render_mix` dopo il riconoscimento ruolo/registro e aspetta approvazione GUI (`redline/director.py`) prima di qualsiasi elaborazione DSP |

### Architettura

#### DSP Core (`redline/`)

| Modulo | Cosa fa |
|---|---|
| `naming.py` | Riconoscimento ruolo, pan e sezione degli stem tramite regex dai nomi file |
| `analyze.py` + `analysis/` | Stima pitch pYIN, analisi VAD-gated, rilevamento genere, profilazione spettrale |
| `depth.py` | Classificazione asse Z (primo piano / centro / sfondo) via Crest Factor + flusso spettrale |
| `mixengine.py` | **Il cuore del mix.** Catena DSP per-stem: HPF adattivo che segue la fondamentale misurata della voce, soppressione risonanze, compressione ruolo-specifica con makeup gain automatico, de-esser, profondità spaziale. Crea bus separati Vocal_Main e Vocal_Doubles (doppie al 50%). Ducking spettrale, sidechain kick/basso, bus musicale Mid/Side, compressione parallela NY. |
| `masterengine.py` | Compressione glue multibanda (split low/mid/high), soft-clip limiting, polish mid/side, targeting LUFS per piattaforma, loop QC automatico con correzione e re-render |
| `elastic_align.py` | Allineamento temporale sillabico via DTW per doppie vocali. **Le voci Main/Lead non vengono mai warplate** (guardia basata sul nome). Warp massimo limitato al **2%** — se DTW richiede più stiramento, la finestra viene saltata per prevenire artefatti flutter. |
| `leveling.py` | Compensazione di gain a potenza costante (1/√N) per take vocali sovrapposti. **Salta le voci Main/Lead** — applicato solo a doppie/adlib. |
| `alignment.py` | Allineamento cross-correlation sample-precise delle doppie al riferimento lead |
| `deesser.py` | De-esser multibanda (4-8kHz) con soglia adattiva per registro |
| `resonance.py` | Rilevamento e soppressione adattiva delle risonanze nella fascia mud |
| `masking.py` | Taglio preventivo di mascheramento: misura la sovrapposizione spettrale tra strumenti e la banda di presenza della voce |
| `denoise.py` | Riduzione rumore spettrale applicata prima di qualsiasi altro DSP (così compressione/EQ non alzano il rumore di fondo) |
| `reverbbus.py` | 3 bus riverbero condivisi (Room / Plate / Hall) invece di istanze per-stem — risparmia CPU e crea uno spazio coeso |
| `fxsends.py` | Quantità di riverbero/delay in base al genere, delay sincronizzato al BPM, drum room send |
| `vocalstack.py` | Classificazione registro (Low / Unison / High / Falsetto) con ricette di elaborazione per registro — un muro di doppie suona come un'entità definita |
| `ltas.py` | Matching Long-Term Average Spectrum via filtro FIR, clampato ±2.5dB |
| `rt60.py` | Regressione onset + decay per stimare RT60 da un brano di riferimento |
| `qc.py` | Controllo true-peak / LUFS / compatibilità mono con correzione automatica e re-render |
| `audition.py` | **Neural Monitor** — ascolto A/B live attraverso le casse via sounddevice/PortAudio. Normalizzazione di picco, fade in/out anti-click, makeup gain per segnali deboli. |
| `llm_classifier.py` | LLM locale offline (Qwen 2.5 1.5B, quantizzato GGUF) per classificazione stem ambigui, stream di token live verso la GUI |
| `director_safety.py` | Valida e clamp qualsiasi valore suggerito dall'LLM prima che raggiunga il motore |
| `director.py` | Gate basato su `threading.Event` che mette in pausa `render_mix` per approvazione GUI a metà pipeline |
| `config.py` | Sistema di flag con `.flags.json` + override da variabili d'ambiente |
| `metrics.py` | Strumentazione timing in-memory per stadio (`[METRIC] stage: Xs`) |
| `dsp_utils.py` | Utility DSP condivise: envelope follower, curve di gain duck, curve di gain per banda, saturazione, panning, codifica/decodifica Mid/Side |

#### GUI (`app/`)

| Modulo | Cosa fa |
|---|---|
| `main.py` | Punto d'ingresso pywebview desktop. Crea la finestra, carica la UI web, scrive un marker di conferma caricamento per diagnostica finestra nera |
| `api.py` | Ponte sottile tra UI web e motore. Espone `pick_input_path()`, `pick_input_file()`, `run_pipeline()`, `toggle_neural_monitor()`, `approve_director_checkpoint()` a JavaScript |
| `web/index.html` | Layout a due colonne: schermate di workflow a sinistra, avatar + terminale a destra |
| `web/app.js` | Animazioni GSAP, reazioni dell'avatar (de-esser → flash piercing, glue compression → orecchini che tintinnano, BPM → headbang), canvas QC, cylon bar, checkpoint Director Mode, console streaming LLM |
| `web/style.css` | Tema scuro industriale (#0A0A0A sfondo, #FF003F accento), moduli rack, pannello terminale, animazioni glitch |
| `web/vendor/gsap.min.js` | GreenSock Animation Platform per animazioni UI fluide e performanti |

L'avatar è un wireframe SVG minimalista con:
- **Occhiali** che si colorano e brillano durante l'inferenza LLM ("deep scan")
- **Piercing al naso** che lampeggia rosso quando il de-esser interviene
- **Orecchini** che tintinnano ad ogni colpo di compressore, con extra kick dalla glue compression
- **Cuffie** che appaiono durante i momenti di "ascolto" (denoise, LTAS matching, QC)
- **Respirazione** a riposo e sguardo autonomo casuale (giri 3D della testa via GSAP)
- **Headbang** sincronizzato al BPM una volta che il motore ha analizzato il tempo

### Progettazione della Catena Vocale

La catena di elaborazione vocale è la parte più attentamente ingegnerizzata del sistema:

1. **Denoise** — riduzione rumore spettrale prima di qualsiasi altra elaborazione
2. **HPF adattivo** — segue la frequenza fondamentale misurata della voce (non un fisso 100Hz che taglierebbe un baritono)
3. **Soppressione risonanze** — taglia solo dove l'energia si accumula nella fascia mud
4. **Presenza** — +1.5dB a 3kHz, con variazione per sezione (chorus +0.7dB in più, verse -0.3dB)
5. **Compressione** — ruolo-specifica con makeup gain automatico. La modalità blueprint abilita la compressione seriale 2-stadi (FET peak catcher + Opto leveler)
6. **De-esser** — multibanda 4-8kHz, soglia adattiva per registro
7. **Bus Vocal_Main** — tutti i take lead sommati in un'entità coerente
8. **Bus Vocal_Doubles** — tutte le backing vocals sommate, incollate, poi scalate al **50%** del livello Main
9. **Spazio** — riverbero in base al genere + delay sincronizzato al BPM, adattivo per sezione (chorus si apre, verse resta intimo)
10. **Ducking spettrale** — solo la banda 1-4kHz viene abbassata negli strumentali quando la voce è attiva

### Sicurezza e Protezioni

- **Le voci Main/Lead non vengono mai warplate** dall'allineamento elastico (guardia basata sul nome in `elastic_align.py`)
- **Le voci Main/Lead non vengono mai attenuate** dalla compensazione di livello (saltate in `leveling.py`)
- **Warp elastico limitato al 2%** — se DTW richiede più stiramento, la finestra viene saltata
- **Guardia energetica** in elastic align: se il segnale "lead" ha meno del 60% dell'RMS del double, la funzione esce (probabili argomenti invertiti)
- **Makeup gain dopo ogni compressore** — previene il calo cumulativo di 6-12dB attraverso stadi di compressione seriali
- **Massimale di sicurezza** a -1dBFS sul mix bus
- **Neural Monitor** ha normalizzazione di picco e fade anti-click così un bug DSP non può mai esplodere le casse
- **Tutto wrapped in try-except** — un dispositivo audio mancante, un'inferenza LLM fallita, o un errore librosa non fermano mai il render

### Documento di Riferimento

`DSP_ENGINE_SPECS.md` è il regolamento numerico di riferimento. Reconcilia linee guida contrastanti da tre fonti di ingegneria audio (Stavrou, Eargle, Winer) in default risolti singoli — target gain staging (-18dBFS RMS), metodo de-esser (multibanda 4-8kHz), i 3 modelli distinti di compressore (VCA/FET/Opto), ordine della catena di segnale, e una tabella completa di impostazioni compressore per strumento.

### Stato

In sviluppo attivo. Vedi `.omo/` per note di pianificazione e la cronologia dei commit per i progressi.

**Fasi completate:**
- **Fase 0** — Director Mode: checkpoint di approvazione human-in-the-loop, verificato end-to-end attraverso i thread
- **Fase 2** — Catene DSP blueprint (compressione vocale seriale, glue drum, catena basso), calibrazione riverbero RT60
- **Fase 3** — Matching spettrale LTAS contro un brano di riferimento
- **Fase 4** — LLM advisory: modello locale Qwen 2.5 1.5B per classificazione stem ambigui, validato da director_safety.py
- **Fase 5** — GUI: layout a due colonne, avatar SVG con animazioni GSAP e reazioni DSP in tempo reale, console streaming LLM, cylon bar, Neural Monitor A/B live
- **Fase 6** — Packaging PyInstaller: costruito e testato con tutte le dipendenze incluse (llama_cpp, pywebview, sounddevice, modello GGUF). Ancora da testare su macchina pulita.

**Indurimento recente della catena vocale (Luglio 2026):**
- Split bus Vocal_Main / Vocal_Doubles — doppie al 50% (-6dB) così la Main mantiene presenza
- Makeup gain dopo ogni stadio di compressore — previene il calo cumulativo di livello
- Limite warp allineamento elastico ridotto al 2% — elimina artefatti flutter
- Le voci Main/Lead non vengono mai warplate o compensate in livello — sono la griglia temporale
- Neural Monitor riparato: risolto mismatch sample rate WASAPI, aggiunto makeup gain per segnali deboli
- File picker riparato: aggiunta selezione file audio singolo affiancata al selettore cartelle
- Sfondo avatar `motus_base.png` integrato come elemento SVG `<image>`

### Problemi Noti

**Finestra nera all'avvio:** Se la scorciatoia desktop apre una finestra nera che non renderizza mai, è molto probabilmente **NVIDIA Overlay** (o un overlay simile che aggancia l'UI Automation — Discord overlay, RTSS, Xbox Game Bar) che intercetta la nuova finestra e innesca una ricorsione infinita nel bridge .NET/COM di pywebview. Confermato killando il processo NVIDIA Overlay e vedendo l'app caricarsi normalmente in secondi.

**Diagnosi:** `app/main.py` scrive `%LOCALAPPDATA%\RedLineEngine\last_load.log` nel momento in cui la pagina finisce di caricarsi. Se quel file è assente o vecchio dopo un tentativo di avvio, la pagina non è mai stata caricata. Se è fresco, la finestra nera ha un'altra causa. Imposta `REDLINE_DEBUG_GUI=1` per aprire DevTools insieme alla finestra.

**Soluzione:** Disabilita l'overlay in-game/in-app per il software rilevante, o escludi `RedLineEngine.exe` da esso.

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the desktop app
python app/main.py

# Or run headless (CLI)
python -m redline.cli --input /path/to/stems --output /path/to/out

# Enable experimental features
echo '{"ENABLE_BLUEPRINT_CHAINS": true}' > .flags.json

# Debug GUI
REDLINE_DEBUG_GUI=1 python app/main.py
```

## Verification

A synthetic gain-staging test is included:

```bash
python verify_gain.py
```

This generates two test tones (Main at 0dBFS, Double at -6dBFS), simulates the mix bus logic, and asserts that:
- Main RMS is identical to the original (bit-perfect, diff=0.0)
- Double RMS is exactly 50% of the original (-6dB)

---

*RedLine Engine — mixing with your mind, mastered by machine.*
