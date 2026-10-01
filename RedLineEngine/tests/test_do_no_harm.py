"""Do-no-harm dynamics (flag-gated): crest-aware glue-compression skip.

ENABLE_DO_NO_HARM off (default) => the render is bit-identical to before this
feature existed: the bus glue compressor always runs, no extra narration.
On => when the mix bus is already at/below the genre's crest target (already
dense material), the glue stage is skipped instead of flattening it further,
and the skip is narrated. Dynamic material (crest above target) still gets
the glue exactly as with the flag off.
"""

from __future__ import annotations

import numpy as np
import pytest

from redline import config
from redline.input_loader import Stems
from redline.analyze import analyze
from redline.wizard import MixPreferences
from redline.mixengine import render_mix

# Distinctive substring of the do-no-harm skip narration (mixengine.py).
_SKIP_MARKER = "salto la compressione glue"


@pytest.fixture(autouse=True)
def _restore_flags():
    yield
    config.reload()  # leave global flag state clean for other tests


def _stems(tracks: dict[str, np.ndarray], sr: int = 44100) -> Stems:
    def st(m: np.ndarray) -> np.ndarray:
        return np.stack([m, m], axis=1).astype(np.float32)

    return Stems(sample_rate=sr, tracks={name: st(m) for name, m in tracks.items()})


def _dense_stems(sr: int = 44100, seconds: float = 2.0) -> Stems:
    """Continuous tones only: very low crest factor (already-dense material)."""
    n = int(sr * seconds)
    t = np.linspace(0, seconds, n, endpoint=False)
    return _stems({
        "vocals": 0.2 * np.sin(2 * np.pi * 220.0 * t),
        "bass": 0.3 * np.sin(2 * np.pi * 220.0 * t),
        "drums": 0.15 * np.sin(2 * np.pi * 220.0 * t),
        "other": 0.2 * np.sin(2 * np.pi * 220.0 * t),
    })


def _dynamic_stems(sr: int = 44100, seconds: float = 2.0) -> Stems:
    """Sparse sharp clicks over a near-silent bed: huge crest factor."""
    n = int(sr * seconds)
    t = np.linspace(0, seconds, n, endpoint=False)
    bed = 0.01 * np.sin(2 * np.pi * 220.0 * t)
    clicks = np.zeros(n)
    idx = np.arange(300)
    burst = 0.9 * np.exp(-8.0 * idx / 300) * np.sin(2 * np.pi * 900.0 * idx / sr)
    for start in range(0, n - 400, sr // 2):
        clicks[start:start + 300] += burst
    signal = bed + clicks
    return _stems({
        "vocals": signal,
        "bass": 0.5 * signal,
        "drums": signal,
        "other": 0.5 * signal,
    })


def test_flag_off_render_bit_identical_to_explicit_off():
    """Flag off: the default-path render is bit-identical to a render with the
    flag explicitly off, and the glue never narrates a skip."""
    stems = _dense_stems()
    analysis = analyze(stems)
    config.set_override("ENABLE_DO_NO_HARM", False)
    explicit_off = render_mix(stems, analysis, MixPreferences())
    config.reload()  # untouched defaults (flag defaults to False)
    default = render_mix(stems, analysis, MixPreferences())
    assert np.array_equal(default, explicit_off)


def test_flag_on_dense_material_skips_glue():
    """Flag on + already-dense material: the glue stage is skipped and the
    skip is narrated (no bus_compressor event emitted)."""
    config.set_override("ENABLE_DO_NO_HARM", True)
    stems = _dense_stems()
    analysis = analyze(stems)
    steps: list[str] = []
    events: list[dict] = []
    render_mix(stems, analysis, MixPreferences(), on_step=steps.append, on_event=events.append)
    assert any(_SKIP_MARKER in s for s in steps)
    assert not any(e.get("type") == "bus_compressor" for e in events)


def test_flag_on_dynamic_material_still_applies_glue():
    """Flag on + dynamic material (crest above the genre target): the glue
    stage runs exactly as with the flag off — bit-identical output."""
    config.set_override("ENABLE_DO_NO_HARM", True)
    stems = _dynamic_stems()
    analysis = analyze(stems)
    steps: list[str] = []
    events: list[dict] = []
    mixed = render_mix(stems, analysis, MixPreferences(), on_step=steps.append, on_event=events.append)
    config.set_override("ENABLE_DO_NO_HARM", False)
    off = render_mix(stems, analysis, MixPreferences())
    assert np.array_equal(mixed, off)
    assert not any(_SKIP_MARKER in s for s in steps)
    assert any(e.get("type") == "bus_compressor" for e in events)