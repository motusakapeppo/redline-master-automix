import numpy as np

from redline.masking import find_masking_cut


def _tone(freq, sr, seconds=2.0, amp=0.3):
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    mono = (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return np.stack([mono, mono], axis=1)


def test_recommends_cut_when_instrumental_clashes_with_vocal_presence():
    sr = 44100
    vocal = _tone(3000.0, sr, amp=0.3)  # vocal living squarely in the presence band
    synth = _tone(3200.0, sr, amp=0.3)  # instrumental also heavily in that band

    cut = find_masking_cut(synth, vocal, sr)
    assert cut is not None
    assert cut.gain_db < 0


def test_no_cut_when_instrumental_lives_elsewhere():
    sr = 44100
    vocal = _tone(3000.0, sr, amp=0.3)
    bass = _tone(80.0, sr, amp=0.3)  # instrumental energy is all down in the bass

    cut = find_masking_cut(bass, vocal, sr)
    assert cut is None


def test_no_cut_when_vocal_does_not_occupy_the_band():
    sr = 44100
    vocal = _tone(150.0, sr, amp=0.3)  # low, doesn't need the presence band
    synth = _tone(3200.0, sr, amp=0.3)

    cut = find_masking_cut(synth, vocal, sr)
    assert cut is None
