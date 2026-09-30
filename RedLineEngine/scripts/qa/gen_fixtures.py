"""Deterministic event/step fixture generator for the RedLine QA harness.

Runs a REAL synthetic render (``render_mix`` + ``render_master``) with the
``on_step`` / ``on_event`` callbacks tapped, and writes every narration string
and structured event to ``tests/fixtures/events_full.jsonl`` -- one JSON object
per line, ``{"kind": "step"|"event", "payload": ...}``.

Why generate instead of hand-write: the frontend's ``onEvent`` switch
(app/web/app.js) is a contract with the engine. A hand-written fixture would
drift the moment the engine changes; this one is produced by the engine itself,
so ``tests/test_fixture_gen.py`` can regenerate it and compare bytes to catch a
silently dropped/renamed event type.

Determinism: the synthetic stems are the exact ones from
``tests/test_neutral_golden.py`` (``np.random.default_rng(7)``, 44100 Hz, 2.0 s)
plus a few extra deterministic stems that exercise the vocal-double / link-group
/ instrument paths. Records are canonically sorted and written with ``\\n``
newlines and ``sort_keys=True``, so the same bytes come out on every run and on
every platform. No timestamps, PIDs or absolute paths are emitted (any absolute
path is scrubbed to ``<PATH>``).

Usage::

    .venv\\Scripts\\python.exe scripts/qa/gen_fixtures.py
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from redline import config  # noqa: E402
from redline.analyze import analyze  # noqa: E402
from redline.masterengine import render_master  # noqa: E402
from redline.mixengine import render_mix  # noqa: E402
from redline.wizard import MixPreferences  # noqa: E402

FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "events_full.jsonl"

# Absolute Windows/POSIX paths that must never leak into a committed fixture.
_ABS_PATH_RE = re.compile(r"(?:[A-Za-z]:[\\/]|/)[^\s\"']+")


def _load_neutral_stems():
    """Import ``_stems`` from tests/test_neutral_golden.py by path.

    ``tests/`` is not a package, so a plain import won't resolve; loading the
    module by path reuses the exact helper (and its fixed seed) rather than
    duplicating the DSP-free stem construction.
    """
    path = REPO_ROOT / "tests" / "test_neutral_golden.py"
    spec = importlib.util.spec_from_file_location("_neutral_golden", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._stems


def _build_stems():
    """Neutral golden stems + deterministic extras that light up the
    vocal-double, link-group and instrument-classification event paths."""
    stems = _load_neutral_stems()()
    sr = stems.sample_rate
    n = stems.num_samples()
    seconds = n / sr
    t = np.linspace(0, seconds, n, endpoint=False)
    rng = np.random.default_rng(7)

    def st(mono: np.ndarray) -> np.ndarray:
        return np.stack([mono, mono], axis=1).astype(np.float32)

    # 880 Hz + noise vs the 440 Hz lead -> classified "falsetto", which is the
    # only register recipe with a non-zero reverb_send (drives reverb_send).
    stems.tracks["Vocals_Double_Falsetto"] = st(
        0.12 * np.sin(2 * np.pi * 880.0 * t) + 0.08 * rng.standard_normal(n)
    )
    stems.tracks["Synth_Pad"] = st(0.2 * np.sin(2 * np.pi * 220.0 * t))
    stems.tracks["Guitar"] = st(0.18 * np.sin(2 * np.pi * 330.0 * t))
    # Kick_In/Kick_Out share a link_id -> exercises the link_group event.
    stems.tracks["Kick_In"] = st(0.2 * rng.standard_normal(n))
    stems.tracks["Kick_Out"] = st(0.2 * rng.standard_normal(n))
    return stems


def _sanitizer():
    """app.api._sanitize_for_json coerces numpy scalars/arrays to native
    Python types. Imported lazily so the generator still works if the webview
    bridge can't be imported in a headless environment."""
    try:
        from app.api import _sanitize_for_json

        return _sanitize_for_json
    except Exception:
        return None


def _jsonable(payload, sanitize):
    """Force a payload through the sanitizer (if available) and a JSON
    round-trip, so every value is a plain JSON type."""
    if sanitize is not None:
        payload = sanitize(payload)
    return json.loads(json.dumps(payload, default=str))


def _scrub(obj):
    """Replace any absolute path with a placeholder -- keeps the fixture
    machine-independent."""
    if isinstance(obj, str):
        return _ABS_PATH_RE.sub("<PATH>", obj)
    if isinstance(obj, dict):
        return {k: _scrub(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_scrub(v) for v in obj]
    return obj


def generate_records() -> list[dict]:
    """Run the real render and return the canonically-sorted record list."""
    # Force the two flags that would otherwise make the run non-deterministic
    # (LLM advisory streams model tokens; live audition touches audio hardware).
    # Saved and restored so importing this module inside a pytest session can't
    # leak the override into unrelated tests.
    _flags = ("ENABLE_LLM_ADVISORY", "ENABLE_LIVE_AUDITION")
    _saved = {flag: config.is_enabled(flag) for flag in _flags}
    for flag in _flags:
        config.set_override(flag, False)

    try:
        sanitize = _sanitizer()
        stems = _build_stems()
        analysis = analyze(stems)

        steps: list[str] = []
        events: list[dict] = []
        prefs = MixPreferences(stereo_width=0.3, transient_attack=1.0, transient_sustain=0.5)

        mixed = render_mix(
            stems, analysis, prefs,
            on_step=steps.append, on_event=events.append,
        )
        render_master(
            mixed, stems.sample_rate, analysis, platform="auto",
            on_step=steps.append, on_event=events.append, prefs=prefs,
        )
    finally:
        for flag, value in _saved.items():
            config.set_override(flag, value)

    records: list[dict] = []
    for step in steps:
        records.append({"kind": "step", "payload": _scrub(_jsonable(str(step), sanitize))})
    for event in events:
        records.append({"kind": "event", "payload": _scrub(_jsonable(event, sanitize))})

    # Canonical order: the engine emits some events from a thread pool, so
    # wall-clock order varies run to run. Sorting by (kind, payload) makes the
    # byte output stable without losing any record.
    records.sort(key=lambda r: (r["kind"], json.dumps(r["payload"], sort_keys=True, ensure_ascii=False)))
    return records


def write_fixture(path: Path | str = FIXTURE_PATH) -> list[dict]:
    """Generate and write the fixture; returns the records written."""
    records = generate_records()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
    return records


def main() -> None:
    records = write_fixture()
    n_steps = sum(1 for r in records if r["kind"] == "step")
    n_events = sum(1 for r in records if r["kind"] == "event")
    counts = Counter(r["payload"]["type"] for r in records if r["kind"] == "event")

    print(f"Wrote {len(records)} records to {FIXTURE_PATH}")
    print(f"  steps:  {n_steps}")
    print(f"  events: {n_events}")
    print(f"Event type histogram ({len(counts)} distinct types):")
    for event_type, count in sorted(counts.items()):
        print(f"  {event_type}: {count}")


if __name__ == "__main__":
    main()
