"""Additive web-surface tests for the live plugin/processor inspection API.

These pin the NEW public methods on ``app.api.Api`` (introspection + character
spec + plugin path + cancel) and, crucially, a *surface snapshot* asserting the
pre-existing public methods are still present -- so a future refactor cannot
silently drop one. Nothing here changes an existing signature.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

pytest.importorskip("webview")  # app/api.py imports pywebview at module scope

import api as api_module  # noqa: E402
from api import Api  # noqa: E402
from redline.processors import available_processors  # noqa: E402


# The public methods that existed BEFORE this additive change. If any of these
# disappears, the GUI breaks silently -- this snapshot is the tripwire.
_EXISTING_PUBLIC_METHODS = {
    "answer_instrument_questions",
    "approve_director_checkpoint",
    "continue_to_mastering",
    "delete_preset",
    "export_final",
    "get_preview_urls",
    "get_waveform_peaks",
    "list_presets",
    "list_sessions",
    "load_preset",
    "open_folder",
    "open_session_folder",
    "pick_input_file",
    "pick_input_path",
    "pick_output_dir",
    "redo_mix",
    "reprocess_mix",
    "run_pipeline",
    "save_preset",
    "submit_feedback",
    "system_ready",
    "toggle_neural_monitor",
    "undo_mix",
}

_NEW_PUBLIC_METHODS = {
    "list_builtin_processors",
    "probe_plugin",
    "get_character_spec",
    "set_character_spec",
    "get_plugin_path",
    "set_plugin_path",
    "cancel_run",
    "enable_processor_variants",
    "enable_plugin_hosting",
}


@pytest.fixture()
def api():
    instance = Api()
    try:
        yield instance
    finally:
        instance._stop_js_worker()


# ---------------------------------------------------------------------------
# Surface snapshot
# ---------------------------------------------------------------------------

def test_existing_public_methods_still_present():
    for name in _EXISTING_PUBLIC_METHODS:
        assert callable(getattr(Api, name, None)), f"missing existing public method: {name}"


def test_new_public_methods_present():
    for name in _NEW_PUBLIC_METHODS:
        assert callable(getattr(Api, name, None)), f"missing new public method: {name}"


def test_no_new_public_attributes_referencing_window(api):
    """State must live on underscore-private attributes only."""
    public_attrs = [n for n in vars(api) if not n.startswith("_")]
    # director_gate is the one pre-existing public attribute; nothing new.
    assert public_attrs == ["director_gate"], public_attrs


# ---------------------------------------------------------------------------
# list_builtin_processors
# ---------------------------------------------------------------------------

def test_list_builtin_processors_schema(api):
    result = api.list_builtin_processors()
    assert result["ok"] is True
    procs = result["processors"]
    assert isinstance(procs, list)
    assert {p["name"] for p in procs} == set(available_processors())
    for p in procs:
        assert isinstance(p["label"], str) and p["label"]
        assert isinstance(p["params"], list) and p["params"]


def test_list_builtin_processors_fail_safe(api, monkeypatch):
    def _boom():
        raise RuntimeError("registry exploded")

    monkeypatch.setattr(api_module, "available_processors", _boom)
    result = api.list_builtin_processors()
    assert result["ok"] is False
    assert "error" in result


# ---------------------------------------------------------------------------
# probe_plugin
# ---------------------------------------------------------------------------

def test_probe_plugin_empty_path_is_false(api):
    result = api.probe_plugin("")
    assert result["ok"] is False
    assert "error" in result


def test_probe_plugin_bad_path_is_false_and_never_raises(api):
    result = api.probe_plugin("Z:/definitely/not/a/plugin.vst3")
    assert result["ok"] is False
    assert "error" in result


def test_probe_plugin_never_raises_on_garbage(api):
    for bad in (None, 123, "Z:/nope.vst3"):
        result = api.probe_plugin(bad)  # type: ignore[arg-type]
        assert isinstance(result, dict)
        assert result["ok"] is False


# ---------------------------------------------------------------------------
# character spec
# ---------------------------------------------------------------------------

def test_character_spec_defaults_empty(api):
    result = api.get_character_spec()
    assert result == {"ok": True, "spec": {}}


def test_set_character_spec_accepts_known_processor(api):
    spec = {"vocals": {"processor": "distortion", "params": {"drive_db": 3.0}}}
    result = api.set_character_spec(spec)
    assert result["ok"] is True
    assert result["spec"]["vocals"]["processor"] == "distortion"
    assert result["spec"]["vocals"]["params"]["drive_db"] == 3.0
    assert api.get_character_spec()["spec"]["vocals"]["processor"] == "distortion"


def test_set_character_spec_rejects_unknown_processor(api):
    spec = {"vocals": {"processor": "not_a_processor", "params": {}}}
    result = api.set_character_spec(spec)
    assert result["ok"] is True
    assert result["spec"] == {}


def test_set_character_spec_clamps_numeric_params(api):
    spec = {"vocals": {"processor": "distortion", "params": {"drive_db": 9999.0}}}
    result = api.set_character_spec(spec)
    meta = {p["name"]: p for p in api.list_builtin_processors()["processors"]}
    max_drive = meta["distortion"]["params"][0]["max"]
    assert result["spec"]["vocals"]["params"]["drive_db"] == max_drive


def test_set_character_spec_ignores_unknown_stems_and_bad_entries(api):
    spec = {
        "vocals": {"processor": "chorus", "params": {}},
        "bogus": "not-a-dict",
        "other": {"processor": "nope", "params": {}},
    }
    result = api.set_character_spec(spec)
    assert result["ok"] is True
    assert set(result["spec"]) == {"vocals"}


def test_set_character_spec_non_dict_is_fail_safe(api):
    result = api.set_character_spec("not a dict")  # type: ignore[arg-type]
    assert result["ok"] is False
    assert "error" in result


# ---------------------------------------------------------------------------
# plugin path
# ---------------------------------------------------------------------------

def test_plugin_path_defaults_empty(api):
    assert api.get_plugin_path() == {"ok": True, "path": ""}


def test_set_plugin_path_round_trips(api):
    result = api.set_plugin_path("C:/plugins/foo.vst3")
    assert result["ok"] is True
    assert result["path"] == "C:/plugins/foo.vst3"
    assert api.get_plugin_path()["path"] == "C:/plugins/foo.vst3"


def test_set_plugin_path_non_str_normalizes_to_empty(api):
    result = api.set_plugin_path(123)  # type: ignore[arg-type]
    assert result["ok"] is True
    assert result["path"] == ""


# ---------------------------------------------------------------------------
# cancel_run
# ---------------------------------------------------------------------------

def test_cancel_run_sets_event(api):
    result = api.cancel_run()
    assert result == {"ok": True, "cancelling": True}
    assert api._cancel_event.is_set() is True


# ---------------------------------------------------------------------------
# enable_processor_variants / enable_plugin_hosting (runtime flag toggles)
# ---------------------------------------------------------------------------

def test_enable_processor_variants_toggles_flag(api):
    from redline import config

    original = config.is_enabled("ENABLE_BUILTIN_PROCESSOR_VARIANTS")
    try:
        assert api.enable_processor_variants(True) == {"ok": True, "enabled": True}
        assert config.is_enabled("ENABLE_BUILTIN_PROCESSOR_VARIANTS") is True
        assert api.enable_processor_variants(False) == {"ok": True, "enabled": False}
        assert config.is_enabled("ENABLE_BUILTIN_PROCESSOR_VARIANTS") is False
    finally:
        config.set_override("ENABLE_BUILTIN_PROCESSOR_VARIANTS", original)


def test_enable_plugin_hosting_toggles_flag(api):
    from redline import config

    original = config.is_enabled("ENABLE_PLUGIN_HOSTING")
    try:
        assert api.enable_plugin_hosting(True) == {"ok": True, "enabled": True}
        assert config.is_enabled("ENABLE_PLUGIN_HOSTING") is True
    finally:
        config.set_override("ENABLE_PLUGIN_HOSTING", original)


def test_enable_toggles_never_raise_on_garbage(api):
    # bool() coercion accepts anything; must never raise.
    assert api.enable_processor_variants("yes")["ok"] is True
    assert api.enable_plugin_hosting(None)["ok"] is True
