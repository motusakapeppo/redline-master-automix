"""Ties the analysis submodules together into one AnalysisResult for a Stems
object. Every field here must actually be consumed downstream by mixengine.py
/ masterengine.py — the old plugin's bug was computing rich analysis data and
never wiring it into the signal path; this module exists so that mistake is
structurally harder to repeat (mixengine/masterengine take this object, not
raw audio, as their primary input)."""

from __future__ import annotations

from dataclasses import dataclass, field

from .input_loader import Stems
from .analysis import (
    detect_bpm,
    detect_key,
    integrated_lufs,
    crest_factor,
    spectral_band_energies,
    sub_bass_ratio,
    detect_genre,
    GenreProfile,
)


@dataclass
class StemAnalysis:
    name: str
    lufs: float
    crest: float
    band_energies: dict[str, float]


@dataclass
class AnalysisResult:
    bpm: float
    key_tonic: str
    key_mode: str
    key_confidence: float
    genre: GenreProfile
    mix_lufs: float
    mix_crest: float
    mix_sub_bass_ratio: float
    stems: dict[str, StemAnalysis]

    @property
    def key_name(self) -> str:
        return f"{self.key_tonic} {self.key_mode}"


def analyze(stems: Stems) -> AnalysisResult:
    mix = stems.mixdown()
    sr = stems.sample_rate

    bpm = detect_bpm(mix, sr)
    tonic, mode, key_conf = detect_key(mix, sr)

    mix_bands = spectral_band_energies(mix, sr)
    mix_sub_bass = sub_bass_ratio(mix_bands)
    mix_crest = crest_factor(mix)
    mix_lufs = integrated_lufs(mix, sr)

    genre = detect_genre(mix_crest, mix_sub_bass)

    per_stem: dict[str, StemAnalysis] = {}
    for name, audio in stems.tracks.items():
        bands = spectral_band_energies(audio, sr)
        per_stem[name] = StemAnalysis(
            name=name,
            lufs=integrated_lufs(audio, sr),
            crest=crest_factor(audio),
            band_energies=bands,
        )

    return AnalysisResult(
        bpm=bpm,
        key_tonic=tonic,
        key_mode=mode,
        key_confidence=key_conf,
        genre=genre,
        mix_lufs=mix_lufs,
        mix_crest=mix_crest,
        mix_sub_bass_ratio=mix_sub_bass,
        stems=per_stem,
    )
