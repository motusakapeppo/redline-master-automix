"""Latency tests for the async JS eval queue (app/api.py).

The DSP pipeline can fire dozens of onStep/onEvent calls per second during a
render. A queue.Queue + background thread decouples the pipeline from
pywebview's .NET/COM bridge, and the worker drops stale frames to keep the
UI responsive.

These tests verify:
1. _narrate / _emit enqueue JS strings (not call evaluate_js directly)
2. The worker drains the queue and calls evaluate_js
3. Rapid calls are collapsed (only the latest survives)
4. No window does not crash
5. Sentinels shut down the worker cleanly
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

from api import Api  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture: Api instance with a mock window that records every evaluate_js call
# ---------------------------------------------------------------------------

class _MockWindow:
    """Records every evaluate_js call for inspection."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def evaluate_js(self, js: str) -> None:
        self.calls.append(js)


def _make_api() -> tuple[Api, _MockWindow]:
    api = Api()
    w = _MockWindow()
    api._window = w
    return api, w


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_narrate_enqueues_not_calls_directly() -> None:
    """_narrate should put on the queue, not call evaluate_js directly."""
    api, w = _make_api()
    api._narrate("hello")
    # Should NOT be in window.calls yet (worker runs async)
    assert len(w.calls) == 0
    # But the queue should have an item
    assert api._js_queue.qsize() >= 1


def test_emit_enqueues_not_calls_directly() -> None:
    """_emit should put on the queue, not call evaluate_js directly."""
    api, w = _make_api()
    api._emit({"type": "compressor", "ratio": 4.0})
    assert len(w.calls) == 0
    assert api._js_queue.qsize() >= 1


def test_worker_drains_queue() -> None:
    """The background worker should eventually call evaluate_js."""
    api, w = _make_api()
    api._narrate("hello")
    # Give the worker a moment to drain
    time.sleep(0.1)
    assert len(w.calls) >= 1
    assert "onStep" in w.calls[0]
    assert "hello" in w.calls[0]


def test_worker_drains_emit() -> None:
    """The background worker should process _emit events."""
    api, w = _make_api()
    api._emit({"type": "eq", "freq": 3000})
    time.sleep(0.1)
    assert len(w.calls) >= 1
    assert "onEvent" in w.calls[0]
    assert "eq" in w.calls[0]


def test_rapid_calls_are_collapsed() -> None:
    """Rapid calls should be collapsed — only the latest survives."""
    api, w = _make_api()
    api._narrate("step1")
    api._narrate("step2")
    api._narrate("step3")
    time.sleep(0.1)
    # The worker collapses stale entries, so we should see at most 2 calls
    # (the first one, then the latest after draining stale)
    assert len(w.calls) <= 2
    # The last call should be step3
    assert "step3" in w.calls[-1]


def test_no_window_does_not_crash() -> None:
    """If window is None, the worker should be a no-op."""
    api = Api()
    api._window = None
    api._narrate("hello")  # must not raise
    time.sleep(0.1)
    # No crash = pass


def test_sentinel_shuts_down_worker() -> None:
    """Sending None should stop the worker thread."""
    api, w = _make_api()
    api._stop_js_worker()
    time.sleep(0.1)
    assert api._js_worker is None or not api._js_worker.is_alive()


def test_toggle_neural_monitor_does_not_block() -> None:
    """toggle_neural_monitor is a pure Python call (no evaluate_js),
    so it should never block on the queue."""
    api, _ = _make_api()
    api.toggle_neural_monitor(True)
    api.toggle_neural_monitor(False)
    # Must not raise or block


def test_approve_director_checkpoint_does_not_block() -> None:
    """approve_director_checkpoint is a pure Python call (no evaluate_js),
    so it should never be affected by the queue."""
    api, _ = _make_api()
    api.approve_director_checkpoint()
    api.approve_director_checkpoint()


# ---------------------------------------------------------------------------
# 60fps throttle tests (rate-limiting inside the worker drain loop)
# ---------------------------------------------------------------------------

def test_throttle_limits_evaluate_js_rate() -> None:
    """The worker should not call evaluate_js more than ~60 times per second.
    Sending 20 items rapidly should result in far fewer than 20 actual calls
    within a short window."""
    api, w = _make_api()
    for i in range(20):
        api._narrate(f"step{i}")
    time.sleep(0.1)
    # At 60fps throttle, at most ~6 calls in 100ms
    assert len(w.calls) <= 10, f"Expected ≤10 calls, got {len(w.calls)}"
    # The last call should be the most recent item
    assert "step19" in w.calls[-1]


def test_throttle_preserves_latest_frame() -> None:
    """Even with aggressive throttling, the latest frame always survives."""
    api, w = _make_api()
    for i in range(50):
        api._narrate(f"step{i}")
    time.sleep(0.2)
    # The last call should always be the most recent item
    assert "step49" in w.calls[-1]


def test_throttle_does_not_starve_steady_stream() -> None:
    """A steady stream at ~30fps should get through without dropping."""
    api, w = _make_api()
    for i in range(10):
        api._narrate(f"step{i}")
        time.sleep(0.02)  # ~50fps — slightly faster than throttle
    time.sleep(0.1)
    # Should have processed several calls (not just 1)
    assert len(w.calls) >= 3, f"Expected ≥3 calls, got {len(w.calls)}"
