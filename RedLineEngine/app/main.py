"""Desktop app entry point: opens a pywebview window backed by the same
engine used by redline/cli.py — no CLI required for day-to-day use."""

from __future__ import annotations

import os
import sys

# Allow `python app/main.py` to find the `redline` package that lives in the
# RedLineEngine root, one level up from this file, without a pip install step.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import webview

from api import Api


def main() -> None:
    api = Api()
    web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
    window = webview.create_window(
        "RedLine Engine",
        url=os.path.join(web_dir, "index.html"),
        js_api=api,
        width=880,
        height=680,
        min_size=(720, 560),
        background_color="#0A0A0A",
    )
    api.window = window
    webview.start()


if __name__ == "__main__":
    main()
