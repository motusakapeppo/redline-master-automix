"""One-time startup warm-up: pay the heavy import and numba-JIT costs in a
background thread while the UI is still coming up, instead of on the first
render where they look like a hang.

Pure latency hiding -- this module must never touch engine state, never
raise, and never change render output. `warm()` is idempotent and can be
disabled entirely with REDLINE_DISABLE_WARMUP=1.
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

_WARMED = False


def _warm_impl() -> None:
    """The actual one-time work. Kept separate so tests can stub it."""
    # Heavy third-party imports: librosa drags in the numba/soundfile stack,
    # pedalboard loads its native extension, scipy.signal is used by every
    # band-split, pyloudnorm on every master render. Each is guarded
    # individually so one missing optional dependency can't skip the rest.
    try:
        import librosa  # noqa: F401
    except Exception:
        log.debug("warm-up: librosa import failed (ignored)", exc_info=True)
    try:
        import scipy.signal  # noqa: F401
    except Exception:
        log.debug("warm-up: scipy.signal import failed (ignored)", exc_info=True)
    try:
        import pedalboard  # noqa: F401
    except Exception:
        log.debug("warm-up: pedalboard import failed (ignored)", exc_info=True)
    try:
        import pyloudnorm  # noqa: F401
    except Exception:
        log.debug("warm-up: pyloudnorm import failed (ignored)", exc_info=True)

    # Trigger the numba-jitted recursion in dsp_utils once with a tiny array
    # so the ~5s one-time compile happens here rather than inside the first
    # real render. envelope_follower is the public entry point that calls
    # _attack_release_recursion (the @njit function).
    import numpy as np

    from redline.dsp_utils import envelope_follower

    envelope_follower(np.zeros(2048, dtype=np.float32), 44100, attack_ms=10.0, release_ms=100.0)


def warm() -> None:
    """Best-effort background warm-up. Idempotent, never raises, returns None."""
    global _WARMED

    if os.environ.get("REDLINE_DISABLE_WARMUP", "").strip() == "1":
        return
    if _WARMED:
        return
    _WARMED = True

    try:
        _warm_impl()
    except Exception:
        # Warm-up is an optimization only: any failure (missing optional
        # dependency, numba cache issue) must be invisible to the app.
        log.debug("warm-up failed (ignored)", exc_info=True)
