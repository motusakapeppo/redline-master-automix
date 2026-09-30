"""QA harness guard for the deterministic event/step fixture.

The frontend's ``onEvent`` switch (app/web/app.js) is the contract between the
engine and the UI: every event type the engine emits must be one the UI knows
how to render. This test pins a *generated* fixture (not hand-written) of every
event type and representative narration the engine actually produces for a
fixed synthetic render, so a future engine change that silently drops or renames
an event type is caught here instead of only being noticed as a dead UI module.

The fixture is produced by ``scripts/qa/gen_fixtures.py``, which runs a real
``render_mix`` + ``render_master`` with the callbacks tapped. It is regenerated
inside the determinism test and compared byte-for-byte, so the committed file
can never silently drift from what the generator produces.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "events_full.jsonl"
GEN_PATH = REPO_ROOT / "scripts" / "qa" / "gen_fixtures.py"

# The minimum set of event types the fixture must exercise. Derived from the
# app/web/app.js onEvent switch -- these are the types whose UI modules would
# silently go dead if the engine stopped emitting them.
REQUIRED_EVENT_TYPES = {
    "bus_eq_band",
    "compressor",
    "deesser",
    "saturation",
    "reverb_send",
    "limiter",
    "mid_side",
    "multiband_compressor",
    "qc_report",
    "bus_compressor",
    "done",
}


def _load_generator():
    """Import scripts/qa/gen_fixtures.py by path (scripts/ is not a package)."""
    if not GEN_PATH.exists():
        pytest.fail(f"generator missing: {GEN_PATH}")
    spec = importlib.util.spec_from_file_location("gen_fixtures", GEN_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_records(path: Path) -> list[dict]:
    records: list[dict] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def test_fixture_file_exists_and_parses_line_by_line():
    assert FIXTURE_PATH.exists(), (
        f"fixture not generated: {FIXTURE_PATH} -- run "
        f"`.venv\\Scripts\\python.exe scripts/qa/gen_fixtures.py`"
    )
    records = _read_records(FIXTURE_PATH)
    assert records, "fixture is empty"
    for record in records:
        assert set(record) == {"kind", "payload"}, record
        assert record["kind"] in ("step", "event"), record
        # Every payload must be JSON-serializable (it already round-tripped
        # through json.loads above, but re-encode to prove no exotic types).
        json.dumps(record["payload"])


def test_fixture_covers_required_event_types():
    records = _read_records(FIXTURE_PATH)
    event_types = {r["payload"]["type"] for r in records if r["kind"] == "event"}
    missing = REQUIRED_EVENT_TYPES - event_types
    assert not missing, f"fixture is missing required event types: {sorted(missing)}"
    # Narration must be present too -- the fixture is not events-only.
    assert any(r["kind"] == "step" for r in records), "fixture has no on_step narration"


def test_fixture_is_deterministic(tmp_path):
    # The generator imports the engine (numpy/scipy/pedalboard/librosa...). If
    # the audio stack is genuinely unavailable, skip rather than fail -- the
    # repo's normal path always has it.
    pytest.importorskip("numpy")
    try:
        generator = _load_generator()
    except ImportError as exc:  # pragma: no cover - environment guard
        pytest.skip(f"audio dependencies unavailable: {exc}")

    regenerated = tmp_path / "events_full.jsonl"
    generator.write_fixture(regenerated)

    assert regenerated.read_bytes() == FIXTURE_PATH.read_bytes(), (
        "regenerated fixture differs from the committed one -- the engine's "
        "event stream changed; regenerate tests/fixtures/events_full.jsonl"
    )
