"""Repeatable performance benchmark harness for the RedLine pipeline.

Times the three heavy stages -- ``analyze``, ``render_mix``, ``render_master``
-- on deterministic synthetic stems (fixed RNG seed, so the same audio is
produced on every run) and prints a readable table. This exists so a
before/after optimization claim is backed by measured numbers instead of a
stopwatch guess: run it on the current commit, run it again after a change,
compare the tables (or the ``--json`` output).

Usage::

    .venv\\Scripts\\python.exe scripts/qa/perf_bench.py --seconds 10
    .venv\\Scripts\\python.exe scripts/qa/perf_bench.py --seconds 20 --sr 44100 --json bench.json

No wall-clock thresholds are asserted anywhere (see tests/test_perf_bench.py):
absolute timings are machine-dependent and flaky; the harness only makes them
visible and comparable.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from redline import config  # noqa: E402
from redline.analyze import analyze  # noqa: E402
from redline.input_loader import Stems  # noqa: E402
from redline.masterengine import render_master  # noqa: E402
from redline.metrics import Metrics  # noqa: E402
from redline.mixengine import render_mix  # noqa: E402
from redline.wizard import MixPreferences  # noqa: E402

DEFAULT_SECONDS = 20.0
DEFAULT_SR = 44100
RNG_SEED = 7  # same seed as tests/test_neutral_golden.py -> same synthetic audio

STAGE_NAMES = ("analyze", "render_mix", "render_master")

# Flags that would make a benchmark run non-deterministic or touch hardware
# (LLM advisory streams model tokens; live audition opens audio devices).
# Forced off for the duration of the run and restored afterwards, exactly like
# scripts/qa/gen_fixtures.py does.
_NONDETERMINISTIC_FLAGS = ("ENABLE_LLM_ADVISORY", "ENABLE_LIVE_AUDITION")


def build_stems(seconds: float = DEFAULT_SECONDS, sr: int = DEFAULT_SR) -> Stems:
    """Deterministic synthetic 4-stem session (vocals/bass/drums/other).

    Same construction as tests/test_neutral_golden.py's ``_stems()`` (fixed
    seed 7), scaled to the requested duration/sample rate so the benchmark can
    be run at different sizes without changing the audio's character.
    """
    n = int(sr * seconds)
    t = np.linspace(0, seconds, n, endpoint=False)
    rng = np.random.default_rng(RNG_SEED)
    vocals = 0.2 * np.sin(2 * np.pi * 440.0 * t) + 0.05 * rng.standard_normal(n)
    bass = 0.3 * np.sin(2 * np.pi * 80.0 * t)
    drums = 0.15 * rng.standard_normal(n)
    other = 0.2 * np.sin(2 * np.pi * 220.0 * t)

    def st(mono: np.ndarray) -> np.ndarray:
        return np.stack([mono, mono], axis=1).astype(np.float32)

    return Stems(sample_rate=sr, tracks={
        "vocals": st(vocals), "bass": st(bass), "drums": st(drums), "other": st(other),
    })


def build_payload(metrics: Metrics, seconds: float, sample_rate: int) -> dict:
    """JSON-serializable benchmark result: per-stage seconds + total."""
    stages = {name: float(value) for name, value in metrics.as_dict().items()}
    return {
        "seconds": float(seconds),
        "sample_rate": int(sample_rate),
        "stages": stages,
        "total_seconds": float(metrics.total_seconds()),
    }


def format_table(payload: dict) -> str:
    """Human-readable table: one row per stage plus a total row."""
    lines = [
        f"Performance benchmark — {payload['seconds']:.1f}s @ {payload['sample_rate']} Hz",
        f"{'stage':<16}{'seconds':>10}",
        f"{'-' * 16}{'-' * 10}",
    ]
    for name, value in payload["stages"].items():
        lines.append(f"{name:<16}{value:>10.2f}")
    lines.append(f"{'-' * 16}{'-' * 10}")
    lines.append(f"{'total':<16}{payload['total_seconds']:>10.2f}")
    return "\n".join(lines)


def run_benchmark(seconds: float = DEFAULT_SECONDS, sr: int = DEFAULT_SR) -> dict:
    """Build the synthetic stems and time the three pipeline stages.

    Returns the same payload ``build_payload`` produces, so callers can print
    it, write it to JSON, or compare two runs programmatically.
    """
    saved = {flag: config.is_enabled(flag) for flag in _NONDETERMINISTIC_FLAGS}
    for flag in _NONDETERMINISTIC_FLAGS:
        config.set_override(flag, False)

    try:
        stems = build_stems(seconds=seconds, sr=sr)
        prefs = MixPreferences()
        metrics = Metrics()

        with metrics.stage("analyze"):
            analysis = analyze(stems)
        with metrics.stage("render_mix"):
            mixed = render_mix(stems, analysis, prefs)
        with metrics.stage("render_master"):
            render_master(mixed, sr, analysis, platform="auto", prefs=prefs)
    finally:
        for flag, value in saved.items():
            config.set_override(flag, value)

    return build_payload(metrics, seconds=seconds, sample_rate=sr)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Time analyze/render_mix/render_master on deterministic synthetic stems.",
    )
    parser.add_argument("--seconds", type=float, default=DEFAULT_SECONDS,
                        help=f"stem duration in seconds (default: {DEFAULT_SECONDS:g})")
    parser.add_argument("--sr", type=int, default=DEFAULT_SR,
                        help=f"sample rate in Hz (default: {DEFAULT_SR})")
    parser.add_argument("--json", type=Path, default=None,
                        help="also write the measured result as JSON to this path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    payload = run_benchmark(seconds=args.seconds, sr=args.sr)
    print(format_table(payload))
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        with open(args.json, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        print(f"\nJSON scritto in {args.json}")


if __name__ == "__main__":
    main()
