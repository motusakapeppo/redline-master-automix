"""Feature flags: every experimental/new module is OFF by default and must
be explicitly enabled via a local `.flags.json` (gitignored — machine-local,
not a shared config) or environment variables. Golden rule: if a flag is
off, the engine behaves exactly like it did before that feature existed —
disabling a flag is a complete, instant rollback with no code revert needed.
"""

from __future__ import annotations

import json
import os

_FLAGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".flags.json")

DEFAULTS = {
    "ENABLE_LTAS_MATCHING": False,
    "ENABLE_RT60_CALIBRATION": False,
    "ENABLE_LLM_ADVISORY": False,
    "ENABLE_DIRECTOR_MODE": False,
    "ENABLE_BLUEPRINT_CHAINS": False,
}

_cache: dict | None = None


def _load() -> dict:
    global _cache
    if _cache is not None:
        return _cache

    flags = dict(DEFAULTS)
    if os.path.exists(_FLAGS_PATH):
        try:
            with open(_FLAGS_PATH, "r", encoding="utf-8") as f:
                on_disk = json.load(f)
            for key, value in on_disk.items():
                if key in flags:
                    flags[key] = bool(value)
        except Exception:
            pass  # malformed flags file -> fall back to all-off defaults, never crash on this

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


def reload() -> None:
    """Forces re-reading .flags.json — mainly for tests."""
    global _cache
    _cache = None
