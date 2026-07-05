"""Musical key detection via chroma features + Krumhansl-Schmuckler key-profile
correlation. No essentia/madmom dependency (neither ships Windows wheels) —
this is a well-documented, self-contained algorithm."""

from __future__ import annotations

import numpy as np
import librosa

from .loudness import to_mono

PITCH_CLASSES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Krumhansl-Kessler key profiles (relative pull of each scale degree)
MAJOR_PROFILE = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
)
MINOR_PROFILE = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
)


def detect_key(signal: np.ndarray, sr: int) -> tuple[str, str, float]:
    """Returns (tonic_name, mode, correlation_confidence) where mode is
    'major' or 'minor'."""
    mono = to_mono(signal).astype(np.float32)
    chroma = librosa.feature.chroma_cqt(y=mono, sr=sr)
    profile_vector = chroma.mean(axis=1)
    profile_vector = profile_vector / (np.linalg.norm(profile_vector) + 1e-9)

    best_score = -np.inf
    best_tonic = "C"
    best_mode = "major"

    for shift in range(12):
        for mode, profile in (("major", MAJOR_PROFILE), ("minor", MINOR_PROFILE)):
            rotated = np.roll(profile, shift)
            rotated = rotated / np.linalg.norm(rotated)
            score = float(np.dot(profile_vector, rotated))
            if score > best_score:
                best_score = score
                best_tonic = PITCH_CLASSES[shift]
                best_mode = mode

    return best_tonic, best_mode, best_score
