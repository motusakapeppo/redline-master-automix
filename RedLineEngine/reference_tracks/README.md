# Reference tracks (drop folder)

Questa cartella alimenta il modulo `redline/reference_profiles.py`: mette a
disposizione del motore delle curve spettrali di riferimento *misurate* da
brani reali, invece delle sole curve teoriche in `redline/qc.py` (`TARGET_BAND_RATIOS`).

## Come funziona

1. Metti almeno 3 (idealmente 20-30) file audio lossless (WAV/FLAB/AIFF) di
   brani **prodotti/masterizzati professionalmente** nella sottocartella del
   genere corrispondente (vedi elenco sotto).
2. Esegui:
   ```
   python -m redline.reference_profiles
   ```
3. Il modulo calcola la Long-Term Average Spectrum (LTAS) di ogni brano,
   fa la media per genere e scrive `redline/targets/target_<slug>.json`.
4. Da quel momento `qc.py` (fase di mastering) confronta l'output del motore
   contro questa media reale invece che contro la curva teorica di fallback.

## Cartelle per genere

- `edm_urban/`
- `hip_hop/`
- `pop_rock/`
- `acoustic_classical/`
- `jazz_vintage/`
- `balanced/` (profilo di fallback quando `detect_genre()` non riconosce con sicurezza uno degli altri 5 generi)

## Provenienza dei file audio: IMPORTANTE

**Non usare mai brani piratati o di provenienza incerta** — file da siti
"download gratis WAV" sono quasi sempre ricampionati da MP3 lossy (rovinano
la mappatura) o distribuiti senza licenza.

Fonti legittime:
- **Acquisto lossless** (Bandcamp, Qobuz, Tidal HiFi/Max) di brani che possiedi.
- **Creative Commons / royalty-free professionalmente prodotti**: Free Music
  Archive, ccMixter, la sezione CC di Jamendo — verifica sempre la licenza
  specifica del singolo brano prima di usarlo.
- Le tue stesse produzioni/mix già pubblicati.

Evita comunque tracce amatoriali/demo anche se legalmente disponibili: la
mappatura ha senso solo se le tracce di riferimento sono davvero al livello
di mix/master professionale del genere che rappresentano.

I file audio dentro `edm_urban/`, `hip_hop/`, ecc. **non vengono committati**
(vedi `.gitignore`) — solo la struttura delle cartelle e questo README sono
tracciati in git.
