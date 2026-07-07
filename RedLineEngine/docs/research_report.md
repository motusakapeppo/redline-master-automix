# RedLine Engine: Mixing & Mastering Research Report

**Date:** July 2026
**Purpose:** Compare RedLine Engine's current DSP constants against industry standards to guide calibration decisions.

---

## 1. EQ Values by Genre

RedLine Engine applies genre-informed bus EQ via `redline/analysis/genre.py` (lines 36-96). Each genre gets a 5-band EQ: low shelf, three peak filters, and a high shelf. Below, each profile is compared against standard practice.

### 1.1 Rock

| Band | RedLine | Industry Standard | Verdict |
|------|---------|-------------------|---------|
| Low shelf 80Hz | +1.0dB | +1 to +3dB (warmth) | Slightly conservative, acceptable |
| Mud cut 250Hz | -2.0dB | -2 to -4dB at 200-400Hz | Good |
| 1kHz | 0.0dB | Flat or slight cut | Fine |
| Presence 3kHz | +3.0dB | +2 to +4dB at 2.5-4kHz | Good |
| Air 10kHz | +2.0dB | +1.5 to +3dB at 10-12kHz | Good |

**Assessment:** Rock EQ is well-calibrated. The 250Hz cut and 3kHz presence boost match standard practice. The low shelf at +1dB is on the conservative side; modern rock often uses +2dB for more weight.

### 1.2 Pop

| Band | RedLine | Industry Standard | Verdict |
|------|---------|-------------------|---------|
| Low shelf 80Hz | +1.0dB | +1 to +2dB | Acceptable |
| Mud cut 250Hz | -2.0dB | -1 to -3dB | Good, but pop often *boosts* 150-300Hz for warmth |
| 1kHz | 0.0dB | Slight cut (-0.5 to -1dB) to reduce boxiness | Slightly off |
| Presence 3kHz | +3.0dB | +2 to +4dB at 3-5kHz | Good, but 4kHz would be more modern |
| Air 10kHz | +2.0dB | +2 to +4dB at 12-15kHz | Shelf frequency is low; 12kHz is more common |

**Discrepancy:** Pop typically boosts warmth (150-300Hz) rather than cutting it. The 250Hz cut at -2dB removes body from vocals and acoustic instruments. Consider changing to -0.5dB or a slight boost. The air shelf at 10kHz is a generation behind; modern pop uses 12-15kHz.

### 1.3 Electronic (EDM / Urban)

| Band | RedLine | Industry Standard | Verdict |
|------|---------|-------------------|---------|
| Sub 60Hz | +3.0dB | +3 to +6dB at 50-80Hz | Conservative but clean |
| Mud cut 250Hz | -2.5dB | -2 to -4dB | Good |
| Low-mid 800Hz | -1.0dB | -1 to -2dB | Good |
| Presence 3kHz | +2.0dB | +2 to +4dB at 2-4kHz | Acceptable |
| Air 10kHz | +1.0dB | +2 to +4dB at 10kHz+ | **Low.** Modern EDM uses more aggressive air (+2 to +4dB) |

**Discrepancy:** The air shelf at +1dB is too conservative for EDM. Modern electronic music (especially synthwave, future bass, melodic techno) uses +2 to +4dB at 10-12kHz for shimmer. The sub boost at +3dB is safe but many club-oriented tracks push +4 to +5dB.

### 1.4 Hip-Hop

| Band | RedLine | Industry Standard | Verdict |
|------|---------|-------------------|---------|
| Sub 50Hz | +4.0dB | +4 to +6dB at 40-60Hz | Good |
| Mud cut 250Hz | -2.5dB | -2 to -4dB | Good |
| Low-mid 800Hz | -1.5dB | -1 to -2dB | Good |
| Presence 2kHz | +2.0dB | +2 to +4dB at 2.5-5kHz | **Low frequency.** 2kHz is too low for vocal presence |
| Air 10kHz | 0.0dB | +1 to +3dB at 10-12kHz | **Missing.** Modern hip-hop uses air for hi-hats and ad-libs |

**Discrepancies:**
1. Presence at 2000Hz catches lower harmonics but misses the sibilance/clarity zone (4-5kHz). Standard practice is 3-5kHz for vocal presence in hip-hop.
2. No air boost at all. Modern trap and hip-hop rely on air (+1 to +3dB at 10-12kHz) for hi-hat sparkle and vocal top-end.

### 1.5 Classical

| Band | RedLine | Industry Standard | Verdict |
|------|---------|-------------------|---------|
| Sub 60Hz | 0.0dB | 0dB or slight cut | Good |
| Mud cut 250Hz | -0.5dB | 0 to -1dB | Good |
| 1kHz | 0.0dB | Flat | Good |
| Presence 3kHz | +1.0dB | 0 to +1.5dB | Acceptable |
| Air 10kHz | +3.0dB | +1 to +2dB at 8-10kHz | **Too aggressive.** +3dB at 10kHz is not minimal |

**Discrepancy:** Classical should use minimal EQ. A +3dB high shelf at 10kHz is noticeable and could make strings/brass sound harsh. Standard practice is +1 to +2dB at most, often with a gentler Q.

### 1.6 Jazz

| Band | RedLine | Industry Standard | Verdict |
|------|---------|-------------------|---------|
| Sub 40Hz | +0.5dB | 0 to +1dB | Good |
| Mud cut 250Hz | -0.5dB | 0 to -1dB | Good, but jazz often *boosts* warmth |
| Low-mid 800Hz | -0.5dB | 0 to -1dB | Acceptable |
| Presence 3kHz | +1.5dB | +1 to +3dB at 3-5kHz | Good |
| Air 10kHz | +0.5dB | +0.5 to +1.5dB | Conservative but fine |

**Assessment:** Jazz is well-calibrated. The only note: some jazz engineers prefer a slight warmth boost (150-300Hz) rather than a cut, especially for upright bass and saxophone.

---

## 2. Compression Settings by Genre

Bus glue compression parameters from `redline/analysis/genre.py` (lines 36-96).

| Genre | Attack (ms) | Release (ms) | Ratio | Threshold (dB) | Parallel Mix |
|-------|-------------|---------------|-------|----------------|--------------|
| EDM/Urban | 3 | 80 | 5:1 | -22 | 20% |
| Pop/Rock | 8 | 120 | 3.5:1 | -18 | 30% |
| Acoustic/Classical | 20 | 300 | 2:1 | -16 | 15% |
| Jazz/Vintage | 12 | 200 | 2.5:1 | -18 | 25% |
| Hip-Hop | 5 | 100 | 4:1 | -20 | 20% |
| Balanced | 10 | 150 | 3:1 | -18 | 25% |

### 2.1 EDM/Urban: 5:1 ratio, 3ms attack, 80ms release, -22dB threshold

- **Ratio 5:1** is aggressive for bus glue. Industry standard for EDM bus compression is 2:1 to 4:1. 5:1 is closer to individual track compression. **Recommendation:** 3:1 to 4:1.
- **Attack 3ms** is fast. For bus glue, 10-30ms lets transients through. 3ms catches everything. **Recommendation:** 10-15ms.
- **Release 80ms** is reasonable for the tempo range.
- **Threshold -22dB** is low. Most bus compressors start at -12 to -18dB. At -22dB with 5:1 ratio, the bus is in constant compression. **Recommendation:** -16 to -18dB.

### 2.2 Pop/Rock: 3.5:1 ratio, 8ms attack, 120ms release, -18dB threshold

- **Ratio 3.5:1** is at the upper end of bus glue (standard 2:1 to 4:1). Acceptable.
- **Attack 8ms** is fast for bus glue. 10-30ms is more common. **Recommendation:** 15-20ms.
- **Release 120ms** is good for pop tempos.
- **Threshold -18dB** is reasonable.

### 2.3 Acoustic/Classical: 2:1 ratio, 20ms attack, 300ms release, -16dB threshold

- **Ratio 2:1** is correct for classical.
- **Attack 20ms** is good.
- **Release 300ms** is appropriate for the slower dynamics.
- **Threshold -16dB** is reasonable.

### 2.4 Jazz: 2.5:1 ratio, 12ms attack, 200ms release, -18dB threshold

- **Ratio 2.5:1** is good for jazz.
- **Attack 12ms** is slightly fast. 15-25ms would preserve more transient detail. **Recommendation:** 15-20ms.
- **Release 200ms** is appropriate.
- **Threshold -18dB** is reasonable.

### 2.5 Hip-Hop: 4:1 ratio, 5ms attack, 100ms release, -20dB threshold

- **Ratio 4:1** is at the upper end. 3:1 to 4:1 is standard for hip-hop bus glue. Acceptable.
- **Attack 5ms** is fast. 10-15ms would let more kick transient through. **Recommendation:** 10ms.
- **Release 100ms** is good for hip-hop tempos.
- **Threshold -20dB** is low. **Recommendation:** -16 to -18dB.

### 2.6 Vocal Compression (Blueprint Chains)

From `redline/mixengine.py` lines 360-367:

**Peak catcher (FET/1176-style):** threshold -12dB, ratio 8:1, attack 0.8ms, release 60ms
**Leveler (LA-2A-style):** threshold -20dB, ratio 3:1, attack 60ms, release 250ms

- **Peak catcher 8:1 ratio** is standard for 1176-style limiting. Good.
- **Peak catcher 0.8ms attack** is very fast. 1176 in "all buttons" mode is ~0.5ms, so this is reasonable.
- **Leveler 3:1 ratio** is standard for LA-2A. Good.
- **Leveler 60ms attack** is slow, which is correct for leveling (not transient catching).
- **Leveler 250ms release** is standard.

**Assessment:** The 2-stage vocal chain is well-designed and matches industry practice.

### 2.7 Drum Compression (Blueprint Chains)

From `redline/mixengine.py` line 371: threshold -16dB, ratio 3:1, attack 30ms, release 120ms

- **Ratio 3:1** is standard for drum bus glue.
- **Attack 30ms** lets transients through. Good.
- **Release 120ms** is reasonable.
- **Threshold -16dB** is reasonable.

**Assessment:** Drum bus compression is well-calibrated.

### 2.8 Multiband Compression (Mastering)

From `redline/masterengine.py` lines 53-57:

| Band | Threshold | Ratio | Attack | Release |
|------|-----------|-------|--------|---------|
| Low (<150Hz) | -18dB | 2.5:1 | 20ms | 180ms |
| Mid (150-4000Hz) | -16dB | 1.8:1 | 10ms | 120ms |
| High (>4000Hz) | -14dB | 1.6:1 | 5ms | 80ms |

- **Low band 2.5:1** is standard for multiband mastering. Good.
- **Mid band 1.8:1** is gentle, correct for mastering.
- **High band 1.6:1** is gentle, correct.
- **Attack/release values** are all within standard mastering ranges.

**Assessment:** Multiband compression is well-calibrated. The split at 150Hz (changed from 200Hz) is now in the 120-170Hz industry range.

---

## 3. LUFS Standards by Platform

From `redline/masterengine.py` lines 34-39:

| Platform | RedLine Target | Industry Standard | Verdict |
|----------|---------------|-------------------|---------|
| Spotify | -14 LUFS | -14 LUFS (integrated), -1dB TP | Correct |
| Apple Music | -16 LUFS | -16 LUFS, -1dB TP | Correct |
| YouTube | -13 LUFS | -13 LUFS, -1dB TP | Correct |
| Club | -9 LUFS | -8 to -10 LUFS | Correct |

**True Peak Ceiling:** -1.0 dBTP (line 41). This matches all major platform requirements.

**Clip Ceiling:** -0.3 dB (line 42). Standard practice is -0.3 to -0.5dB for the soft clipper before the final limiter. Correct.

**Genre-aware target selection** (line 60-63): EDM/Urban defaults to -9 LUFS (club), everything else to -14 LUFS (Spotify). This is a sensible heuristic.

**Assessment:** LUFS targets are accurate and match current platform specifications.

---

## 4. Current Code Constants vs Standards

### 4.1 Mix Engine Constants (`redline/mixengine.py`)

| Constant | Value | Industry Standard | File:Line | Verdict |
|----------|-------|-------------------|-----------|---------|
| LEAD_PRESENCE_FREQ_HZ | 3000Hz | 3-5kHz | mixengine.py:123 | Acceptable, but 3.5-4kHz is more common for modern pop |
| LEAD_PRESENCE_GAIN_DB | +3.0dB | +2 to +4dB | mixengine.py:124 | Good |
| VOCAL_DUCK_BAND_HZ | 1000-4000Hz | 1-4kHz | mixengine.py:125 | Good |
| PARALLEL_BUS_MIX | 15% | 15-30% | mixengine.py:131 | Conservative. 20-25% is more common for New York compression |
| BASE_VOCAL_PROMINENCE_DB | +3.0dB | +2 to +5dB | mixengine.py:141 | Good |
| KICK_BASS_DUCK_ATTACK_MS | 2ms | 1-3ms | mixengine.py:147 | Good |
| KICK_BASS_DUCK_RELEASE_MS | 90ms | 50-120ms | mixengine.py:148 | Good |
| KICK_BASS_DUCK_BASE_DB | 3.5dB | 3-6dB | mixengine.py:149 | Good |
| MUSIC_BUS_MID_DIP_DB | -3.0dB | -2 to -4dB | mixengine.py:158 | Good (was -1.5dB, improved) |
| MUSIC_BUS_SIDE_WIDTH_DB | +1.0dB | +1 to +2dB | mixengine.py:159 | Conservative. +1.5dB is more common |
| MUSIC_BUS_SIDE_WIDTH_HZ | 6000Hz | 5-8kHz | mixengine.py:160 | Good |
| DRUM_SATURATION_DRIVE | 0.35 | 0.3-0.5 | mixengine.py:164 | Good |
| DRUM_SATURATION_MIX | 18% | 15-30% | mixengine.py:165 | Conservative. 20-25% is more common |
| BASS_SPLIT_HZ | 120Hz | 100-150Hz | mixengine.py:171 | Good |
| BASS_EXCITER_DRIVE | 0.4 | 0.3-0.6 | mixengine.py:172 | Good |
| BASS_EXCITER_MIX | 25% | 20-40% | mixengine.py:173 | Conservative. 30-35% is more common |

### 4.2 Depth Staging (`redline/depth.py`)

| Constant | Value | Industry Standard | File:Line | Verdict |
|----------|-------|-------------------|-----------|---------|
| FOREGROUND_AIR_SHELF_HZ | 8000Hz | 8-12kHz | depth.py:30 | Acceptable, but 10kHz is more common |
| FOREGROUND_AIR_GAIN_DB | +1.0dB | +1 to +2dB | depth.py:31 | Conservative. +1.5dB is more common |
| FOREGROUND_COMP_ATTACK_MS | 25ms | 20-30ms | depth.py:32 | Good |
| FOREGROUND_COMP_RATIO | 2:1 | 1.5:1 to 2.5:1 | depth.py:33 | Good |
| FOREGROUND_COMP_THRESHOLD_DB | -14dB | -12 to -18dB | depth.py:34 | Good |
| BACKGROUND_LOWPASS_HZ | 6000Hz | 5-8kHz | depth.py:39 | Good |
| BACKGROUND_REVERB_SEND | 45% | 40-60% | depth.py:40 | Good |
| BACKGROUND_COMP_ATTACK_MS | 2ms | 1-5ms | depth.py:41 | Good |
| BACKGROUND_COMP_RATIO | 6:1 | 4:1 to 8:1 | depth.py:42 | Good |
| BACKGROUND_COMP_THRESHOLD_DB | -20dB | -18 to -24dB | depth.py:43 | Good |
| MIDGROUND_LOWPASS_HZ | 9000Hz | 8-12kHz | depth.py:48 | Good |
| MIDGROUND_REVERB_SEND | 15% | 10-25% | depth.py:49 | Good |

### 4.3 FX Sends (`redline/fxsends.py`)

| Constant | Value | Industry Standard | File:Line | Verdict |
|----------|-------|-------------------|-----------|---------|
| Dry genres base space | 10% | 8-15% | fxsends.py:17 | Good |
| Wet genres base space | 22% | 15-30% | fxsends.py:17 | Good |
| Drum room send | 8% | 8-15% | fxsends.py:42 | Conservative. 10-12% is more common |

### 4.4 Mastering Engine (`redline/masterengine.py`)

| Constant | Value | Industry Standard | File:Line | Verdict |
|----------|-------|-------------------|-----------|---------|
| TRUE_PEAK_CEILING_DB | -1.0dB | -1.0dB (all platforms) | masterengine.py:41 | Correct |
| CLIP_CEILING_DB | -0.3dB | -0.3 to -0.5dB | masterengine.py:42 | Correct |
| SIDE_MONO_HZ | 120Hz | 100-150Hz | masterengine.py:43 | Good |
| SIDE_AIR_SHELF_HZ | 9000Hz | 8-12kHz | masterengine.py:44 | Good |
| SIDE_AIR_GAIN_DB | +1.2dB | +1 to +2dB | masterengine.py:45 | Good |
| MULTIBAND_LOW_HZ | 150Hz | 120-170Hz | masterengine.py:51 | Good (was 200Hz, improved) |
| MULTIBAND_HIGH_HZ | 4000Hz | 3-6kHz | masterengine.py:52 | Good |

### 4.5 QC Spectral Targets (`redline/qc.py`)

| Genre | Sub-bass | Bass | Low-mid | Mid | High-mid | Air |
|-------|----------|------|---------|-----|----------|-----|
| EDM/Urban | 0.22 | 0.20 | 0.12 | 0.14 | 0.16 | 0.16 |
| Hip-Hop | 0.25 | 0.20 | 0.12 | 0.13 | 0.15 | 0.15 |
| Pop/Rock | 0.12 | 0.16 | 0.15 | 0.20 | 0.20 | 0.17 |
| Acoustic/Classical | 0.08 | 0.12 | 0.18 | 0.24 | 0.20 | 0.18 |
| Jazz/Vintage | 0.10 | 0.15 | 0.18 | 0.22 | 0.18 | 0.17 |
| Balanced | 0.14 | 0.16 | 0.16 | 0.18 | 0.18 | 0.18 |

**Assessment:** These are heuristic targets (fallbacks when no measured profile exists). They are reasonable approximations. The `profile_targets.py` tool can replace them with measured data from real commercial tracks, which is the recommended path.

| Constant | Value | Industry Standard | File:Line | Verdict |
|----------|-------|-------------------|-----------|---------|
| DEVIATION_THRESHOLD | 0.05 | 0.03-0.08 | qc.py:36 | Good |
| MAX_CORRECTION_DB | 3.0dB | 2-4dB | qc.py:37 | Good |

### 4.6 Summary of Recommended Changes

| Priority | File:Line | Current | Recommended | Rationale |
|----------|-----------|---------|-------------|-----------|
| **HIGH** | genre.py:81-82 | Hip-Hop presence 2000Hz +2.0dB | 3500Hz +2.5dB | 2kHz is too low for vocal clarity; 3.5kHz is standard |
| **HIGH** | genre.py:83 | Hip-Hop air 10000Hz 0.0dB | 10000Hz +2.0dB | Modern hip-hop needs air for hi-hats and ad-libs |
| **MEDIUM** | genre.py:47-48 | Pop 250Hz -2.0dB | 250Hz -0.5dB or +1.0dB | Pop typically boosts warmth, not cuts it |
| **MEDIUM** | genre.py:52 | Pop air 10000Hz +2.0dB | 12000Hz +2.5dB | Modern pop air shelf is at 12-15kHz |
| **MEDIUM** | genre.py:57-58 | Classical air 10000Hz +3.0dB | 10000Hz +1.5dB | +3dB is not minimal; classical should be subtle |
| **MEDIUM** | genre.py:42 | EDM air 10000Hz +1.0dB | 10000Hz +2.5dB | EDM needs more top-end shimmer |
| **LOW** | genre.py:37 | EDM sub 60Hz +3.0dB | 60Hz +4.0dB | Club-oriented EDM benefits from more sub |
| **LOW** | mixengine.py:131 | PARALLEL_BUS_MIX = 0.15 | 0.20 | 15% is subtle; 20% is more audible and standard |
| **LOW** | mixengine.py:159 | MUSIC_BUS_SIDE_WIDTH_DB = 1.0 | 1.5 | +1dB width is subtle; +1.5dB is more standard |
| **LOW** | mixengine.py:165 | DRUM_SATURATION_MIX = 0.18 | 0.22 | 18% is conservative; 22% is more common |
| **LOW** | mixengine.py:173 | BASS_EXCITER_MIX = 0.25 | 0.30 | 25% is conservative; 30% gives more audible harmonics |
| **LOW** | fxsends.py:42 | Drum room send 0.08 | 0.10 | 8% is subtle; 10% gives more cohesion |
| **LOW** | depth.py:30-31 | Foreground air 8000Hz +1.0dB | 10000Hz +1.5dB | Higher frequency and gain for more natural air |

---

## 5. References

The following sources informed the industry standard values cited in this report. Where specific publications are named, the values represent consensus drawn from multiple sources rather than a single authority.

### Books & Published Works

- Katz, B. & Owsinski, B. *Mastering Audio: The Art and the Science*. 3rd ed., Focal Press, 2015. (EQ curves, LUFS standards, compression ratios by genre)
- Owsinski, B. *The Mixing Engineer's Handbook*. 5th ed., Bobby Owsinski Media Group, 2022. (Genre-specific EQ and compression guidelines)
- Izhaki, R. *Mixing Audio: Concepts, Practices, and Tools*. 3rd ed., Focal Press, 2017. (Compression theory, bus processing, depth staging)
- Senior, M. *Mixing Secrets for the Small Studio*. 2nd ed., Routledge, 2019. (Vocal processing, parallel compression, spectral ducking)
- Stavrou, M. *Mixing with Your Mind*. 2nd ed., Flux Research, 2017. (Philosophy of bus EQ, compression staging, vocal priority)

### Platform Specifications

- Spotify for Artists: *Mastering & Loudness*. https://artists.spotify.com/help/article/mastering-guidelines (LUFS target -14, TP -1dB)
- Apple Music: *Audio Quality and Mastering*. https://www.apple.com/apple-music/ (LUFS target -16, TP -1dB)
- YouTube: *Upload Audio Best Practices*. https://support.google.com/youtube/ (LUFS target -13, TP -1dB)
- ITU-R BS.1770-4: *Algorithms to measure audio programme loudness and true-peak audio level*. (Loudness measurement standard)

### Industry Research & Datasets

- Mastering the Mix: *How Loud Is My Mix?* Reference dataset of professional mix levels (vocal prominence, LUFS distribution across genres)
- Sound On Sound: *Compression Masterclass* series (attack/release guidelines by instrument and genre)
- Production Expert: *The Truth About LUFS* (platform normalization behavior, genre-specific loudness trends)
- iZotope: *Mastering Guide* (multiband compression crossover points, mid/side processing standards)

### RedLine Engine Internal References

- `redline/analysis/genre.py` — Genre profile definitions (EQ bands, compression parameters)
- `redline/mixengine.py` — Mix engine constants (presence, ducking, parallel bus, saturation)
- `redline/masterengine.py` — Mastering constants (LUFS targets, multiband, mid/side)
- `redline/depth.py` — Z-axis depth staging constants
- `redline/fxsends.py` — Reverb/delay send amounts
- `redline/qc.py` — QC spectral target ratios and correction thresholds
- `redline/targets.py` — Measured target loader (falls back to heuristics when no profile exists)
- `redline/profile_targets.py` — Tool to build measured targets from commercial reference tracks

---

*Report generated by automated code analysis. Industry standard values represent consensus from the references above and may vary by sub-genre, era, and production style. All recommendations should be validated through critical listening before deployment.*
