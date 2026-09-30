"""Wave 2 / Track F: optional, fail-safe external plugin hosting.

The whole point of this module is that it can NEVER break a render: every
entry point must degrade to None/False instead of raising, and the feature
must be OFF by default behind ENABLE_PLUGIN_HOSTING. These tests pin that
contract down without ever loading a real (user-supplied) plugin binary.
"""

from __future__ import annotations

from redline import config
from redline.plugins import (
    load_external_plugin,
    is_plugin_hosting_available,
    describe_plugin,
)


def test_plugin_hosting_flag_defaults_off(monkeypatch, tmp_path):
    """ENABLE_PLUGIN_HOSTING must default to False (isolated from any local
    .flags.json a CI run may have written)."""
    monkeypatch.setattr(config, "_FLAGS_PATH", str(tmp_path / "nonexistent.flags.json"))
    config.reload()
    try:
        assert config.is_enabled("ENABLE_PLUGIN_HOSTING") is False
    finally:
        config.reload()


def test_load_missing_plugin_returns_none():
    """A nonexistent path must return None and must NOT raise."""
    assert load_external_plugin("Z:/nope.vst3") is None


def test_is_plugin_hosting_available():
    """Returns a bool; True on this machine because pedalboard exposes
    load_plugin (verified: pedalboard==0.9.23)."""
    available = is_plugin_hosting_available()
    assert isinstance(available, bool)
    assert available is True


def test_describe_plugin_never_raises_on_garbage():
    """describe_plugin must be best-effort: garbage in -> dict or None out,
    never an exception."""
    result = describe_plugin(object())
    assert result is None or isinstance(result, dict)
