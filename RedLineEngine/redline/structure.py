"""Structure-Aware Engine: maps a song into intro/verse/chorus sections so
later features (per-section LLM-driven DSP, a correction timeline UI) have
something concrete to act on. Uses the same "unfair advantage" idea the
rest of the engine already leans on -- stems, not just the mixed-down
signal: the chorus heuristic combines instrumental RMS energy with how
many vocal stems are actually singing at once (Main + Doubles + Ad-libs
overlapping is the strongest chorus signal there is), instead of running
a generic music-structure algorithm blind on a mono mixdown."""

from __future__ import annotations

import numpy as np

BLOCK_SECONDS = 2.0
BOUNDARY_SCORE_JUMP = 0.35  # combined-score delta that counts as a section change
GATE_DB = -40.0  # a vocal stem below this in a block counts as "not singing" there


def _rms_blocks(audio: np.ndarray, sr: int, block_sec: float = BLOCK_SECONDS) -> tuple[np.ndarray, int]:
    mono = audio.mean(axis=1) if audio.ndim == 2 else audio
    hop = max(int(block_sec * sr), 1)
    n_blocks = max(1, len(mono) // hop)
    rms = np.array(
        [
            float(np.sqrt(np.mean(mono[i * hop : (i + 1) * hop].astype(np.float64) ** 2) + 1e-12))
            for i in range(n_blocks)
        ]
    )
    return rms, hop


def _vocal_density_blocks(vocal_stems: dict[str, np.ndarray], sr: int, hop: int, n_blocks: int) -> np.ndarray:
    """Counts, per block, how many of the given vocal stems have energy
    above GATE_DB -- this is the "voice density" signal: a chorus is where
    Main + Doubles + Ad-libs stack up, not just where the instrumental
    happens to be loud (a big instrumental break would otherwise look like
    a chorus to an energy-only heuristic)."""
    density = np.zeros(n_blocks)
    for audio in vocal_stems.values():
        mono = audio.mean(axis=1) if audio.ndim == 2 else audio
        for i in range(n_blocks):
            block = mono[i * hop : (i + 1) * hop]
            if len(block) == 0:
                continue
            rms_db = 20.0 * np.log10(np.sqrt(np.mean(block.astype(np.float64) ** 2)) + 1e-12)
            if rms_db > GATE_DB:
                density[i] += 1
    return density


def analyze_structure(
    instrumental: np.ndarray,
    sr: int,
    vocal_stems: dict[str, np.ndarray] | None = None,
    block_sec: float = BLOCK_SECONDS,
) -> list[dict]:
    """Returns an ordered list of {"name", "start", "end"} sections (seconds).
    Combines instrumental RMS energy with vocal stem overlap density into
    one normalized score per time block, then segments wherever that score
    jumps by more than BOUNDARY_SCORE_JUMP. Sections scoring well above
    the song's own average become "chorus_N", the first below-average
    block is "intro", everything else is "verse_N" -- a deliberately
    simple, auditable rule set instead of a black-box classifier, since a
    human reviews and can rename/adjust these boundaries anyway."""
    rms, hop = _rms_blocks(instrumental, sr, block_sec)
    n_blocks = len(rms)
    rms_db = 20.0 * np.log10(rms + 1e-12)

    density = _vocal_density_blocks(vocal_stems, sr, hop, n_blocks) if vocal_stems else np.zeros(n_blocks)

    rms_range = max(rms_db.max() - rms_db.min(), 1e-6)
    normalized_rms = (rms_db - rms_db.min()) / rms_range
    normalized_density = density / max(density.max(), 1.0)
    score = normalized_rms + 0.5 * normalized_density

    boundaries = {0, n_blocks}
    for i in range(1, n_blocks):
        if abs(score[i] - score[i - 1]) > BOUNDARY_SCORE_JUMP:
            boundaries.add(i)
    boundaries = sorted(boundaries)

    mean_score = float(score.mean())
    sections: list[dict] = []
    verse_count = 0
    chorus_count = 0
    for i in range(len(boundaries) - 1):
        start_block, end_block = boundaries[i], boundaries[i + 1]
        avg_score = float(score[start_block:end_block].mean())
        start_t = round(start_block * block_sec, 1)
        end_t = round(end_block * block_sec, 1)

        if i == 0 and avg_score < mean_score:
            name = "intro"
        elif avg_score > mean_score + 0.1:
            chorus_count += 1
            name = f"chorus_{chorus_count}"
        else:
            verse_count += 1
            name = f"verse_{verse_count}"

        sections.append({"name": name, "start": start_t, "end": end_t})

    return sections
