"""Targeted regression test for the pYIN-reuse optimization: _process_stem
must not re-run estimate_fundamental (confirmed via profiling to cost
several seconds on its own) when render_mix already measured the lead's
fundamental for the doubles' time-alignment step."""

from unittest.mock import patch

import numpy as np

from redline.mixengine import _process_stem
from redline.naming import StemDescriptor


def _lead_audio(n=44100, sr=44100):
    t = np.linspace(0, n / sr, n, endpoint=False)
    mono = (0.3 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)
    return np.stack([mono, mono], axis=1)


def test_process_stem_reuses_lead_fundamental_hint():
    audio = _lead_audio()
    descriptor = StemDescriptor(raw_name="vocal_main", role="vocal", layer="primary")

    with patch("redline.mixengine.estimate_fundamental") as mocked:
        _process_stem(
            "vocal_main", audio, 44100, descriptor,
            on_step=lambda m: None, on_event=lambda e: None,
            lead_fundamental_hint=180.0,
        )
        mocked.assert_not_called()


def test_process_stem_computes_fundamental_when_no_hint():
    audio = _lead_audio()
    descriptor = StemDescriptor(raw_name="vocal_main", role="vocal", layer="primary")

    with patch("redline.mixengine.estimate_fundamental", return_value=180.0) as mocked:
        _process_stem(
            "vocal_main", audio, 44100, descriptor,
            on_step=lambda m: None, on_event=lambda e: None,
            lead_fundamental_hint=None,
        )
        mocked.assert_called_once()
