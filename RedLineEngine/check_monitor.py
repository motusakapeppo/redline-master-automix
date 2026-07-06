"""Neural Monitor readiness check: verifies the ENABLE_LIVE_AUDITION flag
is active and that sounddevice can enumerate audio hardware."""

import sys
import os

# Ensure the project root is on sys.path so we can import redline.config
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from redline import config

FLAG_NAME = "ENABLE_LIVE_AUDITION"

# ── 1. Flag check ──────────────────────────────────────────────────────────
flag_state = config.is_enabled(FLAG_NAME)
print(f"Flag: {FLAG_NAME} = {flag_state}")
if not flag_state:
    print("[WARN] Flag is OFF — Neural Monitor will be skipped at runtime.")
else:
    print("[OK]   Flag is ON — Neural Monitor is enabled.")

# ── 2. sounddevice hardware check ─────────────────────────────────────────
try:
    import sounddevice as sd

    devices = sd.query_devices()
    print(f"\nsounddevice {sd.__version__}: {len(devices)} device(s) found")

    default_input = sd.query_devices(kind="input")
    default_output = sd.query_devices(kind="output")
    print(f"  Default input  : {default_input['name']} "
          f"(channels={default_input['max_input_channels']})")
    print(f"  Default output : {default_output['name']} "
          f"(channels={default_output['max_output_channels']})")

    # Quick sanity: try opening an output stream briefly
    try:
        with sd.OutputStream(samplerate=44100, channels=1, blocksize=512,
                             latency="low") as _:
            pass
        print("\n[PASS] Audio hardware ready — OutputStream opened OK")
    except Exception as stream_err:
        print(f"\n[FAIL] OutputStream open failed: {stream_err}")
        print("       Neural Monitor will not produce sound on this machine.")

except ImportError:
    print("\n[FAIL] sounddevice not installed. Run: pip install sounddevice")
except Exception as dev_err:
    print(f"\n[FAIL] sounddevice init failed: {dev_err}")
    print("       No audio devices found or PortAudio backend unavailable.")
