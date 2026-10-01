"""Guard for the repeatable performance benchmark harness.

``scripts/qa/perf_bench.py`` exists so before/after timing of the three heavy
pipeline stages (analyze / render_mix / render_master) is measurable and
documented instead of guessed at. These tests pin the harness's contract --
importability, CLI arguments and the JSON schema -- WITHOUT asserting any
wall-clock threshold: absolute timings are inherently flaky on shared/CI
machines, so only the shape of the output is pinned here.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "qa" / "perf_bench.py"

EXPECTED_STAGES = ("analyze", "render_mix", "render_master")


def _load_script():
    """Import scripts/qa/perf_bench.py by path (scripts/ is not a package)."""
    if not SCRIPT_PATH.exists():
        pytest.fail(f"perf bench script missing: {SCRIPT_PATH}")
    spec = importlib.util.spec_from_file_location("perf_bench", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_script_imports_and_exposes_entry_points():
    module = _load_script()
    for attr in ("build_stems", "run_benchmark", "build_payload", "format_table", "main"):
        assert callable(getattr(module, attr, None)), f"perf_bench.{attr} missing or not callable"


def test_payload_schema_has_stages_and_total():
    module = _load_script()
    from redline.metrics import Metrics

    metrics = Metrics()
    with metrics.stage("analyze"):
        pass
    with metrics.stage("render_mix"):
        pass
    with metrics.stage("render_master"):
        pass

    payload = module.build_payload(metrics, seconds=10.0, sample_rate=44100)
    # Must survive a JSON round-trip -- it is written to disk with --json.
    payload = json.loads(json.dumps(payload))

    assert set(payload) >= {"seconds", "sample_rate", "stages", "total_seconds"}
    assert set(payload["stages"]) == set(EXPECTED_STAGES)
    for name, value in payload["stages"].items():
        assert isinstance(value, float) and value >= 0.0, (name, value)
    assert isinstance(payload["total_seconds"], float) and payload["total_seconds"] >= 0.0
    assert payload["total_seconds"] == pytest.approx(sum(payload["stages"].values()))


def test_format_table_renders_stage_rows_and_total():
    module = _load_script()
    from redline.metrics import Metrics

    metrics = Metrics()
    with metrics.stage("analyze"):
        pass

    table = module.format_table(module.build_payload(metrics, seconds=10.0, sample_rate=44100))
    assert "analyze" in table
    assert "total" in table.lower()


def test_cli_accepts_seconds_sr_and_json():
    module = _load_script()
    args = module._parse_args(["--seconds", "5", "--sr", "22050", "--json", "out.json"])
    assert args.seconds == 5.0
    assert args.sr == 22050
    assert str(args.json) == "out.json"
