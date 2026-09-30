"""Feature flags: every experimental/new module is OFF by default and must
be explicitly enabled via a local `.flags.json` (gitignored — machine-local,
not a shared config) or environment variables. Golden rule: if a flag is
off, the engine behaves exactly like it did before that feature existed —
disabling a flag is a complete, instant rollback with no code revert needed.
"""

from __future__ import annotations

import json
import os

from redline.logging_setup import get_logger, setup_logging

logger = get_logger(__name__)

_FLAGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".flags.json")

DEFAULTS = {
    "ENABLE_LTAS_MATCHING": False,
    "ENABLE_RT60_CALIBRATION": False,
    "ENABLE_LLM_ADVISORY": False,
    "ENABLE_BLUEPRINT_CHAINS": False,
    "ENABLE_LIVE_AUDITION": False,
    "ENABLE_STEREO_WIDENING": False,
    "ENABLE_TRANSIENT_SHAPER": False,
    "ENABLE_FEEDBACK_DELAY": False,
    "ENABLE_BUS_EXPORT": False,
    # Wave 2 / Track F: optional plugin hosting + built-in character
    # processors. Both OFF by default -- with them off the render is
    # bit-identical to before these features existed. Plugin hosting is
    # user-supplied only and fail-safe (see redline/plugins.py).
    "ENABLE_PLUGIN_HOSTING": False,
    "ENABLE_BUILTIN_PROCESSOR_VARIANTS": False,
}

# Logging configuration (not feature flags — always available)
LOG_LEVEL = "WARNING"
LOG_DIR: str | None = None  # set to a path to enable file logging

_cache: dict | None = None


def _load() -> dict:
    global _cache
    if _cache is not None:
        return _cache

    setup_logging(log_dir=LOG_DIR, level=LOG_LEVEL)

    flags = dict(DEFAULTS)
    if os.path.exists(_FLAGS_PATH):
        try:
            with open(_FLAGS_PATH, "r", encoding="utf-8") as f:
                on_disk = json.load(f)
            for key, value in on_disk.items():
                if key in flags:
                    flags[key] = bool(value)
        except Exception:
            logger.warning("Malformed .flags.json — falling back to all-off defaults", exc_info=True)

    # Environment variables override the file, for quick one-off testing:
    # REDLINE_ENABLE_LTAS_MATCHING=1 python -m redline.cli ...
    for key in flags:
        env_val = os.environ.get(f"REDLINE_{key}")
        if env_val is not None:
            flags[key] = env_val.strip().lower() in ("1", "true", "yes", "on")

    _cache = flags
    return flags


def is_enabled(flag: str) -> bool:
    return _load().get(flag, False)


def set_override(flag: str, value: bool) -> None:
    """Runtime toggle for flags a user can flip from the GUI mid-session
    (e.g. the Neural Monitor A/B switch) without touching .flags.json or
    restarting the app. Only affects the in-memory cache for this process."""
    flags = _load()
    if flag in flags:
        flags[flag] = bool(value)


def reload() -> None:
    """Forces re-reading .flags.json — mainly for tests."""
    global _cache
    _cache = None
