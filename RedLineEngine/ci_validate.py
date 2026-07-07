"""ci_validate.py — Continuous Integration Quality Gate.

Runs verify_gain.py to validate the DSP chain, then auto-enables all
feature flags if the test passes. Exit code 0 = PASS, 1 = FAIL.

Usage:
    python ci_validate.py
    echo $?  # 0 = system ready, 1 = validation failed
"""

import json
import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.abspath(__file__))
FLAGS_PATH = os.path.join(ROOT, ".flags.json")
VERIFY_SCRIPT = os.path.join(ROOT, "verify_gain.py")
VENV_PYTHON = os.path.join(ROOT, ".venv", "Scripts", "python.exe")


def _run_verify() -> tuple[bool, str]:
    """Run verify_gain.py and return (passed, output)."""
    python = VENV_PYTHON if os.path.exists(VENV_PYTHON) else sys.executable
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


def _enable_all_flags() -> None:
    """Write .flags.json with all features enabled."""
    all_on = {
        "ENABLE_LIVE_AUDITION": True,
        "ENABLE_BLUEPRINT_CHAINS": True,
        "ENABLE_LTAS_MATCHING": True,
        "ENABLE_RT60_CALIBRATION": True,
        "ENABLE_LLM_ADVISORY": True,
    }
    with open(FLAGS_PATH, "w", encoding="utf-8") as f:
        json.dump(all_on, f, indent=4)
    print(f"[CI] Flags written to {FLAGS_PATH}")


def main() -> int:
    print("=" * 60)
    print("  RedLine Engine — CI Quality Gate")
    print("=" * 60)

    # Step 1: Run verification
    print("\n[Step 1/2] Running gain staging verification...")
    passed, output = _run_verify()
    print(output)

    if not passed:
        print("[FAIL] Gain staging verification FAILED.")
        print("[CI] System NOT ready — check verify_gain.py output above.")
        print("=" * 60)
        return 1

    # Step 2: Enable all flags
    print("\n[Step 2/2] Verification PASSED — enabling all feature flags...")
    _enable_all_flags()

    print("\n[CI] CI VALIDATION: PASS")
    print("[CI] System ready — all flags enabled, Neural Monitor online.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
