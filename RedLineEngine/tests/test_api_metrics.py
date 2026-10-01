"""Per-stage timing instrumentation for the GUI pipeline (app/api.py).

Mirrors redline/cli.py: ``run_pipeline`` wraps its four stages (load_auto,
analyze, render_mix, mastering) in ``Metrics.stage``, narrates a
``[METRIC] <stage>: <s>s`` line per stage, and returns a JSON-safe
``"timings"`` dict (``{stage: seconds}`` + ``"total"``). Pure
instrumentation -- no audio/render behaviour changes, no existing returned
field changes.
"""

from __future__ import annotations

import json
import os
import sys
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

pytest.importorskip("webview")  # app/api.py imports pywebview at module scope

import api as api_module  # noqa: E402
from api import Api, _sanitize_for_json  # noqa: E402

_STAGE_NAMES = ("load_auto", "analyze", "render_mix", "mastering")


class _FakeStems:
    sample_rate = 44100

    def __init__(self) -> None:
        self.tracks = {"vocals": np.zeros((64, 2), dtype=np.float32)}

    def names(self):
        return list(self.tracks)


def _fake_analysis():
    return SimpleNamespace(
        bpm=120.0,
        key_name="A minor",
        genre=SimpleNamespace(name="Pop"),
        mix_lufs=-14.0,
        mix_crest=8.0,
    )


@pytest.fixture()
def api():
    instance = Api()
    try:
        yield instance
    finally:
        instance._stop_js_worker()


@pytest.fixture()
def wired(api, monkeypatch):
    """Stub the four engine entry points + history write, capture narration."""
    stems = _FakeStems()
    analysis = _fake_analysis()
    messages: list[str] = []

    monkeypatch.setattr(api_module, "load_auto", lambda *a, **k: stems)
    monkeypatch.setattr(api_module, "analyze", lambda *a, **k: analysis)
    monkeypatch.setattr(api_module, "render_mix", lambda *a, **k: np.zeros((64, 2), dtype=np.float32))
    monkeypatch.setattr(api_module, "render_master", lambda *a, **k: np.zeros((64, 2), dtype=np.float32))
    monkeypatch.setattr(api_module.SessionHistory, "add", lambda record: record)
    monkeypatch.setattr(api, "_narrate", messages.append)
    return api, messages


def test_run_pipeline_returns_json_safe_timings_for_all_four_stages(wired, tmp_path):
    api, messages = wired
    result = api.run_pipeline("in.wav", {"aggressiveness": 3}, str(tmp_path / "out"))

    assert result["ok"] is True
    assert result["stage"] == "master"

    timings = result["timings"]
    assert set(timings) == set(_STAGE_NAMES) | {"total"}
    for name, seconds in timings.items():
        assert isinstance(seconds, float), f"{name} is {type(seconds).__name__}, not float"
        assert seconds >= 0.0, f"{name} is negative: {seconds}"
    assert timings["total"] >= max(timings[name] for name in _STAGE_NAMES)

    json.dumps(result)  # must not raise
    json.dumps(_sanitize_for_json(result))  # the webview bridge path must not raise either

    for name in _STAGE_NAMES:
        assert any(f"[METRIC] {name}:" in m for m in messages), f"missing [METRIC] narration for {name}"


def test_run_pipeline_mix_only_timings_cover_executed_stages(wired, tmp_path):
    api, messages = wired
    result = api.run_pipeline(
        "in.wav", {"aggressiveness": 3, "stop_after_mix": True}, str(tmp_path / "out")
    )

    assert result["ok"] is True
    assert result["stage"] == "mix"

    timings = result["timings"]
    assert set(timings) == {"load_auto", "analyze", "render_mix", "total"}
    for seconds in timings.values():
        assert isinstance(seconds, float) and seconds >= 0.0
    json.dumps(result)

    for name in ("load_auto", "analyze", "render_mix"):
        assert any(f"[METRIC] {name}:" in m for m in messages), f"missing [METRIC] narration for {name}"


def test_run_pipeline_existing_fields_unchanged(wired, tmp_path):
    api, _ = wired
    result = api.run_pipeline("in.wav", {"aggressiveness": 3}, str(tmp_path / "out"))

    assert result["bpm"] == 120.0
    assert result["key"] == "A minor"
    assert result["genre"] == "Pop"
    assert result["lufs"] == -14.0
    assert result["mix_path"].endswith("mix.wav")
    assert result["master_path"].endswith("master.wav")
