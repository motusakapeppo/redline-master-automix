"""Timeout detection for pipeline steps. Watches wall-clock time spent in a
step and raises WatchdogTimeout when a step overruns a duration-proportional
budget, so a corrupted file or a runaway DSP call can't hang the pipeline
forever.

IMPORTANT LIMITATION: Python cannot reliably kill a thread that's blocked
inside a C call (numpy/scipy/pedalboard release the GIL and don't check for
pending exceptions until they return control to Python). WatchdogTimer makes
a best-effort attempt to interrupt the calling thread via an asynchronous
exception injection, but this only works reliably for pure-Python code that
periodically re-enters the interpreter loop (e.g. explicit sleeps, Python-level
loops). For a step blocked deep inside a C extension, the WatchdogTimeout may
only be raised once that call eventually returns — i.e. detection is
guaranteed, real interruption of already-running C code is not.
"""

from __future__ import annotations

import ctypes
import threading
from contextlib import contextmanager

from redline.logging_setup import get_logger

logger = get_logger(__name__)

_MIN_TIMEOUT_SEC = 5.0


class WatchdogTimeout(Exception):
    """Raised when a guarded step exceeds its time budget.

    Note: raising this exception does not guarantee the underlying work has
    actually stopped — see module docstring.
    """


def _async_raise(thread_ident: int, exc_type: type) -> None:
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_long(thread_ident), ctypes.py_object(exc_type)
    )
    if res > 1:
        # Broke the interpreter state — undo it.
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(thread_ident), None)


class WatchdogTimer:
    def __init__(self, timeout_multiplier: float = 5.0) -> None:
        self.timeout_multiplier = timeout_multiplier

    def _compute_timeout(self, audio_duration_sec: float) -> float:
        return max(self.timeout_multiplier * audio_duration_sec, _MIN_TIMEOUT_SEC)

    @contextmanager
    def guard(self, step_name: str, audio_duration_sec: float):
        timeout = self._compute_timeout(audio_duration_sec)
        caller_ident = threading.get_ident()
        fired = threading.Event()

        def _watch():
            if not fired.wait(timeout):
                logger.warning(
                    "Watchdog: '%s' ha superato il timeout (%.1fs), interruzione tentata",
                    step_name,
                    timeout,
                )
                _async_raise(caller_ident, WatchdogTimeout)

        timer_thread = threading.Thread(target=_watch, daemon=True)
        timer_thread.start()
        try:
            yield
        finally:
            fired.set()
            timer_thread.join(timeout=0.1)
