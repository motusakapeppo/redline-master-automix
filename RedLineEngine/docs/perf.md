# RedLine Engine performance notes

This document records the performance work on the pipeline: what was sped up,
which changes are guaranteed bit-identical, which one is a flag-gated numerical
tier, the measured baseline, and how to reproduce the numbers yourself.

The guiding rule is the same one the rest of the engine follows: **a speed
change must not change the audio unless it is explicitly behind a flag that
says so.** Anything that alters output is opt-in and off by default.

## 1. Two tiers of speedup

There are two distinct kinds of change, and they must not be confused:

1. **Bit-identical speedups.** Same input, same output, byte for byte. These
   are always on and need no flag. They are verified by the existing golden and
   equivalence tests.
2. **Flag-gated numerical tier.** A cheaper algorithm that trades a small,
   bounded numerical difference for speed. It is off by default; turning it on
   is a deliberate choice, and with it off the render is bit-identical to
   before the feature existed.

## 2. Bit-identical speedups

These are always active. With every feature flag off, the render is
bit-identical to the render before these changes existed (enforced by
`tests/test_neutral_golden.py`).

- **Meter cache** (`redline/analysis/loudness.py`). `spectral_band_energies()`
  accepts an optional `cache` dict and memoizes results under a key combining
  sample rate and a content hash of the signal. The same buffer measured twice
  is measured once. `cache=None` (the default) computes exactly as before, so
  callers that don't opt in are unaffected.

- **Vectorized correlometer** (`redline/correlometer.py`). The sub-bass L/R
  phase search evaluates one float64 dot product per candidate lag. That search
  now runs as a JIT-compiled parallel kernel (`_best_lag_kernel`): the lags are
  independent, so they run in parallel, and the argmax is re-scanned
  sequentially in lag order so tie-breaking is unchanged. Every lag's score is
  the same float64 dot product as the original loop, so the result is
  bit-identical. Verified by `tests/test_correlometer_equiv.py`.

- **Background warm-up** (`redline/warmup.py`, called from `app/main.py`). The
  heavy third-party imports (librosa, scipy.signal, pedalboard, pyloudnorm) and
  the one-time numba JIT compile of the envelope-follower recursion are paid in
  a background thread while the UI is still coming up, instead of on the first
  render where they look like a hang. This is pure latency hiding: it never
  touches engine state, never raises, and never changes render output. It is
  idempotent and can be disabled entirely with `REDLINE_DISABLE_WARMUP=1`.

- **GUI stage timings** (`app/api.py`, `run_pipeline`). Each of the four stages
  (`load_auto`, `analyze`, `render_mix`, `mastering`) is wrapped in
  `Metrics.stage`, narrates a `[METRIC] <stage>: <s>s` line, and the returned
  result carries a JSON-safe `timings` dict (`{stage: seconds}` plus `total`).
  Pure instrumentation: no audio or render behavior changes, and no existing
  returned field changes. Covered by `tests/test_api_metrics.py`.

## 3. The flag-gated numerical tier

- **`ENABLE_FAST_ANALYSIS`** (`redline/analysis/pitch.py`,
  `redline/analysis/bpm.py`). Uses a cheaper plain-YIN pitch path on a shorter
  window instead of pYIN, and a cheaper BPM path. This is the one speed flag
  that is **not** bit-identical: it trades a small musical tolerance for speed.
  With the flag off (default), the analysis is bit-identical to before.

Everything else in the speed/quality wave is either bit-identical when off or
purely presentational. The full flag list lives in `redline/config.py` and is
documented in the root `README.md`.

## 4. Measured baseline

Measured on a deterministic synthetic 10s / 4-stem session (vocals, bass,
drums, other) with **all flags off**:

| Stage | Seconds |
|---|---|
| `analyze` | ~2.7 |
| `render_mix` | ~2.9 |
| `render_master` | ~0.9 |
| **total** | **~6.5** |

Absolute timings are machine-dependent. Treat these as a reference point for
the same machine, not as a cross-machine guarantee. The point of the harness is
comparability: run it on the current commit, run it again after a change, and
compare the tables (or the `--json` output).

## 5. Running the benchmark

`scripts/qa/perf_bench.py` times the three heavy stages on deterministic
synthetic stems (fixed RNG seed 7, the same construction as
`tests/test_neutral_golden.py`, so the same audio is produced on every run) and
prints a readable table.

```bash
# Default: 20s of audio at 44100 Hz
python scripts/qa/perf_bench.py

# The documented baseline size
python scripts/qa/perf_bench.py --seconds 10

# Custom size, and also write the result as JSON
python scripts/qa/perf_bench.py --seconds 20 --sr 44100 --json bench.json
```

On Windows with the repo venv:

```powershell
.venv\Scripts\python.exe scripts/qa/perf_bench.py --seconds 10
```

### Flags

| Flag | Default | Meaning |
|---|---|---|
| `--seconds` | `20` | Stem duration in seconds. |
| `--sr` | `44100` | Sample rate in Hz. |
| `--json` | none | Also write the measured result as JSON to this path. |

### What it does

The harness builds the synthetic stems, then times exactly three stages with
`Metrics.stage`: `analyze`, `render_mix`, `render_master`. Two flags that would
make a run non-deterministic or touch hardware (`ENABLE_LLM_ADVISORY`,
`ENABLE_LIVE_AUDITION`) are forced off for the duration of the run and restored
afterwards, exactly like `scripts/qa/gen_fixtures.py` does.

### Output

Human-readable table:

```
Performance benchmark — 10.0s @ 44100 Hz
stage              seconds
----------------  ----------
analyze                 2.70
render_mix              2.90
render_master           0.90
----------------  ----------
total                   6.50
```

With `--json`, the same data is written as:

```json
{
  "seconds": 10.0,
  "sample_rate": 44100,
  "stages": {"analyze": 2.7, "render_mix": 2.9, "render_master": 0.9},
  "total_seconds": 6.5
}
```

## 6. What is deliberately not asserted

No wall-clock threshold is asserted anywhere. Absolute timings are inherently
flaky on shared or CI machines, so `tests/test_perf_bench.py` pins only the
harness's contract: importability, the CLI arguments, and the JSON schema
(stages present, values non-negative floats, `total_seconds` equal to the sum
of the stages). The harness makes timings visible and comparable; it does not
gate on them.
