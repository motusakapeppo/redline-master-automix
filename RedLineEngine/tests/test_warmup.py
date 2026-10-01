"""Contract tests for redline.warmup.warm().

The warm-up exists purely to hide one-time import/JIT latency at app
startup, so the contract under test is deliberately narrow: it must never
raise, must be safe to call repeatedly, and must be a no-op when
REDLINE_DISABLE_WARMUP=1.

The first test intentionally exercises the *real* heavy path once (imports
+ numba JIT); every later test resets the module's idempotency flag so it
still tests the code path it claims to, while the already-imported modules
and the numba on-disk cache keep those runs fast.
"""

import builtins
import importlib
import time

import pytest


def _fresh(warmup):
    """Reset the idempotency flag so the next warm() call actually runs."""
    warmup._WARMED = False


def test_warm_runs_without_raising():
    warmup = importlib.import_module("redline.warmup")
    _fresh(warmup)
    assert warmup.warm() is None


def test_warm_is_idempotent():
    warmup = importlib.import_module("redline.warmup")
    _fresh(warmup)

    assert warmup.warm() is None

    start = time.perf_counter()
    assert warmup.warm() is None
    # Second call must short-circuit, not redo the heavy work.
    assert time.perf_counter() - start < 0.5


def test_warm_disabled_by_env_var(monkeypatch):
    monkeypatch.setenv("REDLINE_DISABLE_WARMUP", "1")
    warmup = importlib.import_module("redline.warmup")
    _fresh(warmup)

    # A sentinel that would blow up if the disabled path touched the heavy
    # modules at all -- proves the env var short-circuits before any import.
    real_import = builtins.__import__

    def _exploding_import(name, *args, **kwargs):
        if name.split(".")[0] in {"librosa", "pedalboard", "pyloudnorm", "numba", "scipy"}:
            raise AssertionError(f"disabled warm-up imported {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _exploding_import)

    start = time.perf_counter()
    assert warmup.warm() is None
    assert time.perf_counter() - start < 1.0


def test_warm_swallows_exceptions(monkeypatch):
    """Even if the heavy work explodes, warm() must not propagate."""
    warmup = importlib.import_module("redline.warmup")
    _fresh(warmup)

    def _boom():
        raise RuntimeError("simulated JIT failure")

    monkeypatch.setattr(warmup, "_warm_impl", _boom)
    assert warmup.warm() is None
