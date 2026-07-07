# Piano di Correzione: Timing Alignment Drift

> **QUESTO PIANO È STATO CORRETTO — vedi .omo/2026-07-08-timing-verification-verdict.md per la verifica**

## Contesto

Il timing alignment delle voci doppie (double vocals) rispetto al lead funziona
correttamente sul segnale dry (pre-processing), ma dopo il passaggio attraverso
la catena DSP per-stem, l'allineamento non è più garantito.

## Sospetto #1 (CORRETTO): Il processing IIR differenziale

Ogni stem passa attraverso una catena di filtri IIR diversa (lead: 3-4 filtri,
drums: 1-2, bass: 0-1). Questi filtri introducono un group delay (ritardo di
gruppo) che è DIVERSO per ogni stem. L'allineamento iniziale avviene sul segnale
dry (non processato), ma dopo il processing gli stem non sono più allineati tra
loro.

Immagina di avere due tracce perfettamente allineate. La voce lead passa
attraverso 4 filtri IIR che la ritardano di 2ms. La batteria passa attraverso
2 filtri che la ritardano di 1ms. Il risultato: la batteria sente 1ms prima
della voce — un micro-shift che si accumula in modo diverso per ogni traccia.

## Sospetto #2 (SCARTATO): Race condition nel thread pool

Analisi del codice ha confermato che il thread pool è sicuro: _instrument_cache è
pre-popolato prima del pool, _process_stem è read-only sulla cache, e processed è
popolato sul main thread. Escluso.

## Piano d'Azione

### Step 1 — Fix: Ri-allineamento post-processing (1 ora)

Aggiungere in mixengine.py, dopo il thread pool, un passo che ri-allinea ogni stem
non-lead al lead processato via cross-correlation (align_to_reference).

Dove: redline/mixengine.py, dopo riga 804
Cosa: ri-alignare processed[name] a lead_processed per ogni stem non-lead
Rischio: Molto basso. align_to_reference è già usato per le double vocals.

### Step 2 — Test di regressione (1 ora)

Verificare che il test suite passi e che il ri-allineamento non introduca nuovi shift.

### Step 3 — Documentazione (30 min)

Aggiornare README con Known Issue sul timing alignment.
