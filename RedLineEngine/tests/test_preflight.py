import os

import numpy as np
import pytest
import soundfile as sf

from redline.preflight import PreFlightValidator
from redline.input_loader import load_auto


def _stereo(n=4410, sr=44100, amp=0.3):
    t = np.linspace(0, n / sr, n, endpoint=False)
    left = (amp * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    right = (amp * np.sin(2 * np.pi * 445 * t)).astype(np.float32)
    return np.stack([left, right], axis=1)


def test_validates_normal_audio_passes():
    report = PreFlightValidator.check_audio(_stereo(), 44100, "vocals")
    assert report.passed is True
    assert report.issues == []


def test_detects_nan_samples():
    audio = _stereo()
    audio[10, 0] = np.nan
    report = PreFlightValidator.check_audio(audio, 44100, "vocals")
    assert report.passed is False
    assert any("NaN" in i for i in report.issues)


def test_detects_inf_samples():
    audio = _stereo()
    audio[10, 0] = np.inf
    report = PreFlightValidator.check_audio(audio, 44100, "vocals")
    assert report.passed is False
    assert any("Inf" in i for i in report.issues)


def test_detects_false_stereo():
    mono = _stereo()[:, :1]
    audio = np.repeat(mono, 2, axis=1)
    report = PreFlightValidator.check_audio(audio, 44100, "vocals")
    assert report.passed is True
    assert any("identici" in w for w in report.warnings)


def test_detects_silence():
    audio = np.zeros((4410, 2), dtype=np.float32)
    report = PreFlightValidator.check_audio(audio, 44100, "vocals")
    assert report.passed is False
    assert any("silenzio" in i for i in report.issues)


def test_detects_dc_offset():
    audio = _stereo() + 0.05
    report = PreFlightValidator.check_audio(audio.astype(np.float32), 44100, "vocals")
    assert any("DC" in w for w in report.warnings)


def test_detects_clipping():
    audio = _stereo(amp=0.9)
    audio[0, 0] = 1.2
    report = PreFlightValidator.check_audio(audio, 44100, "vocals")
    assert any("clip" in w for w in report.warnings)


def test_detects_sample_rate_mismatch():
    bad = PreFlightValidator.check_sample_rate(6000, "vocals")
    assert bad.passed is False
    good = PreFlightValidator.check_sample_rate(44100, "vocals")
    assert good.passed is True


def test_detects_extreme_duration():
    sr = 8000
    n = int(35 * 60 * sr)
    audio = np.full((n, 2), 0.1, dtype=np.float32)
    report = PreFlightValidator.check_audio(audio, sr, "vocals")
    assert any("chunk" in w for w in report.warnings)


def test_detects_single_sample():
    audio = _stereo(n=10)
    report = PreFlightValidator.check_audio(audio, 44100, "vocals")
    assert report.passed is False
    assert any("256" in i for i in report.issues)


def test_detects_multi_channel():
    audio = np.zeros((4410, 6), dtype=np.float32)
    audio[:, :] = 0.1
    report = PreFlightValidator.check_audio(audio, 44100, "vocals")
    assert any("canali" in w for w in report.warnings)


def test_integration_with_load_auto(tmp_path):
    sr = 44100
    vocals_path = os.path.join(tmp_path, "vocals.wav")
    instrumental_path = os.path.join(tmp_path, "instrumental.wav")
    sf.write(vocals_path, _stereo(), sr)
    sf.write(instrumental_path, _stereo(amp=0.4), sr)

    stems = load_auto(str(tmp_path))
    assert stems.sample_rate == sr
    assert len(stems.names()) == 2
