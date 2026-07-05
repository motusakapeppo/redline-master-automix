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
from .analysis.loudness import to_mono_downsampled
from .analysis.transients import onset_density

# A stem named "bass"/"basso" etc. with less than this fraction of its
# energy below 150Hz almost certainly isn't actually carrying the low end
# (e.g. a "bass" guitar stem that's mostly midrange growl) — validated
# against the actual audio rather than trusted blindly from the file name.
BASS_SUB_ENERGY_MIN = 0.12
BASS_VALIDATION_BAND_HZ = (20.0, 150.0)


@dataclass
class StemAnalysis:
    name: str
    crest: float


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
    transient_density: float
    stems: dict[str, StemAnalysis]

    @property
    def key_name(self) -> str:
        return f"{self.key_tonic} {self.key_mode}"


def has_sub_content(audio, sr: int) -> bool:
    """Checks a single stem's actual audio for real sub/bass energy — used to
    catch a "bass"-named stem that isn't really carrying the low end (a
    growly midrange bass guitar sample, a mislabeled file, etc.)."""
    bands = spectral_band_energies(audio, sr)
    return (bands["sub_bass"] + bands["bass"]) >= BASS_SUB_ENERGY_MIN


def analyze(stems: Stems) -> AnalysisResult:
    mix = stems.mixdown()
    sr = stems.sample_rate

    # BPM/key/spectral shape don't need full-resolution audio — analyzing a
    # downsampled mono mixdown cuts their cost substantially with no material
    # effect on the result (see analysis/loudness.py's ANALYSIS_SR).
    analysis_mono, analysis_sr = to_mono_downsampled(mix, sr)

    bpm = detect_bpm(analysis_mono, analysis_sr)
    tonic, mode, key_conf = detect_key(analysis_mono, analysis_sr)

    mix_bands = spectral_band_energies(analysis_mono, analysis_sr)
    mix_sub_bass = sub_bass_ratio(mix_bands)
    mix_crest = crest_factor(mix)
    mix_lufs = integrated_lufs(mix, sr)  # kept at full resolution — feeds mastering targets
    density = onset_density(analysis_mono, analysis_sr)

    genre = detect_genre(mix_crest, mix_sub_bass, transient_density=density)

    # Cheap per-stem stats only (crest is nearly free). The expensive 6-band
    # spectral filtering used to also run per-stem here, but nothing
    # downstream consumed it yet (masking.py, which will, doesn't exist yet)
    # — computing it for all 24+ stems was pure wasted time. Bring it back
    # scoped to whichever stems actually need it once that lands.
    per_stem: dict[str, StemAnalysis] = {
        name: StemAnalysis(name=name, crest=crest_factor(audio))
        for name, audio in stems.tracks.items()
    }

    return AnalysisResult(
        bpm=bpm,
        key_tonic=tonic,
        key_mode=mode,
        key_confidence=key_conf,
        genre=genre,
        mix_lufs=mix_lufs,
        mix_crest=mix_crest,
        mix_sub_bass_ratio=mix_sub_bass,
        transient_density=density,
        stems=per_stem,
    )
