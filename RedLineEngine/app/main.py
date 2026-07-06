"""Desktop app entry point: opens a pywebview window backed by the same
engine used by redline/cli.py — no CLI required for day-to-day use."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

# Allow `python app/main.py` to find the `redline` package that lives in the
# RedLineEngine root, one level up from this file, without a pip install step.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LOG_PATH = Path(os.environ["LOCALAPPDATA"]) / "RedLineEngine" / "startup_error.log"
LOAD_LOG_PATH = Path(os.environ["LOCALAPPDATA"]) / "RedLineEngine" / "last_load.log"


def _web_dir() -> Path:
    # PyInstaller (--add-data "web;web") extracts bundled data next to the
    # executable under sys._MEIPASS; in dev mode it's just alongside this file.
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "web"
    return Path(__file__).resolve().parent / "web"


def _run() -> None:
    import webview

    from api import Api
    api = Api()
    web_dir = _web_dir()
    # .as_uri() percent-encodes spaces etc. in the path — the project lives
    # under "D:\FASE REM_automix\..." (note the space), and passing the raw
    # Windows path straight to the webview control silently fails to load
    # the page (window opens but stays on the fallback background_color).
    index_uri = (web_dir / "index.html").as_uri()

    window = webview.create_window(
        "RedLine Engine",
        url=index_uri,
        js_api=api,
        width=880,
        height=680,
        min_size=(720, 560),
        background_color="#0A0A0A",
    )
    # Deliberately a private attribute (leading underscore): pywebview's own
    # js_api introspection (webview/util.py's inject_pywebview/get_functions)
    # walks every *public* attribute of the Api instance to build the JS
    # bridge, recursively descending into non-callable objects. `window` is
    # a pywebview Window wrapping the raw WinForms/.NET WebView2 control,
    # and walking into its `.native` COM object hits a genuine infinite
    # loop (window.native.AccessibilityObject.Bounds.Empty.Empty.Empty...)
    # once external UI Automation software (observed: NVIDIA Overlay, AVG)
    # has touched the window's accessibility tree. Prefixing with `_` takes
    # it out of pywebview's introspected surface entirely.
    api._window = window

    # A blank/black window is not the same failure as a Python exception --
    # this writes a timestamped marker the moment WebView2 actually finishes
    # loading the page, so the *next* report of a black window can be
    # checked against this file: if it's missing/stale, the page genuinely
    # never loaded (a WebView2-level problem); if it's fresh, the page did
    # load and the blackness is something else (e.g. a CSS/JS issue).
    def _on_loaded() -> None:
        import datetime
        LOAD_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOAD_LOG_PATH.write_text(
            f"Page loaded OK at {datetime.datetime.now().isoformat()}\nurl={index_uri}\n",
            encoding="utf-8",
        )
        # Signal the UI that the Python bridge is fully initialized
        api.system_ready()

    window.events.loaded += _on_loaded

    # Dedicated WebView2 storage folder: a stale/locked shared default folder
    # from a previous run causes WebView2 init to fail with HRESULT
    # 0x8007139F ("resource not in the correct state") and the window stays
    # blank/black with no visible error to the user.
    storage_path = str(Path(os.environ["LOCALAPPDATA"]) / "RedLineEngine" / "webview")

    # REDLINE_DEBUG_GUI=1 opens Chrome DevTools alongside the window --
    # while the intermittent blank/black-window report is being chased down,
    # this lets it be diagnosed directly (console errors, failed resource
    # loads) instead of guessing blind from outside the process.
    debug = os.environ.get("REDLINE_DEBUG_GUI", "").strip() == "1"
    webview.start(storage_path=storage_path, debug=debug)


def main() -> None:
    # When launched via pythonw.exe (no console) or a double-clicked shortcut,
    # an unhandled exception is otherwise invisible — the process just exits.
    # Log it somewhere findable instead of failing silently.
    try:
        _run()
    except Exception:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
