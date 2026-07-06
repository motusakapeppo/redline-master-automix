import numpy as np

from redline.structure import analyze_structure


def _tone(freq_hz, sr, seconds, amp):
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    return (amp * np.sin(2 * np.pi * freq_hz * t)).astype(np.float32)


def test_analyze_structure_finds_a_loud_dense_chorus():
    sr = 8000  # low sr, fast synthetic test
    quiet = _tone(200, sr, 6.0, 0.05)  # intro-like
    loud = _tone(200, sr, 6.0, 0.6)  # chorus-like instrumental energy
    instrumental = np.stack([np.concatenate([quiet, loud, quiet])] * 2, axis=1)

    # Vocal density: nothing singing during intro/outro, 3 stems overlapping
    # during the loud section -- the actual "chorus" signal.
    silence = np.zeros(6 * sr, dtype=np.float32)
    singing = _tone(300, sr, 6.0, 0.3)
    vocal_stems = {
        "main": np.concatenate([silence, singing, silence]),
        "double_1": np.concatenate([silence, singing, silence]),
        "double_2": np.concatenate([silence, singing, silence]),
    }

    sections = analyze_structure(instrumental, sr, vocal_stems=vocal_stems, block_sec=1.0)

    assert len(sections) >= 2
    # Every section covers non-negative, ordered time and the whole song is covered.
    assert sections[0]["start"] == 0.0
    assert sections[-1]["end"] > 15.0
    for s in sections:
        assert s["end"] > s["start"]

    # At least one section should be identified as a chorus, and it should
    # overlap with where the loud+dense block actually is (roughly 6-12s).
    choruses = [s for s in sections if s["name"].startswith("chorus")]
    assert len(choruses) >= 1
    assert any(s["start"] < 12.0 and s["end"] > 6.0 for s in choruses)


def test_analyze_structure_handles_no_vocal_stems():
    sr = 8000
    instrumental = np.stack([_tone(200, sr, 10.0, 0.3)] * 2, axis=1)
    sections = analyze_structure(instrumental, sr, vocal_stems=None, block_sec=2.0)
    assert len(sections) >= 1
    assert sections[0]["start"] == 0.0


def test_analyze_structure_sections_are_contiguous():
    sr = 8000
    instrumental = np.stack([_tone(200, sr, 8.0, 0.4)] * 2, axis=1)
    sections = analyze_structure(instrumental, sr, block_sec=2.0)
    for prev, nxt in zip(sections, sections[1:]):
        assert prev["end"] == nxt["start"]
