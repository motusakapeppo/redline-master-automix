"""Cooperative cancellation for the render pipeline (app/api.py).

``cancel_run()`` sets a threading.Event that the pipeline checks at cheap
stage boundaries (before load / analyze / mix / master). Native DSP calls are
NOT interrupted mid-flight -- the check only happens between stages -- so these
tests drive the boundary logic with fakes rather than real audio.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

pytest.importorskip("webview")  # app/api.py imports pywebview at module scope

import api as api_module  # noqa: E402
from api import Api  # noqa: E402


class _FakeStems:
    sample_rate = 44100

    def names(self):
        return ["vocals"]


class _StickyEvent:
    """Event double whose ``clear()`` is a no-op, so a pre-set cancel survives
    the start-of-run clear and is caught at the first boundary check. Lets us
    deterministically test the boundary logic without racing a real thread."""

    def __init__(self) -> None:
        self._set = True

    def set(self) -> None:
        self._set = True

    def clear(self) -> None:
        pass

    def is_set(self) -> bool:
        return self._set


@pytest.fixture()
def api():
    instance = Api()
    try:
        yield instance
    finally:
        instance._stop_js_worker()


def test_cancel_before_analyze_returns_cancelled(api, monkeypatch, tmp_path):
    """A cancel raised during the load stage must be caught at the next
    boundary (before analyze) and return the cancelled contract."""

    def _fake_load(*args, **kwargs):
        api._cancel_event.set()
        return _FakeStems()

    monkeypatch.setattr(api_module, "load_auto", _fake_load)

    result = api.run_pipeline("in.wav", {"aggressiveness": 3}, str(tmp_path / "out"))
    assert result == {"ok": False, "cancelled": True}


def test_run_pipeline_clears_stale_cancel_at_start(api, monkeypatch, tmp_path):
    """A cancel left over from a previous run must not abort a fresh run: the
    event is cleared at the start, so the first boundary passes."""
    api._cancel_event.set()

    def _fake_load(*args, **kwargs):
        assert api._cancel_event.is_set() is False, "event was not cleared at start"
        raise RuntimeError("stop-after-clear")

    monkeypatch.setattr(api_module, "load_auto", _fake_load)

    result = api.run_pipeline("in.wav", {"aggressiveness": 3}, str(tmp_path / "out"))
    assert result.get("cancelled") is not True
    assert result["ok"] is False
    assert "stop-after-clear" in result["error"]


def test_continue_to_mastering_cancelled_before_master(api):
    """With a valid cache and a sticky cancel, continue_to_mastering must stop
    at the before-master boundary instead of rendering."""
    api._last_mix = object()
    api._last_stems = _FakeStems()
    api._last_analysis = object()
    api._last_out_dir = "out"
    api._cancel_event = _StickyEvent()

    result = api.continue_to_mastering({"platform": "auto"})
    assert result == {"ok": False, "cancelled": True}


def test_reprocess_mix_cancelled_before_mix(api):
    """With a valid cache and a sticky cancel, reprocess_mix must stop at the
    before-mix boundary instead of rendering."""
    api._last_stems = _FakeStems()
    api._last_analysis = object()
    api._last_out_dir = "out"
    api._cancel_event = _StickyEvent()

    result = api.reprocess_mix({"aggressiveness": 3})
    assert result == {"ok": False, "cancelled": True}


def test_cancel_run_is_idempotent(api):
    assert api.cancel_run() == {"ok": True, "cancelling": True}
    assert api.cancel_run() == {"ok": True, "cancelling": True}
    assert api._cancel_event.is_set() is True
