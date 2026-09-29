"""Regression test for silent event loss in the Python->JS bridge.

``Api._start_js_worker``'s inner ``_drain`` coalesces every pending JS call
into a single ``;``-joined ``evaluate_js`` string (one round trip per 60fps
frame instead of one per event). Before this fix, a single throwing call
aborted the rest of the joined script, and the outer ``except Exception:
pass`` swallowed the error -- so every later event in that batch was
silently lost (flat EQ curve, unlit stage badges, ...).

``_wrap_js_call`` guards each queued call in its own try/catch so one
failure can no longer take down its neighbours. These tests pin down that
transformation: item count is preserved and every item is individually
guarded.
"""

import os
import sys

import pytest

# app/api.py imports pywebview at module scope; skip cleanly if the test
# environment doesn't have it (it is installed in the project venv).
pytest.importorskip("webview")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

from api import _wrap_js_call  # noqa: E402


def test_valid_call_is_wrapped_and_preserves_original_code():
    js = 'onEvent({"type": "done"})'
    wrapped = _wrap_js_call(js)
    assert js in wrapped, "original call must survive wrapping verbatim"
    assert "try" in wrapped
    assert "catch" in wrapped


def test_joining_n_calls_yields_n_catch_guards():
    calls = [f"onStep('step {i}')" for i in range(5)]
    joined = ";\n".join(_wrap_js_call(c) for c in calls)
    # One guard per queued call -- no call is merged away or left unguarded.
    assert joined.count("catch") == len(calls)
    for call in calls:
        assert call in joined


def test_call_body_containing_semicolon_does_not_break_guard():
    js = "onStep('a; b'); onStep('c')"
    wrapped = _wrap_js_call(js)
    assert js in wrapped
    # The embedded ';' must not split the guard into two try/catch blocks.
    assert wrapped.count("catch") == 1
    assert wrapped.count("try") == 1
    assert wrapped.rstrip().endswith("}")
