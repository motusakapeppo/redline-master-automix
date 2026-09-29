"""ci_validate.py — Continuous Integration Quality Gate.

Runs gain staging verification AND the full pytest suite. Feature flags are
only auto-enabled once both pass — a single gain-staging check is not
evidence that LTAS matching, RT60 calibration, blueprint chains, or LLM
advisory are actually working, so it used to be wrong to let it unlock all
of them by itself.

Exit code 0 = PASS, 1 = FAIL.

Usage:
    python ci_validate.py
    echo $?  # 0 = system ready, 1 = validation failed
"""

import json
import os
import subprocess
import sys

from redline import config as redline_config


ROOT = os.path.dirname(os.path.abspath(__file__))
FLAGS_PATH = os.path.join(ROOT, ".flags.json")
VERIFY_SCRIPT = os.path.join(ROOT, "verify_gain.py")
VENV_PYTHON = os.path.join(ROOT, ".venv", "Scripts", "python.exe")


def _python() -> str:
    return VENV_PYTHON if os.path.exists(VENV_PYTHON) else sys.executable


def _run_verify() -> tuple[bool, str]:
    """Run verify_gain.py and return (passed, output)."""
    python = _python()
    try:
        result = subprocess.run(
            [python, VERIFY_SCRIPT],
            capture_output=True, text=True, timeout=30,
        )
        output = result.stdout + result.stderr
        passed = "ALL CHECKS PASSED" in result.stdout
        return passed, output
    except subprocess.TimeoutExpired:
        return False, "[TIMEOUT] verify_gain.py did not finish in 30s"
    except FileNotFoundError as e:
        return False, f"[ERROR] {e}"
    except Exception as e:
        return False, f"[ERROR] {e}"


def _run_pytest() -> tuple[bool, str]:
    """Run the full test suite and return (passed, output)."""
    python = _python()
    try:
        result = subprocess.run(
            [python, "-m", "pytest", "tests", "-q"],
            capture_output=True, text=True, timeout=1800, cwd=ROOT,
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "[TIMEOUT] pytest did not finish in 1800s"
    except FileNotFoundError as e:
        return False, f"[ERROR] {e}"
    except Exception as e:
        return False, f"[ERROR] {e}"


def _enable_all_flags() -> None:
    """Write .flags.json with every known feature flag enabled.

    The flag surface is derived from redline.config.DEFAULTS so new flags are
    never silently left out. Keys already on disk that are not part of
    DEFAULTS (e.g. ENABLE_DIRECTOR_MODE) are preserved with their current
    value — this must not clobber machine-local user settings.
    """
    all_on: dict = {}
    if os.path.exists(FLAGS_PATH):
        try:
            with open(FLAGS_PATH, "r", encoding="utf-8") as f:
                all_on = json.load(f)
        except Exception:
            all_on = {}
    for flag in redline_config.DEFAULTS:
        all_on[flag] = True
    with open(FLAGS_PATH, "w", encoding="utf-8") as f:
        json.dump(all_on, f, indent=4)
    print(f"[CI] Flags written to {FLAGS_PATH}")


def main() -> int:
    print("=" * 60)
    print("  RedLine Engine — CI Quality Gate")
    print("=" * 60)

    print("\n[Step 1/3] Running gain staging verification...")
    gain_passed, gain_output = _run_verify()
    print(gain_output)
    if not gain_passed:
        print("[FAIL] Gain staging verification FAILED.")
        print("[CI] System NOT ready — check verify_gain.py output above.")
        print("=" * 60)
        return 1

    print("\n[Step 2/3] Running full pytest suite...")
    tests_passed, tests_output = _run_pytest()
    print(tests_output)
    if not tests_passed:
        print("[FAIL] Test suite FAILED.")
        print("[CI] System NOT ready — feature flags left untouched.")
        print("=" * 60)
        return 1

    print("\n[Step 3/3] Gain staging + full test suite PASSED — enabling feature flags...")
    _enable_all_flags()

    print("\n[CI] CI VALIDATION: PASS")
    print("[CI] System ready — all flags enabled, Neural Monitor online.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
