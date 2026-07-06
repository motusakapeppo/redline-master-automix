"""Reference-track profiler: builds real per-genre spectral targets from a
folder of commercial reference tracks, instead of the theoretical curves the
QC pass ships with.

Usage:
    python -m redline.profile_targets "EDM / Urban" "C:\\refs\\edm"

Analyzes every audio file in the folder, computes each track's 6-band energy
distribution (the same bands the QC pass measures), averages them into a
Long-Term Average Spectrum for the genre, and writes
redline/targets/target_<slug>.json. The QC pass (via targets.py) then
compares finished masters against this measured industry average.

Point it at 20-30 high-quality commercial tracks per genre for a meaningful
average. Files are only read, never modified.
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np
import soundfile as sf

from .analysis.loudness import spectral_band_energies, SPECTRAL_BANDS
from .targets import TARGETS_DIR, genre_slug, target_path

AUDIO_EXTENSIONS = (".wav", ".flac", ".aiff", ".aif", ".mp3", ".ogg")
BAND_NAMES = [name for name, _lo, _hi in SPECTRAL_BANDS]


def _profile_file(path: str) -> dict[str, float] | None:
    try:
        data, sr = sf.read(path, dtype="float32", always_2d=True)
    except Exception:
        return None
    if data.shape[0] < sr:  # under a second, not worth profiling
        return None
    return spectral_band_energies(data, sr)


def profile_folder(genre_name: str, folder: str) -> dict:
    files = [
        os.path.join(folder, f)
        for f in sorted(os.listdir(folder))
        if os.path.splitext(f)[1].lower() in AUDIO_EXTENSIONS
    ]
    if not files:
        raise ValueError(f"No audio files found in {folder}")

    per_file = []
    used = []
    for path in files:
        ratios = _profile_file(path)
        if ratios is not None:
            per_file.append([ratios[b] for b in BAND_NAMES])
            used.append(os.path.basename(path))
            print(f"  profiled: {os.path.basename(path)}")

    if not per_file:
        raise ValueError(f"None of the files in {folder} could be profiled")

    mean_ratios = np.mean(np.array(per_file), axis=0)
    # Renormalize so the averaged band ratios sum to 1.0 again.
    mean_ratios = mean_ratios / (mean_ratios.sum() + 1e-12)

    return {
        "genre": genre_name,
        "slug": genre_slug(genre_name),
        "n_tracks": len(used),
        "source_files": used,
        "band_ratios": {b: float(v) for b, v in zip(BAND_NAMES, mean_ratios)},
    }


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) < 2:
        print('Usage: python -m redline.profile_targets "<Genre Name>" <folder_of_reference_tracks>')
        return 1

    genre_name, folder = argv[0], argv[1]
    result = profile_folder(genre_name, folder)

    os.makedirs(TARGETS_DIR, exist_ok=True)
    out_path = target_path(genre_name)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"\nProfiled {result['n_tracks']} tracks for '{genre_name}':")
    for band, ratio in result["band_ratios"].items():
        print(f"  {band:9s} {ratio * 100:5.1f}%")
    print(f"\nWritten: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
