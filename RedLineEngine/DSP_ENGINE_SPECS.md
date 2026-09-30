# Specifiche Architetturali Motore DSP — RedLineEngine

**Data**: 2026-07-06
**Fonti**: 
- *Mixing with Your Mind* — Michael Paul Stavrou (12 tecniche)
- *Handbook of Recording Engineering* — John Eargle (16 tecniche)
- *The Audio Expert* — Ethan Winer (20 tecniche)

**Librerie target**: `pedalboard`, `librosa`, `numpy`, `scipy.signal`

---

## Indice

1. [Mappa Conflitti e Risoluzioni](#0-mappa-conflitti-e-risoluzioni)
2. [Psicoacustica e Illusioni (Stavrou)](#1-psicoacustica-e-illusioni-stavrou)
3. [Fisica ed Elettroacustica (Eargle)](#2-fisica-ed-elettroacustica-eargle)
4. [Ingegnerizzazione Workflow (AudioExpert)](#3-ingegnerizzazione-workflow-audioexpert)
5. [Tabelle Riassuntive Unificate](#4-tabelle-riassuntive-unificate)
6. [Architettura di Routing Consigliata](#5-architettura-di-routing-consigliata)

---

## 0. Mappa Conflitti e Risoluzioni

Prima di elencare le tecniche, ecco tutti i punti in cui le tre fonti divergono. **Per ogni conflitto ho scelto la soluzione migliore** — quella spiegata più chiaramente, più specifica, o più adatta a un motore DSP headless.

### 0.1 Calibrazione 0VU
| Fonte | Valore | 
|-------|--------|
| **Stavrou** | 0VU = -14dBFS |
| **AudioExpert** | Target RMS mixing = -18dBFS |

**Scelta: AudioExpert (-18dBFS RMS)**. 
AudioExpert spiega il gain staging digitale moderno in modo completo: target RMS a -18dBFS con headroom 12-20dB. Stavrou usa 0VU = -14dBFS che è uno standard analogico pre-digitale (più "caldo", meno headroom). Per un motore headless Python che processa audio digitale, lo standard -18dBFS è più sicuro (previene clipping, lascia margine per l'elaborazione). Il metering VU a -14dBFS = 0VU rimane come opzione "vintage mode".

### 0.2 De-Esser: Sidechain vs Multibanda
| Fonte | Approccio | Frequenza |
|-------|-----------|-----------|
| **Stavrou** | Sidechain: HPF 1-2kHz + boost 14kHz (Q=10-20) → compressor ducking | 14kHz |
| **AudioExpert** | Multi-band compressor su banda 4-8kHz, Ratio 5:1-10:1 | 4-8kHz |

**Scelta: AudioExpert (multibanda 4-8kHz)**.
AudioExpert descrive il de-esser moderno standard: compressione solo sulla banda sibilante, lasciando intatto il resto dello spettro. Più trasparente, più preciso, industrialmente accettato. Stavrou usa un approccio più rudimentale (ducking dell'intero segnale) che è meno trasparente e può creare artefatti. Il metodo Stavrou rimane come alternativa per sibilanza estrema (es. voci maschili con "S" molto forti) dove il multibanda non basta.

### 0.3 Compressor Attack per Basso
| Fonte | Attack | Ratio | Scopo |
|-------|--------|-------|-------|
| **Stavrou** | 0.1-50ms (generico) | 1.5:1-20:1 | Tuning sequenziale |
| **AudioExpert (punch)** | 30-80ms | 4:1-10:1 | Preservare attacco |
| **AudioExpert (sustain)** | 5-10ms | 10:1 | Appiattire dinamica |

**Scelta: AudioExpert (due preset: punch 30-80ms, sustain 5-10ms)**.
AudioExpert è molto più specifico e实用: dà valori numerici precisi per due scenari d'uso distinti. Stavrou descrive un processo di tuning generico che è utile come *metodologia* ma non dà valori di partenza. Nel motore: implementa i due preset di AudioExpert, e opzionalmente il processo di auto-tuning di Stavrou come raffinamento.

### 0.4 Compressor Attack per Voce
| Fonte | Attack | Ratio | Threshold |
|-------|--------|-------|-----------|
| **Stavrou (Limiter1)** | 1ms | 4:1 | 0VU (-14dBFS) |
| **Stavrou (Comp2)** | 10ms | 2:1 | -4dBVU (-18dBFS) |
| **AudioExpert** | 10ms | 2:1 | -4dBVU |

**Scelta: AudioExpert (10ms, 2:1, -18dBFS) come default. Stavrou come estensione per voci estreme.**
AudioExpert dà il setting standard per voci normali (dinamica <30dB). Stavrou aggiunge un limiter extra a monte per voci con dinamica >50dB. I due sono compatibili: il secondo stadio di Stavrou è IDENTICO al setting AudioExpert. Nel motore: default = AudioExpert (1 compressore). Opzione "wide dynamic" = Stavrou (2 stadi).

### 0.5 Pre-Delay Riverbero
| Fonte | Pre-Delay | Decay |
|-------|-----------|-------|
| **Stavrou** | 50ms | 3s → 2s (con pre-delay) |
| **AudioExpert (basic)** | 50ms | 1.9s |
| **AudioExpert (ambience)** | 35ms | 0.4s |

**Scelta: AudioExpert per i preset, Stavrou per la formula di relazione pre-delay/decay.**
AudioExpert dà valori assoluti pronti all'uso per due scenari (basic 1.9s, ambience 0.4s). Stavrou spiega un principio più profondo: il pre-delay *riduce* il decay necessario perché l'orecchio integra i due parametri. La formula `decay_eff = decay_base - pre_delay * 0.02` è utile come algoritmo di auto-tuning. Nel motore: preset AudioExpert + formula Stavrou per variazioni.

### 0.6 Gate: Hi-Hat (Stavrou) vs Noise Gate (AudioExpert)
| Fonte | Threshold | Attack | Release | Range |
|-------|-----------|--------|---------|-------|
| **Stavrou** | 30% del picco | <1ms | 50-100ms | -10 a -20dB |
| **AudioExpert** | -40 a -60dB | 0.5-2ms | 100-500ms | -60dB |

**Scelta: AudioExpert per noise gate standard. Stavrou per gate creativo sidechain.**
Due tool completamente diversi. AudioExpert descrive il noise gate tradizionale (silenzia rumore di fondo, range totale -60dB). Stavrou descrive un gate *creativo* (range parziale -10/-20dB, usato in sidechain per mascherare bleed). Nel motore: implementa entrambi come modelli separati.

### 0.7 MS Processing
| Fonte | Tecnica |
|-------|---------|
| **Stavrou** | MS Width dinamico (width segue envelope del Mid) |
| **Eargle** | MS encoding/decoding matrix + polar patterns |
| **AudioExpert** | MS EQ (EQ separato su M e S) |

**Scelta: Eargle come foundation matematica. AudioExpert e Stavrou come processori sulla catena MS.**
Eargle fornisce la matrice di base (M=(L+R)/2, S=(L-R)/2) che è la *sola* mathematically correct way. AudioExpert e Stavrou sono processori che si inseriscono *dopo* l'encoding e *prima* del decoding. Ordine: MS Encode (Eargle) → MS EQ (AudioExpert) → MS Width (Stavrou) → MS Decode (Eargle).

### 0.8 Segnale Stereo: Somma In-Phase
| Fonte | Regola |
|-------|--------|
| **Eargle** | In-phase = +6dB, 90° shift = +3dB, uncorrelated = +3dB |
| **AudioExpert** | "Stacking myth" — sommare segnali identici NON dà +6dB percepiti |

**Scelta: Eargle per calcoli interni (fisica del segnale). AudioExpert per metering output (percezione).**
Eargle ha ragione dal punto di vista elettrico: due segnali identici in fase sommati danno +6dB di tensione. AudioExpert ha ragione dal punto di vista percettivo: il nostro orecchio non percepisce +6dB come "doppio del volume" (servono circa +10dB per il "doppio" percepito). Nel motore: usa Eargle per i calcoli di livello interni (evita clipping), usa AudioExpert per il metering output (dà all'utente letture percettivamente significative).

### 0.9 Compression Types
| Fonte | Specificità |
|-------|-------------|
| **Stavrou** | Compressore generico (un modello) |
| **Eargle** | Compressore generico (un modello) |
| **AudioExpert** | 3 tipi: VCA, FET, Opto (modelli separati) |

**Scelta: AudioExpert (3 modelli: VCA, FET, Opto).**
AudioExpert è l'unica fonte che distingue i tipi di compressore con parametri specifici per ciascuno. Stavrou ed Eargle trattano il compressore come unico blocco generico — utile per capire il concetto, ma insufficiente per implementazione. Nel motore: 3 modelli separati (VCA per bus, FET per drums, Opto per voci/basso). Il processo di tuning di Stavrou si applica a tutti e tre come interfaccia utente unificata.

### 0.10 Signal Chain Order
| Fonte | Ordine |
|-------|--------|
| **Stavrou** | Compressor post-fader |
| **AudioExpert** | HPF → EQ sub → Comp → EQ add → Limiter |

**Scelta: AudioExpert (HPF → EQ sub → Comp → EQ add → Fader → Limiter) con integrazione Stavrou (fader dopo compressore).**
AudioExpert descrive la catena completa di insert nel dettaglio. Stavrou aggiunge un dettaglio importante: il compressore deve essere *dopo* il fader (post-fader), non prima. Le due cose sono compatibili: la catena AudioExpert con il fader posizionato *dopo* il compressore e *prima* del limiter. Questo dà `HPF → EQ sub → Comp → EQ add → Fader → Limiter`.

---

## 1. Psicoacustica e Illusioni (Stavrou)

### 1.1 Flame Tip Positioning
**Scopo**: Trovare la distanza ottimale microfono-fonte dove la coerenza di fase è massima.
**Parametri**: distanza 0.3-3m, bande 0-200Hz / 200-4kHz / 4kHz-20kHz
**Pseudocodice**: `find_flame_tip(signal, fs, positions_m, freq_bands)` → restituisce distanza ottimale
**Routing**: Pre-recording (simulabile come delay + filtraggio in DSP)

### 1.2 Compressor Sequential Tuning
**Scopo**: Ordine di tuning: Attack → Release → Ratio → Threshold
**Parametri**: Attack 0.1-50ms, Release 20-500ms, Ratio 1.5:1→20:1, Threshold -40→0dB
**Pseudocodice**: `stavrou_compressor(audio, fs, attack_ms, release_ms, ratio, threshold_db)`
**Routing**: Insert post-fader (fader → compressor → output)
**Nota**: I valori specifici per strumento vanno presi dalla tabella 4.1 (AudioExpert). Questo è il *processo* di tuning, non i valori.

### 1.3 Auto 3D Effect
**Scopo**: Profondità dinamica — segnale compresso in path A, riverbero non compresso in path B
**Parametri**: Ratio 2:1-4:1, reverb decay 1-3s, threshold -20dB
**Pseudocodice**: `auto_3d_effect(dry_signal, fs, comp_ratio=3, threshold_db=-20, reverb_decay=1.5)`
**Routing**: Send-return (uncompressed → reverb, compressed → master)

### 1.4 Sidechain De-Esser (Stavrou Method) — Alternativa
**Scopo**: Ducking dell'intero segnale vocale quando rileva sibilanza a 14kHz. Metodo aggressivo per sibilanza estrema.
**Parametri**: HPF @ 1-2kHz, boost @ 14kHz (Q=10-20), Attack <1ms, Release 50ms, Ratio 10:1-20:1
**Pseudocodice**: `stavrou_deesser(audio, fs, threshold_db=-30, release_ms=50)`
**Routing**: Sidechain (EQ'd signal → compressor sidechain input)
**⚠️ DEFAULT CONSIGLIATO**: Per la maggior parte dei casi, usare il De-Esser multibanda (AudioExpert §3.6) che opera a 4-8kHz ed è più trasparente. Questo metodo Stavrou è solo per sibilanza estrema dove il multibanda non basta.

### 1.5 Dual Limiter Vocal Chain
**Scopo**: Due limiters in cascata con soglie scalate per voci a 50dB di dinamica
**Parametri**: Limiter1 Ratio=4:1 Threshold=0VU (-14dBFS), Compressor2 Ratio=2:1 Threshold=-4dBVU (-18dBFS)
**Pseudocodice**: `dual_limiter_vocal(audio, fs, fader_gain_db=0)`
**Routing**: Insert post-fader → Limiter → Compressor
**Nota**: Per voci con dinamica normale (<30dB), usare solo il secondo stadio (Compressor 2:1 a -18dBFS) che corrisponde allo standard AudioExpert.

### 1.6 Time Machine Effect
**Scopo**: Correzione percezione temporale via gain — fader su = più lento, fader giù = più veloce
**Parametri**: Gain ±3-6dB, tolleranza onset 20ms
**Pseudocodice**: `time_machine(audio, fs, beat_times, onset_tolerance_ms=20)`
**Routing**: Channel fader automation

### 1.7 Blur Zone / Phase Alignment
**Scopo**: Allineamento fase tra close mic e overhead drum
**Parametri**: Delay 0-200 samples @48kHz, phase inversion toggle
**Pseudocodice**: `blur_zone_align(close_mic, overhead, fs)`
**Routing**: Multi-mic su stessa source

### 1.8 MS Width Control (Dynamic Stereo)
**Scopo**: Larghezza stereo dinamica — più stretto quando forte, più largo quando piano
**Parametri**: Width factor 0-100%, side gain -∞ a +6dB
**Pseudocodice**: `dynamic_ms_width(stereo_signal, fs, base_width=0.7, width_range=0.5)`
**Routing**: Bus (MS encode → process → decode). Da posizionare DOPO MS EQ (AudioExpert §3.18) se presente.

### 1.9 Bass DI + Mic Delay Alignment
**Scopo**: Allineamento fase tra DI (arriva ~2ms prima) e microfono amplificato
**Parametri**: Delay 0-5ms (step 0.02ms), phase inversion
**Pseudocodice**: `align_di_mic(di_signal, mic_signal, fs, max_delay_ms=5)`
**Routing**: Due canali sommati su un bus

### 1.10 Hi-Hat Sidechain Gate
**Scopo**: Il rullante gating la hi-hat per nascondere bleed
**Parametri**: Gate range -10 a -20dB, Attack <1ms, Release 50-100ms
**Pseudocodice**: `hihat_snare_gate(hihat, snare, fs, gate_range_db=-15, release_ms=80)`
**Routing**: Sidechain (snare → gate su hi-hat)
**Nota**: Questo è un gate *creativo* (range parziale). Per noise gate tradizionale, usare §3.14.

### 1.11 Reverse Mixing
**Scopo**: Mixare al contrario per bilanciare il sustain invece dell'attacco
**Parametri**: Nessuno (time-reversal dell'intera sessione)
**Pseudocodice**: `reverse_mix(multitrack_tracks, mix_function)`
**Routing**: Globale (intera sessione reversed)

### 1.12 Pink Noise Gate for Reverb Tuning
**Scopo**: Test signal (rumore rosa gated) per tarare riverbero
**Parametri**: Gate attack/release min-50ms, BPM
**Pseudocodice**: `pink_noise_reverb_tuner(fs, bpm=120, gate_attack_ms=1, gate_release_ms=1)`
**Routing**: Send-return (test signal → reverb → monitor)

---

## 2. Fisica ed Elettroacustica (Eargle)

### 2.1 Inverse-Square Law Distance Attenuation
**Formula**: `Loss_dB = 20 * log10(D2 / D1)`
**Parametri**: D1 (distanza riferimento), D2 (distanza corrente)
**Pseudocodice**: `eargle_inverse_square_attenuation(signal, spl_ref_db, dist_ref, dist_current)`
**Routing**: Pre-mix depth simulation

### 2.2 Critical Distance (Dc) Calculation
**Formula**: `Dc = 0.14 * sqrt(Q * S * a)`
**Parametri**: Q (directivity, 2-13), S (m²), a (absorption 0-1)
**Pseudocodice**: `eargle_dry_wet_blend(signal_dry, signal_wet, mic_distance, Dc)`
**Routing**: Reverb bus send calibration

### 2.3 Sabine Reverberation Time (RT60)
**Formula**: `RT60 = 0.161 * V / (S * a)` (metric)
**Parametri**: V (m³), S (m²), a_i per banda d'ottava
**Pseudocodice**: `eargle_rt60_sabine(V, S, absorption_coeffs)`
**Routing**: Reverb algorithm design

### 2.4 Absorption Coefficient Table
**Valori**: 6 materiali × 6 bande d'ottava (125Hz-4kHz)
**Uso**: Lookup table per riverbero multibanda
**Pseudocodice**: Tabella `EARGLE_ABSORPTION_TABLE` con coefficienti per materiale

### 2.5 Phase Cancellation & Comb Filtering
**Formula**: `f = c / (2 * |D2 - D1|)` dove c = 343 m/s
**Parametri**: D1, D2 (distanze in metri)
**Pseudocodice**: `eargle_comb_filter_frequencies(d1, d2, c=343)`
**Routing**: Mono compatibility checker

### 2.6 Electrical Signal Summation
**Regole**: In-phase = +6dB, anti-phase = 0, 90° shift = +3dB, uncorrelated = +3dB
**Pseudocodice**: `eargle_signal_summation_level(sig1, sig2)`
**Routing**: Mix bus level prediction
**⚠️ Nota percettiva**: Questi sono valori *elettrici* (tensione). La percezione di loudness segue regole diverse (vedi AudioExpert §0.8). Usare per calcoli interni, non per metering finale.

### 2.7 Stereo Correlation Meter
**Formula**: `corr = E[L*R] / sqrt(E[L²] * E[R²])`
**Parametri**: Integrazione 0.5-1.0s
**Pseudocodice**: `eargle_correlation_meter(left, right, sr, tau=0.5)`
**Routing**: Stereo monitoring, phase issue detection

### 2.8 Mid/Side (MS) Encoding/Decoding Matrix
**Formule**: M = (L+R)/2, S = (L-R)/2; L = M+S, R = M-S
**Parametri**: Width 0.0-2.0+, Position -1 to +1
**Pseudocodice**: `eargle_ms_encode(left, right)` / `eargle_ms_decode(m, s, width=1.0, position=0.0)`
**Routing**: Base matematica per tutte le elaborazioni MS (Stavrou §1.8, AudioExpert §3.18)

### 2.9 Polar Pattern Equations
**Formula**: `P(θ) = a + b*cos(θ)` — 6 pattern (omni, subcardioid, cardioid, supercardioid, hypercardioid, figure-8)
**Parametri**: Angolo 0-360°, pattern type
**Pseudocodice**: `eargle_polar_gain(pattern, angle_deg)`
**Routing**: Virtual microphone simulation

### 2.10 Panpot Law (Equal-Power Panning)
**Formula**: L = cos(θ), R = sin(θ) con θ = 0° (center) a 45° (full L/R)
**Parametri**: Pan -1 to +1, law "equal_power" o "equal_amplitude"
**Pseudocodice**: `eargle_panpot(signal, pan, law="equal_power")`
**Routing**: Mixer panpot

### 2.11 Proximity Effect
**Formula**: `Boost(f,d) = 20*log10(sqrt(1 + (2πfd/c)²) / (2πfd/c))`
**Parametri**: Distanza (m), pattern (figure8=1.0, cardioid=0.5)
**Pseudocodice**: `eargle_proximity_filter(signal, sr, distance, pattern="cardioid")`
**Routing**: Microphone simulation, LF management

### 2.12 Early Reflections & Delay Architecture
**Architettura**: Delay1 ~15ms (L), Delay2 ~25ms (R), Delay3 ~40-60ms (pre-delay reverb)
**Parametri**: Pre-delay 0-100ms, RT60 per banda
**Pseudocodice**: `eargle_early_reflections(signal, sr, delay_ms=15, level_db=-6)`
**Routing**: Reverb algorithm design

### 2.13 Stereo Image Widening (Negative Cross-Feed)
**Formula**: L_out = L_in - k*LP(R_in), R_out = R_in - k*LP(L_in)
**Parametri**: Amount 0.0-0.5, crossover 200-500Hz
**Pseudocodice**: `eargle_stereo_widener(left, right, sr, amount=0.2, crossover_hz=300)`
**Routing**: Mastering, stereo enhancement

### 2.14 Compressor Anatomy
**Formula**: `G_out = G_threshold + (G_in - G_threshold) / ratio`
**Parametri**: Threshold -60 a 0dB, Ratio 1:1 a ∞:1, Attack 100µs-1ms, Release 0.5-3s
**Pseudocodice**: `eargle_compressor(signal, sr, threshold_db=-20, ratio=4, attack_ms=1, release_ms=100)`
**Routing**: Dynamics processing
**Nota**: Modello generico. Per implementazioni specifiche (VCA/FET/Opto), usare AudioExpert §3.16.

### 2.15 Franssen Localization
**Principio**: Posizione immagine stereo = funzione di level_diff + time_diff
**Parametri**: Level diff -6 a +6dB, time diff -4 a +4ms
**Pseudocodice**: `eargle_franssen_localization(level_diff_db, time_diff_ms)`
**Routing**: Stereo array analysis

### 2.16 All-Pass Phase Shift Network
**Formula**: `H(s) = (R - sC) / (R + sC)` (first-order allpass, 0°→180°)
**Parametri**: fc (corner frequency)
**Pseudocodice**: `eargle_allpass_phase_shift(signal, sr, fc=1000)`
**Routing**: Broadcast processing, crest factor management

---

## 3. Ingegnerizzazione Workflow (AudioExpert)

### 3.1 Signal Chain Ordering
**Regola**: HPF → EQ sottrattivo → Compressor → EQ additivo → Fader → Limiter
**Parametri**: HPF cutoff 60Hz, Comp ratio 10:1, Post-EQ 175Hz +2dB
**Pseudocodice**: `signal_chain(audio_buffer, sr, hpf_cutoff=60, comp_ratio=10, comp_thresh=-20, post_eq_freq=175, post_eq_gain=2)`
**Routing**: Insert chain su traccia individuale
**Nota**: Il fader è DOPO il compressore (post-fader = compressore vede il segnale già livellato dal fader). Questo è compatibile con Stavrou §1.2.

### 3.2 Compressor Attack for Bass Punch
**Parametri**: Attack 30-80ms, Release 500ms+, Ratio 4:1-10:1, Threshold -18 a -12dB
**Pseudocodice**: `bass_punch_compressor(audio, sr, attack=50e-3, release=500e-3, ratio=6, threshold=-18)`
**Routing**: Insert su basso, dopo HPF, prima di EQ tonale

### 3.3 Compressor for Sustain (Electric Bass)
**Parametri**: Ratio 10:1, Threshold -20 a -15dB, Attack 5-10ms, Release 300-800ms, GR target 6-10dB
**Pseudocodice**: `sustain_compressor(audio, sr, ratio=10, threshold=-20, attack=5e-3, release=500e-3)`
**Routing**: Insert su basso

### 3.4 Subtractive EQ (Surgical Cutting)
**Regola**: Sweep narrow boost per trovare risonanza → cut
**Parametri**: Q=5-20, cut -3 a -12dB, sweep 100Hz-5kHz
**Target**: 300Hz (boxy), 1kHz (nasal), 2kHz (scratchy), 600Hz (hollow)
**Pseudocodice**: `surgical_eq(audio, sr, target_freq, cut_db=-6, q=10)`
**Routing**: Insert su qualsiasi traccia, prima del compressor

### 3.5 Complementary EQ (Carving Space)
**Regola**: Boost +2-3dB su featured track, cut -2-3dB stesso freq su competing tracks
**Parametri**: Boost/cut ±2dB, Q=1-2, freq 600Hz-2kHz
**Pseudocodice**: `complementary_eq(featured_track, competing_bus, sr, freq=1500, boost_db=2, q=1.5)`
**Routing**: Featured track boost, competing bus cut

### 3.6 De-Essing via Multi-Band Compressor — DEFAULT
**Scelta**: Questo è il metodo consigliato per la maggior parte dei casi. Più trasparente e preciso del metodo Stavrou.
**Parametri**: Band 4-8kHz, Ratio 5:1-10:1, Threshold -20dB, Attack 1ms, Release 50ms
**Pseudocodice**: `deesser(audio, sr, center_freq=6000, q=2, threshold=-20, ratio=8, attack=1e-3, release=50e-3)`
**Routing**: Insert su voce, dopo HPF, prima di EQ tonale
**⚠️ Alternativa (Stavrou)**: Per sibilanza estrema (es. voci maschili con "S" molto forti), usare Sidechain De-Esser (§1.4) che ducka l'intero segnale invece della sola banda.

### 3.7 Pop Filter (Low-Frequency De-Essing)
**Parametri**: Band <80Hz, Ratio 10:1+, Threshold -20dB, Attack 1ms, Release 30ms
**Pseudocodice**: `pop_filter(audio, sr, threshold=-20, ratio=15, attack=1e-3, release=30e-3)`
**Routing**: Insert su voce, primo in catena

### 3.8 Side-Chain Ducking
**Parametri**: Attack 10-50ms, Release 200-500ms, Ratio 4:1-10:1, Threshold -18dB
**Pseudocodice**: `ducker(main_audio, sidechain_audio, sr, threshold=-18, ratio=5, attack=20e-3, release=300e-3)`
**Routing**: Compressor su music bus, sidechain da vocal track

### 3.9 Parallel Compression (New York)
**Parametri**: Wet/dry mix 20-50%, Ratio 10:1+, Threshold -20dB, Attack 1-5ms, Release 100-300ms
**Pseudocodice**: `parallel_compression(audio, sr, mix=0.3, ratio=10, threshold=-20, attack=3e-3, release=200e-3)`
**Routing**: Aux bus send → compressor → return mixed with dry

### 3.10 Reverb Settings (Basic vs Ambience)
**Basic**: LowCut=75Hz, HighCut=4kHz, Predelay=50ms, Decay=1.9s, BassMult=0.3, Crossover=350Hz
**Ambience**: LowCut=55Hz, HighCut=11kHz, Predelay=35ms, Decay=0.4s, BassMult=0.7, Crossover=800Hz
**Pseudocodice**: `basic_reverb(audio, sr, decay_time=1.9, predelay=50e-3, low_cut=75, high_cut=4000, bass_mult=0.3, crossover=350, high_damp=4000)`
**Routing**: Aux bus send (100% wet), due bus separati
**Nota**: La relazione pre-delay/decay segue Stavrou §1.12: `decay_effettivo = decay_base - pre_delay * 0.02`.

### 3.11 Echo Timing to Tempo
**Formula**: `delay_time = 60 / BPM * factor`
**Parametri**: Factor 0.25-8, feedback 20-40%, mix -10dB
**Pseudocodice**: `tempo_echo(audio, sr, bpm=120, subdivision=0.25, feedback=0.3, mix_db=-10)`
**Routing**: Aux bus send, pan echo opposto

### 3.12 Gain Staging / Headroom
**Regola**: Target RMS = -18dBFS, headroom 12-20dB, max peak -1dBFS
**Pseudocodice**: `gain_stage(audio, target_rms_db=-18, max_peak_db=-1)`
**Routing**: Applicato a ogni stage input/output
**Nota**: 0VU = -14dBFS (Stavrou) è un riferimento diverso. Il motore supporta entrambi: `mode="modern"` (-18dBFS RMS) o `mode="vintage"` (0VU = -14dBFS).

### 3.13 Low-Cut Filter on Non-Bass Tracks
**Regola**: HPF 80-120Hz su tutte le tracce tranne basso e kick
**Parametri**: Cutoff 80-120Hz, slope 12-24dB/oct
**Pseudocodice**: `thin_track(audio, sr, cutoff=100, order=4)`
**Routing**: Primo insert su ogni traccia non-bass/kick

### 3.14 Noise Gate with Hold Time
**Parametri**: Threshold -40 a -60dB, Attack 0.5-2ms, Hold 50-200ms, Release 100-500ms, Depth -60dB
**Pseudocodice**: `noise_gate(audio, sr, threshold=-50, attack=1e-3, hold=100e-3, release=200e-3, depth_db=-60)`
**Routing**: Insert su traccia rumorosa, prima del compressor
**Nota**: Gate tradizionale (range totale). Per gate creativo (range parziale), usare Stavrou §1.10.

### 3.15 Maximizer / Peak Limiting
**Parametri**: Threshold -6 a -3dB, Lookahead 1-5ms
**Pseudocodice**: `maximizer(audio, sr, threshold_db=-6, lookahead_ms=2)`
**Routing**: Ultimo processor su master bus, prima del dither

### 3.16 Compressor Types (VCA vs FET vs Opto) — DEFAULT
**Scelta**: AudioExpert è l'unica fonte che distingue i tipi di compressore. Implementare 3 modelli separati.
**VCA**: Attack 0.1-50ms, Release 10ms-2s, feed-forward, pulito, distortion <0.01%
**FET**: Attack 0.05-20ms, Release 50ms-1s, +2nd/3rd harmonics, distortion 0.5-2%
**Opto**: Attack 5-20ms, Release 100ms-2s, feedback topology, smooth, distortion <0.1%
**Pseudocodice**: `vca_compressor(...)`, `fet_compressor(...)`, `opto_compressor(...)`
**Routing**: VCA per bus/master, FET per drums/percussione, Opto per vocals/basso
**Nota**: Questi 3 modelli sostituiscono il compressore generico di Stavrou ed Eargle. Il processo di tuning sequenziale (Stavrou §1.2) si applica a tutti e tre come interfaccia di auto-tuning unificata.

### 3.17 Bus Compression (Mix Glue)
**Parametri**: Ratio 1.2:1-2:1, Threshold -12 a -8dB, Attack 10-30ms, Release 100-500ms, GR 2-4dB
**Pseudocodice**: `bus_compressor(audio, sr, ratio=1.5, threshold=-10, attack=20e-3, release=200e-3, knee=6)`
**Routing**: Ultimo insert su master bus, prima del limiter

### 3.18 Mid/Side EQ
**Regola**: Decode MS → EQ separato → Re-encode
**Parametri**: Mid EQ any, Side EQ any (tipico: +1-3dB low boost su sides)
**Pseudocodice**: `ms_eq(left, right, sr, mid_eq_params=None, side_eq_params=None)`
**Routing**: Su stereo bus o master, prima del bus compressor
**Nota**: Da posizionare PRIMA di MS Width (Stavrou §1.8) se usati insieme.

### 3.19 Transient Shaper
**Parametri**: Attack boost 0-10dB, Sustain 0-10dB, Attack time 1-20ms
**Pseudocodice**: `transient_shaper(audio, sr, attack_gain_db=3, sustain_gain_db=0, attack_time=10e-3)`
**Routing**: Insert su drums, percussione, strumenti pizzicati

### 3.20 Monitor Level Standard
**Regola**: Mix a 85dBA SPL (Fletcher-Munson flat), check a 75/85/95dBA
**Pseudocodice**: `spl_monitor_check(mix, sr, calibration_offset=0)`
**Routing**: Monitoring chain (non processing)

---

## 4. Tabelle Riassuntive Unificate

### 4.1 Setting Compressore per Strumento

| Strumento | Attack | Release | Ratio | Threshold | Tipo Comp | Fonte Primaria |
|-----------|--------|---------|-------|-----------|-----------|----------------|
| Kick | 1-5ms | 50-100ms | 4:1-10:1 | -18dB | FET | AudioExpert |
| Snare | 1-10ms | 50-150ms | 4:1-8:1 | -20dB | FET | AudioExpert |
| Hi-Hat | <1ms | 50-100ms | 4:1-6:1 | -20dB | VCA | AudioExpert |
| Bass (punch) | 30-80ms | 500ms+ | 4:1-10:1 | -18dB | Opto | AudioExpert |
| Bass (sustain) | 5-10ms | 300-800ms | 10:1 | -20dB | Opto | AudioExpert |
| Voce (normale) | 10ms | 100ms | 2:1 | -18dBFS | Opto | AudioExpert + Stavrou |
| Voce (dinamica ampia) | 1ms → 10ms | 50ms → 100ms | 4:1 → 2:1 | -14dBFS → -18dBFS | FET → Opto | Stavrou §1.5 |
| Acoustic Guitar | 5-15ms | 100-300ms | 3:1-5:1 | -18dB | VCA | AudioExpert |
| Electric Guitar | 5-20ms | 100-250ms | 4:1-8:1 | -15dB | FET | AudioExpert |
| Piano | 10-30ms | 200-500ms | 2:1-4:1 | -18dB | VCA | AudioExpert |
| Master Bus | 10-30ms | 100-500ms | 1.2:1-2:1 | -12dB | VCA | AudioExpert |

**Processo di tuning** (da Stavrou §1.2, applicabile a tutti i tipi):
1. Set Ratio=20:1, Release=fast, Threshold=low → adjust Attack
2. Adjust Release: longest possible without losing groove
3. Lower Ratio until artifacts disappear (tipico 2:1-4:1)
4. Set Threshold so compressor NON squeeze constantly

### 4.2 EQ Corrections per Frequenza

| Frequenza | Problema | Azione | Q | Fonte |
|-----------|----------|--------|----|-------|
| <80Hz | Rumble/Pop | HPF | 12dB/oct | AudioExpert |
| 80-120Hz | Mud (non-bass) | HPF | 12dB/oct | AudioExpert |
| 200-300Hz | Boxy/Thin | Cut -3dB | 2-5 | AudioExpert |
| 300-500Hz | Mud/Honk | Cut -2dB | 1-2 | AudioExpert |
| 600Hz | Hollow | Cut -2dB | 2-3 | AudioExpert |
| 1kHz | Nasal | Cut -3dB | 3-5 | AudioExpert |
| 2-4kHz | Harsh/Scratchy | Cut -2dB | 3-5 | AudioExpert |
| 4-8kHz | Sibilance | De-ess (multibanda) | - | AudioExpert (default) |
| 8-12kHz | Air/Brilliance | Boost +2dB | 0.7-1 | AudioExpert |
| 14kHz | Sibilance detect | Boost (sidechain) | 10-20 | Stavrou (solo casi estremi) |

### 4.3 Valori Soglia Fondamentali

| Parametro | Valore | Fonte | Note |
|-----------|--------|-------|------|
| 0VU = | -14dBFS | Stavrou | Standard vintage. Usare per metering VU. |
| Target RMS mixing | -18dBFS | AudioExpert | Standard moderno. Usare per gain staging. |
| Headroom raccomandato | 12-20dB | AudioExpert | Tra RMS target e picco max |
| Max peak digitale | -1dBFS | AudioExpert | True peak, prima del limiter |
| Monitor level target | 85dBA SPL | AudioExpert | Fletcher-Munson curve flat |
| Velocità suono | 343 m/s (1ft/ms) | Eargle/Stavrou | Per calcoli delay/phase |
| Critical distance Dc | 0.14*sqrt(Q*S*a) | Eargle | Per dry/wet blend |
| RT60 Sabine | 0.161*V/(S*a) | Eargle | Per riverbero algoritmico |
| Inverse-square | 6dB per doubling | Eargle | Per depth simulation |
| Pre-delay reverb | 35-50ms | AudioExpert/Stavrou | 50ms = standard, 35ms = ambience |
| Reverb decay basic | 1.9s | AudioExpert | Con pre-delay 50ms |
| Reverb decay ambience | 0.4s | AudioExpert | Con pre-delay 35ms |
| Relazione pre-delay/decay | decay_eff = decay_base - pd*0.02 | Stavrou | Ogni 50ms di pre-delay ≈ 1s di decay risparmiato |

---

## 5. Architettura di Routing Consigliata

### 5.1 Catena per Traccia Individuale — DEFAULT

```
Input → HPF (80-120Hz) → EQ Sub (surgical cut) → Gate/Expander → Compressor → EQ Add (tonal) → Fader → Limiter
```

**Scelta**: AudioExpert per l'ordine degli insert, Stavrou per la posizione del fader (dopo compressore).
**Fonti**: AudioExpert §3.1 (ordine insert) + Stavrou §1.2 (fader dopo compressore = "post-fader")
**Eccezioni**: 
- Voce: Pop filter (§3.7) prima di HPF, De-esser multibanda (§3.6) dopo HPF
- Basso: Nessun HPF (o cutoff <40Hz)

### 5.2 Catena per Bus di Gruppo

```
Tracce → Bus → EQ Sub → Bus Compressor (glue) → EQ Add → Limiter → Master
```

### 5.3 Catena Master — DEFAULT

```
Stereo Bus → MS Encode (Eargle §2.8) → MS EQ (AudioExpert §3.18) → MS Width (Stavrou §1.8) → MS Decode (Eargle §2.8) → Bus Compressor (§3.17) → Maximizer (§3.15) → Dither → Output
```

**Scelta**: Eargle per la matrice matematica (encoding/decoding), AudioExpert per l'EQ differenziale, Stavrou per la width dinamica.
**Ordine MS**: MS Encode (Eargle) → MS EQ (AudioExpert) → MS Width (Stavrou) → MS Decode (Eargle)

### 5.4 Send/Return (Effetti)

```
Track → Send (pre/post) → Reverb/Delay Bus → Return → Master
```

**Reverb bus**: 100% wet, EQ sul return (LowCut 75Hz, HighCut 4kHz)
**Delay bus**: 100% wet, pan echo opposto

### 5.5 Sidechain Routing

```
Source A → Sidechain Input → Compressor/Gate on Source B → Output
```

**Casi d'uso**:
- Ducking: Voce → sidechain → Music Bus compressor
- De-esser (default): Multibanda su banda 4-8kHz (AudioExpert §3.6)
- De-esser (alternativo): Voce EQ'd → sidechain → Voce compressor (Stavrou §1.4, solo sibilanza estrema)
- Gate creativo: Snare → sidechain → Hi-Hat gate (Stavrou §1.10)

### 5.6 Mappa delle Dipendenze tra Tecniche

```
                    ┌─────────────────┐
                    │  Eargle §2.8    │
                    │  MS Matrix      │ (base matematica)
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
    ┌─────────────────┐ ┌──────────┐ ┌──────────┐
    │ AudioExpert     │ │ Stavrou  │ │ Eargle   │
    │ §3.18 MS EQ     │ │ §1.8 MS  │ │ §2.13    │
    │                 │ │ Width    │ │ Widener  │
    └────────┬────────┘ └────┬─────┘ └──────────┘
             │               │
             └───────┬───────┘
                     ▼
            ┌─────────────────┐
            │ AudioExpert     │
            │ §3.17 Bus Comp  │
            └────────┬────────┘
                     ▼
            ┌─────────────────┐
            │ AudioExpert     │
            │ §3.15 Maximizer │
            └─────────────────┘
```

---

## 6. Addendum Luglio 2026 — Ricerca Web + Correzioni "Mix Inascoltabile"

Aggiunta dopo un secondo giro di ricerca (fonti web multiple: sound-on-sound,
musicguymixing, masteringthemix, izotope, waves, gearspace, edmprod, ecc. —
non solo i tre libri della Sezione 0) fatto per risolvere un problema reale
riportato dall'utente: voce quasi inudibile, audio che "gracchia", nessuna
reale separazione primo piano/sfondo tra gli strumenti.

### 6.1 Bug reali trovati e corretti (non solo tuning)

| Bug | Causa | Fix |
|---|---|---|
| Audio "gracchia" | `envelope_follower` (dsp_utils.py) generava una curva di gain "a scalini" (np.repeat su blocchi da 512 campioni) invece che interpolata — ogni scalino è un click in banda larga, usato da de-esser/sidechain/ducking su quasi ogni stem | Interpolazione lineare tra i centri-blocco (np.interp) |
| Voce sepolta di default | `vocal_gain_db = prefs.vocal_prominence * 5.0` → a slider neutro (0) nessuna spinta di priorità, la voce competeva alla pari col resto | Aggiunta `BASE_VOCAL_PROMINENCE_DB = 3.0` sempre applicata, slider si somma sopra |
| "Ammasso" strumentale che cresce con più tracce | Ogni stem strumentale sommato a piena intensità senza bilanciamento — 8 tracce = bed molto più forte di 2 tracce, a scapito della voce | Scala power-preserving (1/√N) sul bed strumentale, stessa logica già usata per le prese vocali multiple |
| Compressione bus finale inefficace | Il bus poteva arrivare a +6/+12dB prima della compressione glue (rapporto 1.1-1.6:1, troppo gentile per un overshoot così grande); l'unica rete di sicurezza era un taglio secco finale che appiattiva tutta la dinamica | Headroom proattivo (+3dB max) applicato PRIMA della glue, così il limiter finale non deve più fare un taglio drastico |
| Bus parallelo (New York comp) sbilanciato verso la batteria | Mix 22% + compressione 8:1 aggressiva favoriva i transienti della batteria sulla voce | Mix ridotto a 15% |
| Ogni strumento "other" trattato identicamente | `_guess_instrument()` era esplicitamente solo cosmetico (icona 3D), MAI usato per decisioni DSP — violino, chitarra, synth pad ricevevano lo stesso HPF/compressore | Nuovo modulo `instrumentstack.py`: ricette per strumento (vedi 6.2) |

### 6.2 Ricette per strumento (nuove, `instrumentstack.py`)

| Strumento | HPF | Tagli/boost EQ chiave | Compressione | Note |
|---|---|---|---|---|
| Archi (strings) | 150Hz | -2dB@3.2kHz (ruvidezza archetto), +1.5dB shelf 10kHz (aria) | 2.2:1, attack 20ms lento (preserva lo swell dell'arco) | Riverbero +30% (gli archi vivono nello spazio) |
| Chitarra acustica | 90Hz | -2.5dB@250Hz (boominess), +1.5dB@3kHz (attacco plettro), +1dB shelf 9kHz | 3.5:1, attack 10ms | |
| Chitarra elettrica | 110Hz | -2dB@500Hz (honk), +2dB@3.5kHz (presenza) | 2.5:1, attack 12ms | Saturazione leggera (drive 0.3) |
| Piano/tastiere | 50Hz | -2dB@300Hz (accumulo basso-medio), -1.5dB@3kHz (cede spazio alla voce) | 3:1, attack 15ms medio (piano molto dinamico) | |
| Fiati/ottoni | 150Hz | -2dB@600Hz (honk), +1.5dB@4kHz (bite) | 3.5:1, attack 8ms veloce | |
| Synth pad | 120Hz | -2dB shelf 6kHz (rolloff per "distanza") | 2:1, attack 30ms lentissimo | Riverbero +40%, sempre di sfondo |
| Synth lead/pluck | 90Hz | +2dB@3kHz (presenza), +1dB shelf 9kHz | 3:1, attack 6ms veloce (preserva il pluck) | Riverbero -20% (resta definito/asciutto) |

Rilevamento strumento: prima per nome file (esteso rispetto a prima: ora
riconosce anche archi/violino/cello/orchestra, non solo chitarra/piano/
fiati), poi fallback spettrale conservativo (crest factor + energia nelle
bande alte) per synth pad vs lead quando il nome non dà indizi — mai un
fallback che inventa un'identità specifica (es. "violino" vs "cello") che
l'audio da solo non può garantire in modo affidabile.

### 6.3 Target voce vs strumentale (dati da masteringthemix.com e altre fonti)

- La voce lead in mix professionali siede in media **~4.5 LU sopra** la
  loudness integrata dell'intero brano, non alla pari.
  Le voci di supporto stanno chiaramente "sotto" — non un numero fisso, ma
  HPF spostato 100-200Hz più in alto rispetto al lead + un LPF/taglio alto
  (~5.5kHz) che prima mancava del tutto sul registro UNISON (ora aggiunto).
- Causa più comune di "crackle" digitale non dovuta a clipping vero: gain
  staging non gestito quando si sommano molte tracce (confermato: è
  esattamente il bug trovato in 6.1).

### 6.4 Plugin: pedalboard built-in vs VST3 esterni

`pedalboard` (Spotify) può caricare plugin VST3/AU reali via
`load_plugin()`, non solo i suoi processori integrati — ma i suoi
Compressor/Limiter/EQ/Reverb integrati sono già implementazioni
professionali (stesso motore JUCE dietro molti plugin commerciali), non
"amatoriali". Il vincolo reale per bundle plugin di terze parti non è la
qualità ma la **licenza di ridistribuzione** (un plugin "gratis per la tua
DAW" spesso non permette di essere incorporato in un altro software).
Conclusione: prima di aggiungere plugin esterni, la priorità era — ed era
il vero collo di bottiglia — la progettazione della catena e le decisioni
per-strumento/per-voce (Sezione 6.1-6.2), non l'algoritmo del singolo
plugin. Valutazione di plugin liberi specifici (es. Airwindows, licenza
permissiva) resta un possibile miglioramento futuro, non urgente.

---

## 7. Addendum Luglio 2026 (parte 2) — Reference Profiles, Feedback Iterativo, Re-run Masking, A/B

Quattro estensioni strutturali costruite sopra le fondamenta della Sezione 6,
tutte additive: nessun default numerico esistente è stato cambiato, solo
resi misurabili/verificabili contro un profilo di riferimento e correggibili
entro i clamp di sicurezza già esistenti (`director_safety.py`).

### 7.1 Reference Profiles per Genere (`redline/reference_profiles.py`)

Estende `qc.TARGET_BAND_RATIOS` (curve LTAS teoriche) con un profilo
percettivo completo per ognuno dei 6 generi di `analysis/genre.py`
(`_PROFILES`): LTAS a 6 bande, LUFS target, crest factor target, target di
compatibilità mono/larghezza stereo.

| Genere | LUFS target | Crest factor target | Compatibilità mono target | Derivazione |
|---|---|---|---|---|
| EDM / Urban | -9.0 (club) | 8.0dB | 0.90 | LUFS: riuso di `PLATFORM_TARGETS["club"]`. Crest: punto medio del range `crest < 10` che `detect_genre()` già usa per riconoscere il genere (`[6,10]`). Mono compat: sub deve sommarsi in mono senza cancellazioni su sistemi PA/club. |
| Hip-Hop | -14.0 (spotify) | 10.5dB | 0.88 | Crest: punto medio di `crest < 13` (`[8,13]`). Mono compat: guidato da 808, stesso requisito EDM. |
| Pop / Rock | -14.0 (spotify) | 10.5dB | 0.80 | Crest: punto medio di `crest < 12` (`[9,12]`). |
| Jazz / Vintage | -14.0 (spotify) | 14.0dB | 0.72 | Crest: punto medio di `crest > 12` (denso) (`[12,16]`). Mono compat più bassa: immagine stereo di batteria/room più ampia è attesa. |
| Acoustic / Classical | -14.0 (spotify) | 17.0dB | 0.68 | Crest: punto medio di `crest > 14`, sparso (`[14,20]`). Mono compat più bassa: decorrelazione stereo naturale di sala/ambiente. |
| Balanced | -14.0 (spotify) | 12.0dB | 0.78 | Fallback: centro esatto di tutti i range sopra. |

Nessun numero è inventato da zero: LUFS riusa `masterengine.PLATFORM_TARGETS`,
il crest factor riusa le soglie decisionali già in `detect_genre()`, la
compatibilità mono interpola tra la soglia di pass/fail già esistente in
`qc.py` (`> 0.6`) e la correlazione perfetta (`1.0`).

**Drop folder + blending misurato**: `reference_tracks/<slug>/` (slug: `edm_urban`,
`hip_hop`, `pop_rock`, `acoustic_classical`, `jazz_vintage`, `balanced`) per
brani reali CC/acquistati/propri. `redline/profile_targets.py` misura ogni
file con le stesse funzioni già usate ovunque nel motore
(`analysis.loudness.spectral_band_energies`, nessuna duplicazione), poi
`profile_folder()` fa una **media pesata** tra la curva teorica di default e
la media misurata reale:

```
blended = (DEFAULT_WEIGHT_TRACKS * default + n_real_tracks * misurata) / (DEFAULT_WEIGHT_TRACKS + n_real_tracks)
```

con `DEFAULT_WEIGHT_TRACKS = 5.0` (la curva di default "vale" come 5 brani
sintetici nella media — una singola cartella con 3-5 brani reali sposta il
target ma non lo rimpiazza del tutto; 20-30 brani reali, il numero
consigliato, dominano la media come previsto). Nessuna cartella popolata =
comportamento identico a prima (fallback teorico puro). Nessun download
automatico di brani è stato effettuato in questo giro — solo l'architettura
a cartella + numero è stata implementata, come esplicitamente richiesto.

### 7.2 Feedback Iterativo nel Mastering (`masterengine.py`, `_apply_reference_correction`)

Loop bounded, distinto e complementare a quello già esistente in `qc.py`
(che corregge le 6 bande spettrali — vedi `MAX_QC_ITERATIONS`): questo
secondo loop misura **LUFS, crest factor, compatibilità mono/larghezza
stereo** del master già passato da `run_qc()`, li confronta contro
`reference_profiles.resolve_perceptual_target()`, e corregge — sempre
passando ogni valore da `director_safety.clamp_params()` prima di applicarlo,
mai un valore DSP non validato:

| Metrica | Tolleranza | Motivazione |
|---|---|---|
| LUFS | ±0.5 LU | Le piattaforme streaming stesse normalizzano circa in questo intervallo — inseguire una precisione maggiore rincorre rumore di misura, non un problema reale. |
| Crest factor | ±1.5dB | Sotto questa soglia la differenza dinamica/"loudness war" non è più percepibile in modo affidabile; forzare oltre rischierebbe di appiattire inutilmente. |
| Compatibilità mono/larghezza | ±0.08 | Banda più stretta *attorno al target ideale* del genere, distinta dalla soglia di pass/fail già esistente in `qc.py` (0.6, molto più permissiva — quella è un floor di sicurezza, questa è un target di qualità). |

Correzioni applicate (ognuna clampata via `director_safety.clamp_params()`):
- **Makeup loudness**: `clamp_params({"gain_db": delta})` — stesso range
  ±12dB già usato dal guardrail principale di `render_master`.
- **Compressione glue extra**: solo quando il crest misurato è *sopra* il
  target (troppo dinamico/piccato) — `clamp_params({"compressor_ratio":
  1.3, "compressor_threshold_db": -10.0})`. Non corregge la direzione
  opposta (crest già troppo basso/sovra-compresso): richiederebbe
  un'espansione, fuori scopo per un passaggio correttivo di sicurezza.
- **Larghezza stereo (canale Side)**: `clamp_params({"eq_gain_db": delta})`
  — riusa il range ±6dB di `eq_gain_db` (non esiste un parametro "width"
  dedicato in `director_safety.py`; un guadagno sul canale Side dopo
  encode/decode Mid/Side è concettualmente lo stesso tipo di mossa limitata).

Bounded a **`MASTER_CORRECTION_MAX_PASSES = 3`** passaggi; si ferma prima se
tutte le metriche rientrano in tolleranza, oppure se un passaggio non
migliora la somma delle deviazioni rispetto al precedente (evita
oscillazione tra due correzioni che si contrastano a vicenda). Ogni
passaggio ri-applica il clamp del true-peak ceiling (stessa garanzia già
presente altrove in `render_master`), e ogni passaggio è loggato via
`on_step`/`on_event` (evento `master_feedback_pass`) con lo stile
diagnostico già usato nel resto del modulo.

### 7.3 Re-run del Masking dopo Leveling/Ducking (`mixengine.py`)

`find_masking_cut()`/`find_midrange_masking_cut()` (invariati, nessuna
logica duplicata) venivano invocati una sola volta, per singolo stem
"other", subito dopo la classificazione registri/prima del sidechain
kick/basso (circa riga 1033 pre-modifica). Quella posizione era già
*dopo* la compressione per-stem (`_process_stem`), ma *prima* del sidechain
kick/basso, del ducking spettrale voce e del dip Mid/Side del bus musicale
— tutte operazioni che spostano ulteriormente il bilanciamento spettrale.

Aggiunta una seconda invocazione **a livello di bus**, subito dopo il dip
Mid/Side del bus musicale (`music_bus`) e prima della regolazione di
presenza vocale — vedi `mixengine.py`, blocco `if vocal_main_bus is not
None:` che segue immediatamente lo step "Bus musicale Mid/Side" (circa
righe 1118-1128). Confronta il `music_bus` sommato/EQato contro il
`vocal_main_bus` reale, catturando un accumulo residuo che esiste solo una
volta che tutti gli stem strumentali sono sommati insieme (uno stem
singolarmente pulito può comunque contribuire a un accumulo di bus).
Eventi separati (`bus_masking_cut` / `bus_midrange_masking_cut`) permettono
di distinguere in log/GUI la correzione per-stem da quella di bus.

### 7.4 A/B Loudness-Matched Comparison (`redline/ab_compare.py`)

Modulo importabile + CLI (`python -m redline.ab_compare before.wav
after.wav`). Allinea le due tracce a `TARGET_LUFS_FOR_MATCH = -18.0 LUFS`
(punto di riferimento neutro per il confronto, non un target di
mastering) riusando `analysis.loudness.integrated_lufs`, poi calcola i
delta LTAS/crest factor/correlazione stereo/true peak riusando
`spectral_band_energies`. Scrive un report JSON + può opzionalmente
scrivere un WAV di confronto concatenato (before, 0.5s di silenzio, after)
per l'ascolto manuale dell'utente nel proprio player/DAW — lo script **non
riproduce mai audio** (nessuna chiamata a `sounddevice`/playback in nessun
punto del modulo, verificato anche a livello statico da
`tests/test_ab_compare.py`).

---

## 8. Addendum Luglio 2026 (parte 3) — Bilanciamento voce/strumentale, bug crest factor, Link Groups

Ciclo di modifiche validato senza ascolto diretto (utente non disponibile) —
ogni decisione è ancorata a una misura oggettiva (spettro, LUFS, fase) invece
che al giudizio d'orecchio, e verificata su una sessione reale multi-stem
(27 stem strumentali + 14 stem vocali, `redline/cli.py --folder` + Demucs
non necessario, stem già separati).

### 8.1 Bug reali trovati e corretti

| Bug | Causa | Fix |
|---|---|---|
| Doppio scavo della strumentale | `MUSIC_BUS_MID_DIP_DB = -1.8` tagliava staticamente le medie del `music_bus` *a prescindere* dal ducking dinamico già presente sulla stessa banda — buco perenne anche fuori dai passaggi vocali | Portato a `0.0`; log/evento del dip resi condizionali (`if MUSIC_BUS_MID_DIP_DB < 0.0`) così la console non stampa un "buco vocale +0.0dB" inerte |
| Crest factor confrontato in unità sbagliate | `analysis/loudness.py::crest_factor()` restituisce un **rapporto lineare** peak/rms (es. 4.02), ma `masterengine.py` lo passava così com'è al feedback loop iterativo confrontandolo contro `reference_profiles.py::CREST_FACTOR_TARGETS`, che sono in **dB** — il QC leggeva "crest 4.0dB (target 8.0dB)" e tentava correzioni per un problema che non esisteva (il valore reale in dB era ~12.1, sopra il target, non sotto) | Aggiunta `_crest_factor_db()` in `masterengine.py` (conversione `20*log10(rapporto)`) usata solo nel confronto QC/feedback loop; `analysis/loudness.py::crest_factor()` **non toccato** perché condiviso con `genre.py::detect_genre()`, `depth.py`, `instrumentstack.py` — le soglie lì andrebbero riverificate a parte prima di cambiarne le unità |
| Presence boost vocale sovradimensionato | `LEAD_PRESENCE_GAIN_DB = 3.0` (Q=1.0 @ 3kHz) — misurato +19.4dB di margine voce/strumentale in banda 2-3kHz durante i tratti vocali attivi, ben oltre i ~6-10dB tipicamente sufficienti per l'intelligibilità in un mix urban/rap | Ridotto a `1.5`; verificato che l'EQ **non è la causa principale** del margine (il delta è sceso solo a +18.9dB) — il grosso del divario è strutturale (una voce sola concentra più energia in banda stretta di un bed diviso su 14 stem) e non va inseguito ulteriormente via gain, serve validazione d'ascolto |

### 8.2 Link Groups — coerenza di fase multi-mic (`naming.py` + `mixengine.py`)

Prima di questa modifica, ogni stem veniva elaborato in un thread pool
completamente indipendente (`_process_stem`, `ThreadPoolExecutor` in
`mixengine.py`): due mic diversi sulla stessa fonte fisica (es.
`Kick_In.wav`/`Kick_Out.wav`, `Synth_Pad_L.wav`/`Synth_Pad_R.wav`) potevano
ricevere tagli di risonanza (`find_resonance`) a frequenze/gain/Q diverse,
il classico presupposto per comb-filtering quando le tracce si sommano nel
bus. Verificato con un test sintetico: due "microfoni" della stessa fonte
con risonanze a 280Hz e 310Hz venivano tagliati a frequenze diverse quando
processati indipendentemente.

- **`naming.py`**: nuovo campo `StemDescriptor.link_id`, calcolato da
  `_link_id_from_name()`. Riusa lo stesso stile word-boundary già in uso per
  dx/sx/R/L (evita falsi positivi tipo "Outro" che contiene "out" come
  substring ma non come token isolato). Riconosce dx/sx/r/right/l/left/in/
  out/top/bottom come suffissi di gruppo; solo il **basename** del file
  viene usato (non il path completo, per non far collidere gruppi diversi
  su parole ricorrenti nel nome cartella tipo "Vocal Stems Pitch
  Correction"), e solo l'**ultimo** token trovato viene rimosso.
- **`mixengine.py`**: prima del thread pool, i nomi con lo stesso `link_id`
  (solo se compaiono **almeno 2 volte** nella sessione — un `link_id` senza
  partner viene processato come sempre) vengono raggruppati; la risonanza
  viene misurata una sola volta sulla **somma** dei segnali dry del gruppo
  e passata a ogni membro via il parametro `forced_resonance` di
  `_process_stem` (sentinel `_RESONANCE_UNSET` per distinguere "nessun
  gruppo, calcola come sempre" da "gruppo senza risonanza da tagliare").
  Evento `link_group` emesso per visibilità in log/GUI.
- **Non ancora esteso**: l'HPF e la classificazione strumento (`other`/
  `drums`) restano per-stem indipendenti anche per stem linkate — solo la
  risonanza adattiva è condivisa. Se in pratica emergono ancora artefatti
  di fase su gruppi linkati, il prossimo passo è unificare anche HPF cutoff
  e `classify_instrument()` sulla somma del gruppo.

---

## 9. Addendum Settembre 2026 — Audit di disposizione post-riconciliazione `research_report.md` (Wave 2, task D2)

Contesto: la riconciliazione di `docs/research_report.md` (commit `40b7e56`, task D1) ha
corretto la colonna "Current" della tabella §4.6 del report, che precedeva il commit di
calibrazione `033043c`. Questo addendum è la verifica indipendente (task D2) di ogni riga
di quella tabella e delle Sezioni 1-3 del report contro il codice live, con la regola di
decisione concordata: **nessuna modifica di costanti audio senza validazione d'ascolto**
(utente non disponibile) — una delta "di gusto" (non un difetto misurabile) si RINVIa, non
si applica. Esito: **zero modifiche al codice**; nessuna delta difendibile residua.

### 9.1 Disposizione riga-per-riga della tabella §4.6 (13 righe, verificate sul live)

| # | Raccomandazione report | Decisione | Valore live misurato (file:line) | Razionale |
|---|---|---|---|---|
| 1 | Hip-Hop presence 3500Hz +2.5dB | APPLICATA — nessuna azione | `EQBand(3500, 2.5, 0.8, "peak")` — `redline/analysis/genre.py:81` | Verificato identico |
| 2 | Hip-Hop air 10000Hz +2.0dB | APPLICATA | `EQBand(10000, 2.0, 0.7, "high_shelf")` — `genre.py:82` | Verificato identico |
| 3 | Pop 250Hz −0.5dB | APPLICATA | `EQBand(250, -0.5, 1.2, "peak")` — `genre.py:49` | Verificato identico |
| 4 | Pop air 12000Hz +2.5dB | APPLICATA | `EQBand(12000, 2.5, 0.7, "high_shelf")` — `genre.py:52` | Verificato identico |
| 5 | Classical air 10000Hz +1.5dB | APPLICATA | `EQBand(10000, 1.5, 0.7, "high_shelf")` — `genre.py:62` | Verificato identico |
| 6 | EDM air 10000Hz +2.5dB | APPLICATA | `EQBand(10000, 2.5, 0.7, "high_shelf")` — `genre.py:42` | Verificato identico |
| 7 | EDM sub 60Hz +4.0dB | APPLICATA | `EQBand(60, 4.0, 0.7, "low_shelf")` — `genre.py:38` | Verificato identico |
| 8 | PARALLEL_BUS_MIX 0.15 → 0.20 | **RIGETTATA (ulteriore modifica)** | `PARALLEL_BUS_MIX = 0.20` — `redline/mixengine.py:150` | Il valore live è già 0.20: la raccomandazione è già soddisfatta, nulla da "alzare". La Sezione 6.1 (riga 584) documenta la riduzione deliberata da 22% a 15% perché mix 22% + 8:1 favoriva i transienti della batteria sulla voce; il commento in `mixengine.py:145-150` documenta il successivo riporto a 0.20 entro il range di ricerca 10-20%. Non si alza oltre (riaprirebbe esattamente il problema chiuso in 6.1) e non si sposta in alcuna direzione senza ascolto. |
| 9 | MUSIC_BUS_SIDE_WIDTH_DB 1.0 → 1.5 | APPLICATA | `MUSIC_BUS_SIDE_WIDTH_DB = 1.5` — `mixengine.py:188` | Verificato identico |
| 10 | DRUM_SATURATION_MIX 0.18 → 0.22 | APPLICATA | `DRUM_SATURATION_MIX = 0.22` — `mixengine.py:194` | Verificato identico |
| 11 | BASS_EXCITER_MIX 0.25 → 0.30 | APPLICATA | `BASS_EXCITER_MIX = 0.30` — `mixengine.py:202` | Verificato identico |
| 12 | Drum room send 0.08 → 0.10 | APPLICATA | `def drum_room_send(..., mix: float = 0.10)` — `redline/fxsends.py:42` | Verificato identico |
| 13 | Foreground air 8000Hz +1.0dB → 10000Hz +1.5dB | APPLICATA | `FOREGROUND_AIR_SHELF_HZ = 10000.0` / `FOREGROUND_AIR_GAIN_DB = 1.5` — `redline/depth.py:30-31` | Verificato identico |

### 9.2 Scansione Sezioni 1-3 del report: nessuna delta aperta

Compressione bus per genere (§2.1-2.5) — tutte le raccomandazioni numerate già applicate:

| Genere | Raccomandazione report | Valore live (`redline/analysis/genre.py`) |
|---|---|---|
| EDM/Urban | ratio 5:1 → 3-4:1; attack 3 → 10-15ms; thr −22 → −16/−18 | `ratio=3.5, attack_ms=12.0, threshold_db=-18.0` — `genre.py:44` |
| Pop/Rock | attack 8 → 15-20ms | `attack_ms=18.0` — `genre.py:54` |
| Acoustic/Classical | (nessuna modifica suggerita) | invariato — `genre.py:64` |
| Jazz | attack 12 → 15-20ms | `attack_ms=18.0` — `genre.py:74` |
| Hip-Hop | attack 5 → 10ms; thr −20 → −16/−18 | `attack_ms=10.0, threshold_db=-17.0` — `genre.py:84` |

Catene blueprint (§2.6-2.8) e target LUFS (§3): verificati identici al live —
`mixengine.py:433-434` (peak catcher/leveler voce), `mixengine.py:444` (glue batteria),
`masterengine.py:48-64` (ceiling TP/clip, split multiband, ricette low/mid/high),
`masterengine.py:41-46` + `_target_lufs_for_genre` (`masterengine.py:85-88`) (LUFS per
piattaforma, selezione genre-aware). Nessuna delta.

Note residue di gusto nel §1, senza raccomandazione numerata né difetto misurabile — RINVIATE (richiedono ascolto, non modifica meccanica):
- Rock low shelf +1dB vs "+2dB per più peso" (§1.1) — live `EQBand(80, 1.0, …)` `genre.py:48`.
- Pop 1kHz leggero taglio vs 0.0dB; presence 3kHz vs 4kHz "più moderno" (§1.2) — live `genre.py:50-51`.
- EDM sub +4 vs "+4/+5dB club" (§1.3) — già al valore raccomandato e applicato (`genre.py:38`).
- Jazz warmth boost 150-300Hz (§1.6) — live `genre.py:69`.

Staleness residua del report (documentata qui, non corretta nel report per vincolo del task D2):
- §4.1 colonna "Current" outdated anche per `PARALLEL_BUS_MIX` (15% → live 0.20, `mixengine.py:150`), `DRUM_SATURATION_MIX` (18% → 0.22, `:194`), `BASS_EXCITER_MIX` (25% → 0.30, `:202`), `MUSIC_BUS_SIDE_WIDTH_DB` (1.0 → 1.5, `:188`) — oltre alle 4 già elencate nella nota di riconciliazione del report.
- Tabella §2 "RedLine" per-genere: attacchi/soglie EDM/Pop/Jazz/Hip-Hop anteriori a `033043c` (le raccomandazioni derivate sono comunque applicate, vedi tabella sopra).

### 9.3 Esito

Nessuna delta difendibile contro una misura/standard e non contraddicente una decisione
documentata: **nessuna costante modificata, nessun test aggiunto**. Le voci rinviate
richiedono validazione d'ascolto (A/B loudness-matched via `redline/ab_compare.py`)
prima di qualsiasi ulteriore modifica audio.

---

## 10. Addendum Settembre 2026 — Universalizzazione (lingue, strumenti, generi, parametri, piattaforme)

Giro di ampiezza (Wave 1/2, Track A/B/C1/E1/G): il motore riconosce più lingue e
convenzioni DAW, più famiglie di strumenti e più generi, e l'utente può pilotare più
parametri. **Nessun default esistente è cambiato**: le espansioni sono additive e i
nuovi parametri sono neutri di default. Ogni conteggio è verificato sul codice live
(`redline.genres.GENRE_NAMES`, `redline.instrumentstack.RECIPES`,
`redline.platforms.PLATFORM_TARGETS`, `redline.presets._BUILTIN_PRESETS`).

### 10.1 Nomenclatura stem multilingua e DAW-aware (`naming.py`)

Il parsing dei nomi file (ruolo/layer/sezione/pan/link) ora copre:

- **Lingue**: inglese, italiano, spagnolo, francese, tedesco. Esempi di token aggiunti:
  voce (`voz`, `voces`, `voix`, `stimme`, `gesang`), basso (`bajo`, `basse`), batteria
  (`bateria`, `bombo`, `caja`, `batterie`, `caisse claire`, `schlagzeug`, `trommel`).
- **Convenzioni DAW**: i numeri di traccia iniziali (`01_Kick`, `02 - Snare`, `01Kick`)
  vengono rimossi per il matching degli hint (il `raw_name` e il `link_id` conservano la
  stringa originale); le varianti numerate di take (`L1`, `R1`, `L100`) sono riconosciute
  dai pattern `_R_NUM_PATTERN`/`_L_NUM_PATTERN`.
- **Elementi di kit** aggiunti: `hat`, `hihat`, `hi-hat`, `cymbal`, `crash`, `ride`,
  `tom`, `clap`, `rim`, `overhead` (sottostringa), più `oh`/`hh` a word boundary.
- **Sezioni** aggiunte: `prechorus`, `intro`, `outro`, `drop`, `breakdown`, `refrain`,
  `interlude`, `coda`, `tag` (oltre a chorus/verse/bridge già presenti).
- **Pan esplicito**: token di centro (`center`/`centre`/`mono`) forzano `pan=0.0` anche
  se un altro token suggerirebbe un lato; `L1`/`R1` numerati riconosciuti.
- **Token di link** aggiunti per i gruppi multi-mic/multi-take: `dx`, `sx`, `r`, `right`,
  `l`, `left`, `in`, `out`, `top`, `bottom`, `close`, `far`, `near`, `mic1`, `mic2`, `amp`,
  `front`, `back`, `di`.

**Fix di falsi positivi**: i token corti/pericolosi sono ora matchati a word boundary
(`textmatch.contains_word`), il che elimina casi reali come `percent` → batteria
(il token `perc` era sottostringa) e `invoice` → voce (il token `voice` era sottostringa).
La tabella morta `MAIN_HINTS` è stata rimossa.

### 10.2 Famiglie di strumenti: da 16 a 21 categorie (`instrumentstack.py`)

Cinque nuove categorie, ognuna con la propria ricetta (HPF, ratio/soglia/attack/release
del compressore, EQ correttivo, bias di invio riverbero):

| Categoria | HPF | EQ chiave | Compressione | Riverbero |
|---|---|---|---|---|
| `ACCORDION` (fisarmonica/armonica/melodica/bandoneon) | 120Hz | -1.5dB@350Hz (corpo ancia), +1.5dB@2kHz (presenza) | 2.2:1, attack 12ms | ×1.1 |
| `HARPSICHORD` (clavicembalo/clavicordo/spinetta) | 180Hz | -2dB@400Hz (corpo), +1.5dB@4kHz (definizione plettro) | 2.5:1, attack 3ms | ×0.7 |
| `FOLK_PLUCK` (banjo/mandolino/ukulele/lap steel/dobro/dulcimer) | 110Hz | +1.5dB@3kHz (attacco plettro), +1dB shelf 9kHz (aria) | 2.8:1, attack 4ms | ×0.95 |
| `WORLD_STRINGS` (erhu/oud/bouzouki/balalaika/kora...) | 140Hz | -1.5dB@3.2kHz (ruvidezza), +1dB shelf 9kHz (aria) | 2.0:1, attack 18ms | ×1.25 |
| `WORLD_WINDS` (duduk/shakuhachi/bansuri/ney/ocarina/cornamusa/zampogna...) | 180Hz | -1dB@450Hz (mud di fiato), +1.5dB shelf 7.5kHz (aria) | 2.0:1, attack 15ms | ×1.2 |

Le ricette EQ/compressione sono punti di partenza informati da fonti secondarie
(iZotope genre guides, Sound On Sound, MusicProductionWiki), stesso status euristico
delle ricette originali della §6.2 — non esiste uno standard primario per queste
famiglie. **Fix di falsi positivi da sottostringa**: i token corti/pericolosi
(`organ`, `harp`, `bell`, `pad`, `keys`, `arp`, `chant`, `coro`, `cori`, `mmh`, `ooh`,
`aahs`, `wash`, `drone`, `swell`, `clav`, `clavi`, `b3`, `oud`, `ney`, `uke`, `lead`)
sono matchati a word boundary, eliminando `organic` → organ e `sharp` → harp.

### 10.3 Generi: da 6 a 21 (`analysis/genre.py`, `reference_profiles.py`, `qc.py`, `fxsends.py`)

I 6 profili originali (EDM/Urban, Pop/Rock, Acoustic/Classical, Jazz/Vintage, Hip-Hop,
Balanced) sono **invariati**. I 15 nuovi sono additivi. `detect_genre` è stato esteso
**solo nel ramo finale `else`** (la regione che il vecchio albero mappava a "Balanced"),
quindi nessun input esistente cambia genere misurato.

Ancoraggi di loudness/crest (LUFS integrato / PLR crest, dB) e target risolti:

| Genere | LUFS tipico | Crest tipico | Crest target | Mono target | Bus EQ chiave | Glue comp |
|---|---|---|---|---|---|---|
| Lo-Fi | -10..-13 | 10-14 | 12.0 | 0.80 | -2dB@4kHz, -3dB shelf 10kHz (roll-off nastro) | 2.5:1, 25ms |
| Cinematic | -14..-18 | 14-20 | 17.0 | 0.70 | +2dB shelf 40Hz, +2dB shelf 12kHz | 1.8:1, 30ms |
| Drum & Bass | -6..-9 | 8-12 | 10.0 | 0.90 | +3.5dB shelf 50Hz, +2dB@4kHz | 4.0:1, 8ms |
| Reggaeton | -8..-10 | 9-13 | 11.0 | 0.88 | +3.5dB shelf 55Hz, -2dB@300Hz | 3.5:1, 12ms |
| Metal | -8..-11 | 10-14 | 12.0 | 0.82 | -3dB@400Hz (mid scoop), +2.5dB@3kHz | 4.5:1, 5ms |
| Country | -12..-16 | 12-16 | 14.0 | 0.78 | +1dB@1.5kHz, +1.5dB@3.5kHz | 2.5:1, 20ms |
| Gospel | -12..-16 | 12-16 | 14.0 | 0.74 | +1.5dB shelf 70Hz, +2dB shelf 11kHz | 2.5:1, 22ms |
| Funk | -10..-14 | 11-15 | 13.0 | 0.80 | -1.5dB@350Hz, +2dB@4kHz | 3.0:1, 10ms |
| Ambient | -14..-18 | 15-22 | 18.5 | 0.66 | +2.5dB shelf 12kHz | 1.5:1, 40ms |
| Trap | -8..-11 | 8-12 | 10.0 | 0.90 | +4dB shelf 45Hz, +2.5dB@5kHz | 4.0:1, 8ms |
| R&B | -12..-16 | 11-15 | 13.0 | 0.84 | +2.5dB shelf 60Hz, -2dB@300Hz | 3.0:1, 15ms |
| Blues | -12..-16 | 12-16 | 14.0 | 0.76 | +1dB shelf 70Hz, +1.5dB@3kHz | 2.5:1, 20ms |
| Reggae | -10..-14 | 11-15 | 13.0 | 0.86 | +3dB shelf 50Hz, -2dB@300Hz | 3.0:1, 18ms |
| Afrobeats | -9..-12 | 9-13 | 11.0 | 0.88 | +3dB shelf 55Hz, +2dB@4kHz | 3.5:1, 12ms |
| K-Pop | -7..-10 | 9-13 | 11.0 | 0.82 | +3dB shelf 60Hz, +2.5dB@3.5kHz | 3.5:1, 10ms |

**Fonti degli ancoraggi di loudness**: Spotify normalizza a -14 LUFS, Apple Music a -16,
YouTube a -14 (dal 2019); i master club/EDM girano più caldi (-6..-9). I range di
crest/PLR sono il carattere dinamico tipico del genere (tabelle PLR di
MusicProductionWiki, loudness-war references). I target di crest sono il punto medio del
range ricercato; i target mono interpolano tra il floor di pass/fail di `qc.py` (> 0.6)
e la correlazione perfetta (1.0) — generi club/sub-heavy più stretti, generi con
stereo di sala più larghi. Le mosse EQ/dinamica sono informate da fonti secondarie
(iZotope genre guides, Sound on Sound, MusicProductionWiki), marcate `[secondary]` nel
codice dove non esiste una spec primaria.

Ogni nuovo genere ha anche un target spettrale a 6 bande in `qc.TARGET_BAND_RATIOS`
e un bias dry/wet in `fxsends.py` (`DRY_GENRES` = EDM/Hip-Hop/Trap/Drum & Bass/
Reggaeton/Afrobeats; `WET_GENRES` = Ambient/Cinematic/Gospel).

### 10.4 `genre_override` ora cablato (`analyze.py`, `cli.py`, `batch.py`, `app/api.py`)

Prima campo morto: una selezione di genere utente/preset non aveva alcun effetto.
Ora `analyze()` accetta `genre_override` e `apply_genre_override()` sostituisce
`analysis.genre` con il profilo richiesto (via `redline.genres.resolve_genre_name`,
con warning e fallback al genere misurato se il nome è sconosciuto). CLI, batch e API
lo passano tutti, quindi la scelta di genere pilota realmente bus EQ, target LUFS e QC.

### 10.5 Piattaforme: correzione YouTube e nuove piattaforme (`platforms.py`)

| Piattaforma | LUFS target | Nota |
|---|---|---|
| Spotify | -14.0 | invariato |
| Apple Music | -16.0 | invariato |
| YouTube | **-14.0** | **corretto da -13**: YouTube normalizza a -14 LUFS dal 2019 |
| Tidal | -14.0 | nuovo |
| Amazon Music | -14.0 | nuovo |
| Deezer | -14.0 | nuovo |
| Club | -9.0 | invariato (target più caldo per materiale EDM/club) |

`redline/platforms.py` è ora la fonte unica di verità; `masterengine` riesporta il dict,
quindi `from redline.masterengine import PLATFORM_TARGETS` continua a restituire lo
stesso oggetto. `PLATFORM_CHOICES` = `("auto",) + tuple(PLATFORM_TARGETS)`.

### 10.6 7 nuovi parametri utente (`wizard.py`, `MixPreferences`)

Tutti **neutri di default** (0.0 = default del motore, nessun cambiamento), quindi una
`MixPreferences` non toccata si comporta esattamente come prima. Sono override opzionali
consumati dal motore; il wizard interattivo non li chiede.

| Parametro | Range | Semantica a 0.0 |
|---|---|---|
| `mono_compatibility_target` | 0.0..1.0 | auto/genre default (target QC mono) |
| `bass_mono_below_hz` | 0.0..300.0 | default del motore (120 Hz) |
| `reference_lufs_target` | -30.0..0.0 | usa il target piattaforma/genere |
| `saturation_amount` | -1..+1 | default del motore, nessun cambiamento (scala la saturazione per-strumento/batteria) |
| `deess_amount` | -1..+1 | default del motore, nessun cambiamento (scala l'intensità del de-esser) |
| `compression_amount` | -1..+1 | default del motore, nessun cambiamento (bias globale sui ratio dei compressori per-stem) |
| `vocal_reverb_amount` | -1..+1 | default del motore, nessun cambiamento (bias sull'invio spazio della voce) |

Corretto anche un disallineamento di range dello schema su `stereo_width` (0.0..1.0) e
`transient_attack`/`transient_sustain` (-6..+6), allineati al clamp di `__post_init__`.

### 10.7 Nuovi moduli di infrastruttura

- **`redline/textmatch.py`**: un unico matcher di token per le due semantiche usate
  leggendo nomi scritti dall'utente — `contains_token(text, token, mode="substr"|"word")`,
  `contains_any`, `contains_word`. Il boundary set è lo stesso che `naming.py` ha sempre
  usato (whitespace, underscore, punto, slash, backslash, parentesi, graffe, quadre,
  trattino). I token sono `re.escape`'d e il matching è case-insensitive.
- **`redline/genres.py`**: registro canonico dei generi (`GENRE_NAMES`, 21 nomi, stesso
  ordine di `analysis.genre._PROFILES`), con `resolve_genre_name()`/`is_known_genre()`.
  `tests/test_registry.py` blocca i due insieme.
- **`redline/platforms.py`**: registro canonico delle piattaforme (vedi §10.5).

### 10.8 Conteggi verificati (live)

| Elemento | Prima | Dopo | Fonte |
|---|---|---|---|
| Generi | 6 | **21** | `redline.genres.GENRE_NAMES` |
| Categorie strumenti | 16 | **21** | `redline.instrumentstack.RECIPES` |
| Piattaforme | 4 | **7** | `redline.platforms.PLATFORM_TARGETS` |
| Preset built-in | 22 | **24** | `redline.presets._BUILTIN_PRESETS` |
| Parametri utente neutri | 0 | **7** | `redline.wizard.MixPreferences` |

---

*Fine documento specifiche. Tutti i conflitti tra le tre fonti sono stati identificati e risolti nella Sezione 0, dove per ogni divergenza è stata scelta la soluzione migliore (più chiara, più specifica, o più adatta a un motore DSP headless). I valori numerici sono stati unificati nella Sezione 4. L'architettura di routing nella Sezione 5 integra tutte e tre le fonti in un flusso coerente. La Sezione 6 documenta il secondo giro di ricerca (fonti web) e le correzioni applicate per il problema "mix inascoltabile". La Sezione 7 documenta l'estensione Reference Profiles / Feedback Iterativo / Re-run Masking / A/B Compare. La Sezione 9 documenta l'audit di disposizione post-riconciliazione del research report (zero modifiche audio). La Sezione 10 documenta l'universalizzazione (lingue, strumenti, generi, parametri, piattaforme).*
