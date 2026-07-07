"""Normalizes the three supported input modes (stems folder, vocals+instrumental
pair, single mixed file) into one common in-memory representation: a dict of
named stem tracks sharing sample rate, length and channel count."""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass, field

import numpy as np
import soundfile as sf
import librosa

from redline.preflight import PreFlightValidator
from redline.logging_setup import get_logger

logger = get_logger(__name__)

AUDIO_EXTENSIONS = (".wav", ".flac", ".aiff", ".aif", ".mp3", ".ogg")

# Our own conventional output file names (cli.py/app/api.py always write
# exactly "mix.wav"/"master.wav"). If a previous run's output happens to sit
# inside the folder being loaded as input (e.g. an output dir nested under
# the source project), it must not be silently re-ingested as an extra stem
# and summed into the next render — that's real, confirmed-in-practice data
# contamination on repeated runs, not a hypothetical edge case.
RESERVED_OUTPUT_NAMES = {"mix", "master"}


def _is_reserved_output(rel_path_no_ext: str) -> bool:
    basename = os.path.basename(rel_path_no_ext).lower()
    return basename in RESERVED_OUTPUT_NAMES


@dataclass
class Stems:
    sample_rate: int
    tracks: dict[str, np.ndarray] = field(default_factory=dict)  # name -> (n_samples, n_channels) float32

    def names(self) -> list[str]:
        return list(self.tracks.keys())

    def num_samples(self) -> int:
        return next(iter(self.tracks.values())).shape[0] if self.tracks else 0

    def mixdown(self) -> np.ndarray:
        """Sum of all stems, useful for whole-mix analysis (LUFS, bpm, key, genre)."""
        total = np.zeros((self.num_samples(), 2), dtype=np.float32)
        for track in self.tracks.values():
            total += track
        return total


def _read_audio(path: str) -> tuple[np.ndarray, int]:
    """Reads any supported audio file as float32 (n_samples, n_channels), stereo-forced."""
    data, sr = sf.read(path, dtype="float32", always_2d=True)
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    elif data.shape[1] > 2:
        data = data[:, :2]
    return data, sr


def _align(named: dict[str, tuple[np.ndarray, int]]) -> Stems:
    """Resamples everything to the highest sample rate found and zero-pads to the
    longest track, so every stem in the returned Stems has identical shape."""
    sample_rates = [sr for _, sr in named.values()]
    mixed_sr_report = PreFlightValidator.check_mixed_sample_rates(sample_rates, "stems")
    if mixed_sr_report.warnings or mixed_sr_report.issues:
        for w in mixed_sr_report.warnings:
            logger.warning(w)
        if not mixed_sr_report.passed:
            for issue in mixed_sr_report.issues:
                logger.error(issue)
            raise ValueError("PreFlight fallito:\n" + "\n".join(mixed_sr_report.issues))

    issues: list[str] = []
    for name, (data, sr) in named.items():
        report = PreFlightValidator.check_audio(data, sr, name)
        for w in report.warnings:
            logger.warning(w)
        if not report.passed:
            issues.extend(report.issues)
    if issues:
        for issue in issues:
            logger.error(issue)
        raise ValueError("PreFlight fallito:\n" + "\n".join(issues))

    target_sr = max(sr for _, sr in named.values())

    resampled: dict[str, np.ndarray] = {}
    for name, (data, sr) in named.items():
        if sr != target_sr:
            data = librosa.resample(data.T, orig_sr=sr, target_sr=target_sr).T
        resampled[name] = data.astype(np.float32)

    max_len = max(d.shape[0] for d in resampled.values())
    aligned: dict[str, np.ndarray] = {}
    for name, data in resampled.items():
        if data.shape[0] < max_len:
            pad = np.zeros((max_len - data.shape[0], data.shape[1]), dtype=np.float32)
            data = np.concatenate([data, pad], axis=0)
        aligned[name] = data

    return Stems(sample_rate=target_sr, tracks=aligned)


def load_stems_dir(directory: str) -> Stems:
    """Mode A: a folder containing an arbitrary number of named stem files,
    optionally organized into subfolders (e.g. a top-level instrumental file
    plus a "vocals stems" subfolder full of takes). Walks recursively and
    keys each stem by its path relative to `directory` (folder names included,
    extension stripped) — the folder name is often the clearest role signal
    a user gives us (e.g. "vocals stems/Main - Str1.wav"), so it must survive
    into the stem name that naming.parse_stem() later inspects."""
    named: dict[str, tuple[np.ndarray, int]] = {}
    for root, _dirs, files in os.walk(directory):
        for fname in sorted(files):
            ext = os.path.splitext(fname)[1].lower()
            if ext not in AUDIO_EXTENSIONS:
                continue
            full_path = os.path.join(root, fname)
            rel_path = os.path.relpath(full_path, directory)
            stem_name = os.path.splitext(rel_path)[0].replace(os.sep, "/")
            if _is_reserved_output(stem_name):
                continue
            named[stem_name] = _read_audio(full_path)

    if not named:
        raise ValueError(f"No audio files found in {directory}")

    return _align(named)


def load_two_track(vocals_path: str, instrumental_path: str) -> Stems:
    """Mode B: a pre-mixed vocals track + a pre-mixed instrumental track."""
    named = {
        "vocals": _read_audio(vocals_path),
        "instrumental": _read_audio(instrumental_path),
    }
    return _align(named)


def separate_with_demucs(input_path: str, work_dir: str | None = None) -> dict[str, str]:
    """Mode C helper: runs Demucs (4-stem htdemucs model) on a single mixed file
    and returns {stem_name: wav_path} for vocals/drums/bass/other."""
    from demucs.separate import main as demucs_main

    work_dir = work_dir or tempfile.mkdtemp(prefix="redline_demucs_")
    base = os.path.splitext(os.path.basename(input_path))[0]

    argv_backup = sys.argv
    try:
        sys.argv = ["demucs", "-o", work_dir, input_path]
        demucs_main()
    finally:
        sys.argv = argv_backup

    sep_dir = os.path.join(work_dir, "htdemucs", base)
    stems = {}
    for name in ("vocals", "drums", "bass", "other"):
        path = os.path.join(sep_dir, f"{name}.wav")
        if os.path.exists(path):
            stems[name] = path
    if not stems:
        raise RuntimeError(f"Demucs did not produce any stems in {sep_dir}")
    return stems


def load_single_file(input_path: str, work_dir: str | None = None) -> Stems:
    """Mode C: a single mixed file — auto-separated into stems via Demucs first."""
    stem_paths = separate_with_demucs(input_path, work_dir)
    named = {name: _read_audio(path) for name, path in stem_paths.items()}
    return _align(named)


def _find_audio_files(directory: str) -> list[str]:
    found = []
    for root, _dirs, files in os.walk(directory):
        for fname in files:
            base, ext = os.path.splitext(fname)
            if ext.lower() in AUDIO_EXTENSIONS and base.lower() not in RESERVED_OUTPUT_NAMES:
                found.append(os.path.join(root, fname))
    return found


def load_auto(path: str, work_dir: str | None = None, on_step=None) -> Stems:
    """Single entry point: point it at one file or one folder and it figures
    out the right loading mode, so the user doesn't need to already know
    whether they have stems, a vocals+instrumental pair, or a single mixdown.

    - A single audio file (or a folder containing exactly one) -> Demucs
      auto-separation (Mode C).
    - A folder containing several audio files, in any subfolder layout (e.g.
      a top-level pre-mixed instrumental + a "vocals stems" subfolder full of
      takes, as in a real production session) -> load_stems_dir, which already
      keys stems by their folder-inclusive relative path so naming.py can read
      the folder name as a role signal (Mode A).
    """
    narrate = on_step or (lambda _msg: None)

    if os.path.isfile(path):
        narrate(f"Rilevato un singolo file audio: separazione automatica con Demucs...")
        return load_single_file(path, work_dir)

    if not os.path.isdir(path):
        raise ValueError(f"Path not found: {path}")

    audio_files = _find_audio_files(path)
    if not audio_files:
        raise ValueError(f"No audio files found in {path}")

    if len(audio_files) == 1:
        narrate(f"Cartella con un solo file audio ('{os.path.basename(audio_files[0])}'): separazione automatica con Demucs...")
        return load_single_file(audio_files[0], work_dir)

    narrate(f"Rilevati {len(audio_files)} file audio nella cartella: uso la struttura di sottocartelle per capire i ruoli.")
    return load_stems_dir(path)
