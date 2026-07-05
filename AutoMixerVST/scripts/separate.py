#!/usr/bin/env python3
"""RED-LINE MASTER - Demucs Source Separation
Usage: python separate.py <input.wav> <output_dir>
Outputs: vocals, drums, bass, other WAVs + JSON with per-stem loudness
"""

import sys, os, json, shutil
import numpy as np
import scipy.io.wavfile as wav
import warnings

warnings.filterwarnings("ignore")


def load_wav(path):
    sr, data = wav.read(path)
    if data.dtype == np.int16:
        data = data.astype(np.float32) / 32768.0
    elif data.dtype == np.int32:
        data = data.astype(np.float32) / 2147483648.0
    if len(data.shape) == 1:
        data = np.stack([data, data], axis=1)
    return data, sr


def save_wav(data, sr, path):
    data = np.clip(data, -1.0, 1.0)
    wav.write(path, sr, (data * 32767).astype(np.int16))


def stem_loudness(path):
    sr, data = wav.read(path)
    if data.dtype == np.int16:
        data = data.astype(np.float32) / 32768.0
    if len(data.shape) == 2:
        data = data.mean(axis=1)
    rms = np.sqrt(np.mean(data**2))
    return float(20.0 * np.log10(rms)) if rms > 1e-6 else -120.0


def main():
    if len(sys.argv) < 3:
        print("Usage: separate.py <input.wav> <output_dir>")
        sys.exit(1)

    inp, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(inp))[0]
    results = {"status": "processing", "input": inp}

    print(f"Loading {inp}...")
    data, sr = load_wav(inp)
    temp = os.path.join(out_dir, "_tmp.wav")
    save_wav(data, sr, temp)

    print("Running Demucs htdemucs (CPU)...")
    try:
        from demucs.separate import main as demucs_main

        sys.argv = ["demucs", "--two-stems", "vocals", "-o", out_dir, temp]
        original_argv = sys.argv
        demucs_main()
        sys.argv = original_argv
    except Exception as e:
        print(f"Demucs error: {e}")
        results["status"] = f"error: {e}"
        if os.path.exists(temp):
            os.remove(temp)
        with open(os.path.join(out_dir, f"{base}_stems.json"), "w") as f:
            json.dump(results, f, indent=2)
        sys.exit(1)

    sep_dir = os.path.join(out_dir, "htdemucs", base)

    for stem_name in ["vocals", "drums", "bass", "other"]:
        src = os.path.join(sep_dir, f"{stem_name}.wav")
        if os.path.exists(src):
            dst = os.path.join(out_dir, f"{base}_{stem_name}.wav")
            shutil.copy2(src, dst)
            loudness = stem_loudness(dst)
            results[stem_name] = {"file": dst, "loudness_db": loudness}
            print(f"  {stem_name}: {loudness:.1f} dB")

    v = results.get("vocals", {}).get("loudness_db", -120)
    b = results.get("bass", {}).get("loudness_db", -120)
    d = results.get("drums", {}).get("loudness_db", -120)
    o = results.get("other", {}).get("loudness_db", -120)

    results["metrics"] = {
        "vocal_prominence_db": v,
        "bass_loudness_db": b,
        "drums_loudness_db": d,
        "vocal_vs_instruments": v - max(b, d, -120),
        "bass_vs_rest": b - o if o > -120 else 0,
        "is_vocal_low": v < max(b, d) - 3.0,
        "is_bass_low": b < o - 3.0,
        "is_drums_low": d < o - 3.0,
    }
    results["status"] = "complete"

    res_path = os.path.join(out_dir, f"{base}_stems.json")
    with open(res_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results: {res_path}")
    if os.path.exists(temp):
        os.remove(temp)
    print("Done!")


if __name__ == "__main__":
    main()
