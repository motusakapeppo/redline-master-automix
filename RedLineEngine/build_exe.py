"""Builds the standalone RedLineEngine.exe with PyInstaller.

Run from the RedLineEngine directory with the project venv active:
    .venv\\Scripts\\python build_exe.py

Produces dist/RedLineEngine/RedLineEngine.exe (onedir build — much faster
to start than --onefile, which has to unpack itself to a temp dir on every
launch; startup speed matters more here than a single-file download).
"""

from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    pyinstaller = os.path.join(ROOT, ".venv", "Scripts", "pyinstaller.exe")
    web_dir = os.path.join(ROOT, "app", "web")

    args = [
        pyinstaller,
        "--noconfirm",
        "--windowed",
        "--name", "RedLineEngine",
        "--paths", ROOT,  # so PyInstaller's static analysis can resolve `import redline...`
        "--add-data", f"{web_dir};web",
        "--collect-all", "librosa",
        "--collect-all", "pedalboard",
        "--collect-all", "pyloudnorm",
        "--collect-all", "redline",
        "--hidden-import", "soundfile",
        os.path.join(ROOT, "app", "main.py"),
    ]

    result = subprocess.run(args, cwd=ROOT)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
