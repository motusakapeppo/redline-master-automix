"""Optional, fail-safe external plugin hosting (Wave 2 / Track F).

WHAT THIS IS
------------
A thin, defensive wrapper around ``pedalboard.load_plugin`` so the engine can
*optionally* host a user-supplied VST3/AU plugin. It is a seam, not a live
feature: nothing here is wired into the render path, and the whole capability
is gated behind the ``ENABLE_PLUGIN_HOSTING`` feature flag (OFF by default).

SAFETY / LICENSING FACTS (read before enabling)
-----------------------------------------------
  - USER-SUPPLIED ONLY. No third-party plugin binary is bundled with RedLine
    Engine. The user points the engine at a plugin they already own and have
    installed. RedLine ships zero plugins.
  - pedalboard itself is GPL-3.0. Hosting a plugin through it inherits that
    licensing constraint; distributing a build that hosts plugins has GPL
    implications the user must understand.
  - CRASH RISK: a hosted plugin can crash the Python interpreter with NO
    catchable exception (a segfault inside native plugin code cannot be
    caught by try/except). For any plugin you do not fully trust, run it in a
    separate subprocess so a crash takes down the child, not the render.
  - ``reset()`` on a non-main thread can raise; plugin calls are therefore
    kept off the render's worker threads.
  - Because of the above, hosting is OFF by default and every entry point
    here degrades to ``None``/``False`` instead of raising. A missing file, a
    malformed bundle, or any exception during load returns ``None`` -- it can
    never abort a render.

``pedalboard`` is imported lazily inside the functions (never at module
import time) so importing this module is free and cannot fail on a machine
without pedalboard.
"""

from __future__ import annotations

from typing import Any


def is_plugin_hosting_available() -> bool:
    """True if the installed pedalboard exposes ``load_plugin`` (i.e. this
    build can host external plugins at all). Never raises."""
    try:
        import pedalboard

        return callable(getattr(pedalboard, "load_plugin", None))
    except Exception:
        return False


def load_external_plugin(
    path: str,
    plugin_name: str | None = None,
    initialization_timeout: float = 10.0,
):
    """Load a user-supplied VST3/AU plugin, fail-safe.

    Returns the plugin object on success, or ``None`` on ANY failure
    (missing file, bad bundle, unsupported format, exception) -- this
    function NEVER raises, so a bad plugin path can never abort a render.

    NOTE: a plugin that crashes the interpreter natively (segfault) cannot be
    caught here; use subprocess isolation for untrusted plugins.
    """
    try:
        import os

        if not path or not os.path.exists(path):
            return None

        import pedalboard

        loader = getattr(pedalboard, "load_plugin", None)
        if not callable(loader):
            return None

        return loader(
            path,
            plugin_name=plugin_name,
            initialization_timeout=initialization_timeout,
        )
    except Exception:
        return None


def describe_plugin(plugin: Any) -> dict | None:
    """Best-effort introspection of a loaded plugin for a future GUI.

    Returns ``{"name": ..., "parameters": [{"name", "label", "raw_value"}]}``
    or ``None`` if the object exposes nothing usable. Never raises -- any
    attribute access that fails is simply skipped.
    """
    if plugin is None:
        return None
    try:
        name = getattr(plugin, "name", None)
        if name is None:
            name = type(plugin).__name__

        parameters: list[dict] = []
        raw_params = getattr(plugin, "parameters", None)
        if raw_params is not None:
            try:
                for param in raw_params.values():
                    parameters.append(
                        {
                            "name": getattr(param, "name", None),
                            "label": getattr(param, "label", None),
                            "raw_value": getattr(param, "raw_value", None),
                        }
                    )
            except Exception:
                # A plugin whose parameter collection misbehaves still yields
                # a usable name-only description rather than nothing.
                pass

        return {"name": name, "parameters": parameters}
    except Exception:
        return None
