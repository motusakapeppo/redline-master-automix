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

*Fine documento specifiche. Tutti i conflitti tra le tre fonti sono stati identificati e risolti nella Sezione 0, dove per ogni divergenza è stata scelta la soluzione migliore (più chiara, più specifica, o più adatta a un motore DSP headless). I valori numerici sono stati unificati nella Sezione 4. L'architettura di routing nella Sezione 5 integra tutte e tre le fonti in un flusso coerente. La Sezione 6 documenta il secondo giro di ricerca (fonti web) e le correzioni applicate per il problema "mix inascoltabile".*
