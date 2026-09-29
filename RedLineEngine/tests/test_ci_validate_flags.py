"""Tests for ci_validate._enable_all_flags().

The CI flag enabler must be:
  - complete: it enables every flag known to redline.config.DEFAULTS (derived,
    not a hardcoded subset), so new flags are never silently left inert;
  - non-destructive: keys already present in the machine-local .flags.json
    that are not part of DEFAULTS (e.g. ENABLE_DIRECTOR_MODE) are preserved
    with their current value instead of being clobbered.
"""

import importlib.util
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from redline import config


def _load_ci_validate():
    """ci_validate.py is a top-level script module in the repo root, not part
    of the redline package — load it by file path."""
    spec = importlib.util.spec_from_file_location(
        "ci_validate", os.path.join(REPO_ROOT, "ci_validate.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ci_validate = _load_ci_validate()


def test_enable_all_flags_writes_every_known_flag(monkeypatch, tmp_path):
    flags_path = tmp_path / ".flags.json"
    monkeypatch.setattr(ci_validate, "FLAGS_PATH", str(flags_path))

    ci_validate._enable_all_flags()

    written = json.loads(flags_path.read_text(encoding="utf-8"))
    assert set(written) == set(config.DEFAULTS)
    assert all(value is True for value in written.values())
    # The newer flags must be part of the surface, not just the original five.
    assert written["ENABLE_STEREO_WIDENING"] is True
    assert written["ENABLE_TRANSIENT_SHAPER"] is True


def test_enable_all_flags_preserves_unknown_user_keys(monkeypatch, tmp_path):
    flags_path = tmp_path / ".flags.json"
    flags_path.write_text(
        json.dumps({"ENABLE_DIRECTOR_MODE": False}), encoding="utf-8"
    )
    monkeypatch.setattr(ci_validate, "FLAGS_PATH", str(flags_path))

    ci_validate._enable_all_flags()

    written = json.loads(flags_path.read_text(encoding="utf-8"))
    # User setting survives the CI run untouched...
    assert "ENABLE_DIRECTOR_MODE" in written
    assert written["ENABLE_DIRECTOR_MODE"] is False
    # ...while every known flag is enabled.
    assert set(config.DEFAULTS) <= set(written)
    assert all(written[flag] is True for flag in config.DEFAULTS)
