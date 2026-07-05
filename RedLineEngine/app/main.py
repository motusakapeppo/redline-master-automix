"""Desktop app entry point: opens a pywebview window backed by the same
engine used by redline/cli.py — no CLI required for day-to-day use."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow `python app/main.py` to find the `redline` package that lives in the
# RedLineEngine root, one level up from this file, without a pip install step.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import webview

from api import Api


def main() -> None:
    api = Api()
    web_dir = Path(__file__).resolve().parent / "web"
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
    api.window = window

    # Dedicated WebView2 storage folder: a stale/locked shared default folder
    # from a previous run causes WebView2 init to fail with HRESULT
    # 0x8007139F ("resource not in the correct state") and the window stays
    # blank/black with no visible error to the user.
    storage_path = str(Path(os.environ["LOCALAPPDATA"]) / "RedLineEngine" / "webview")
    webview.start(storage_path=storage_path)


if __name__ == "__main__":
    main()
