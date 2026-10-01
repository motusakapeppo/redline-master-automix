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
    # ------------------------------------------------------------------
    # Quality + intelligence + speed program (all OFF => bit-identical to
    # the render before these features existed; see tests/test_neutral_golden.py).
    # ------------------------------------------------------------------
    # Analysis / speed (flag-gated numerical tiers)
    "ENABLE_FAST_ANALYSIS": False,          # cheaper BPM/pitch path (musical tolerance, not bit-identical)
    "ENABLE_LLM_RESULT_CACHE": False,       # memoize LLM advisory classification across renders
    # Recognition: which stem / instrument / voice type is this
    "ENABLE_STEM_PROFILE": False,           # one shared per-stem feature pass
    "ENABLE_RECOGNITION_V2": False,         # expanded multilingual lexicon + confidence fusion
    "ENABLE_AUDIO_CLASSIFIER": False,       # audio-based instrument classifier (PANNs), optional model
    "ENABLE_VOCAL_ANALYSIS": False,         # singing-voice detection + absolute register
    # Musical knowledge / adaptivity
    "ENABLE_ADAPTIVE_TARGETS": False,       # measurement-scaled, confidence-weighted targets
    "ENABLE_DO_NO_HARM": False,             # crest-aware: bypass dynamics when already dense
    "ENABLE_TWO_STAGE_BALANCE": False,      # intra-group then inter-group balance
    "ENABLE_MULTI_RESONANCE": False,        # N-node content-driven corrective EQ
    "ENABLE_AUTO_PROCESSORS": False,        # auto-assign the RIGHT character processor per stem (role/instrument/register aware)
    # Mastering / QC
    "ENABLE_QC_V2": False,                  # true-peak ISP, LRA, DC offset, stereo correlation, tonal distance
    "ENABLE_LTAS_V2": False,                # loudest-pieces + LOWESS log-smooth + separate mid/side FIR
    "ENABLE_QC_REPORT_JSON": False,         # serialize the QC report to disk (explainable)
    # Per-stem character-processor presets (additive; OFF => nothing is ever
    # auto-inserted, render bit-identical)
    "ENABLE_PROCESSOR_PRESETS": False,      # curated per-instrument processor presets (data only)
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
