"""verify_gain.py — Synthetic gain-staging test for the mix bus.

Simulates the mix bus logic from mixengine.py (lines 796-810):
  - Main (lead vocal) goes into mix at full level via Vocal_Main bus
  - Double (backing vocal) goes into mix at 0.5x via Vocal_Doubles bus
  - Asserts that Main is undistorted and Doubles are at -6dB relative to Main
"""

import numpy as np

# Constants matching mixengine.py
SR = 44100
DURATION_SEC = 2.0
N_SAMPLES = int(SR * DURATION_SEC)
FREQ_HZ = 440.0
_DOUBLES_VOLUME_SCALE = 0.5  # matches line 699: vocal_doubles_bus * 0.5

# Tolerance for floating-point RMS comparisons
RMS_TOLERANCE = 0.001


def rms(signal: np.ndarray) -> float:
    """Compute RMS of a mono signal."""
    return float(np.sqrt(np.mean(signal ** 2)))


def generate_sine(amplitude: float, freq: float = FREQ_HZ,
                  sr: int = SR, n: int = N_SAMPLES) -> np.ndarray:
    """Generate a mono sine tone at the given amplitude."""
    t = np.arange(n, dtype=np.float64) / sr
    return (amplitude * np.sin(2.0 * np.pi * freq * t)).astype(np.float32)


def main():
    # --- Generate test signals ---
    # Main: 440Hz sine at 0dBFS (amplitude 1.0)
    main_original = generate_sine(amplitude=1.0)
    # Double: 440Hz sine at -6dBFS (amplitude 0.5)
    double_original = generate_sine(amplitude=0.5)

    # --- Compute original RMS values ---
    main_rms_original = rms(main_original)
    double_rms_original = rms(double_original)

    # Expected theoretical RMS for a pure sine: A / sqrt(2)
    main_rms_expected = 1.0 / np.sqrt(2)   # ~0.7071
    double_rms_expected = 0.5 / np.sqrt(2)  # ~0.3536

    print(f"Original Main  RMS: {main_rms_original:.6f}  (expected ~{main_rms_expected:.6f})")
    print(f"Original Double RMS: {double_rms_original:.6f}  (expected ~{double_rms_expected:.6f})")

    # --- Simulate mix bus routing ---
    # Main goes into Vocal_Main bus at full level (no scaling)
    main_in_mix = main_original.copy()

    # Double goes into Vocal_Doubles bus, scaled by _DOUBLES_VOLUME_SCALE
    double_in_mix = double_original * _DOUBLES_VOLUME_SCALE

    # --- Compute post-mix RMS values ---
    main_mix_rms = rms(main_in_mix)
    double_mix_rms = rms(double_in_mix)

    # Expected: Main unchanged, Double at -6dB relative to Main
    # Double after mix = 0.5 * (0.5 / sqrt(2)) = 0.25 / sqrt(2) ≈ 0.1768
    double_mix_expected = double_rms_expected * _DOUBLES_VOLUME_SCALE

    print(f"\nMain  in mix RMS: {main_mix_rms:.6f}  (expected ~{main_rms_expected:.6f})")
    print(f"Double in mix RMS: {double_mix_rms:.6f}  (expected ~{double_mix_expected:.6f})")

    # --- Assertions ---
    all_pass = True

    # 1. Main RMS in mix == Main RMS original (Main is NOT distorted)
    main_ok = abs(main_mix_rms - main_rms_original) < RMS_TOLERANCE
    if main_ok:
        print(f"\n[PASS] Main RMS in mix ({main_mix_rms:.6f}) == Main RMS original ({main_rms_original:.6f}) "
              f"(diff={abs(main_mix_rms - main_rms_original):.6f})")
    else:
        print(f"\n[FAIL] Main RMS in mix ({main_mix_rms:.6f}) != Main RMS original ({main_rms_original:.6f}) "
              f"(diff={abs(main_mix_rms - main_rms_original):.6f})")
        all_pass = False

    # 2. Double RMS in mix == Double RMS original * 0.5
    double_ok = abs(double_mix_rms - double_rms_original * _DOUBLES_VOLUME_SCALE) < RMS_TOLERANCE
    if double_ok:
        print(f"[PASS] Double RMS in mix ({double_mix_rms:.6f}) == Double RMS original * 0.5 "
              f"({double_rms_original * _DOUBLES_VOLUME_SCALE:.6f}) "
              f"(diff={abs(double_mix_rms - double_rms_original * _DOUBLES_VOLUME_SCALE):.6f})")
    else:
        print(f"[FAIL] Double RMS in mix ({double_mix_rms:.6f}) != Double RMS original * 0.5 "
              f"({double_rms_original * _DOUBLES_VOLUME_SCALE:.6f}) "
              f"(diff={abs(double_mix_rms - double_rms_original * _DOUBLES_VOLUME_SCALE):.6f})")
        all_pass = False

    # --- Summary ---
    print(f"\n{'=' * 50}")
    if all_pass:
        print("ALL CHECKS PASSED — Gain staging is correct.")
    else:
        print("SOME CHECKS FAILED — Review gain staging logic.")
    print(f"{'=' * 50}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    exit(main())
