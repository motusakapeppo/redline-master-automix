import numpy as np

from redline.alignment import find_sample_delay, apply_sample_delay, align_to_reference


def test_find_sample_delay_recovers_known_shift():
    sr = 44100
    n = sr * 2
    rng = np.random.default_rng(3)
    reference = rng.standard_normal(n).astype(np.float32) * 0.2

    true_delay = int(0.03 * sr)  # 30ms
    shifted = apply_sample_delay(reference, true_delay)

    found = find_sample_delay(reference, shifted, sr)
    # shifted lags reference by true_delay, so the correction to bring it
    # back into alignment is the negative of that; analysis runs on a
    # downsampled copy, so allow a small tolerance
    assert abs(found - (-true_delay)) < sr * 0.005  # within 5ms


def test_align_to_reference_improves_correlation():
    sr = 44100
    n = sr * 2
    rng = np.random.default_rng(4)
    reference = rng.standard_normal(n).astype(np.float32) * 0.2
    shifted = apply_sample_delay(reference, int(0.02 * sr))

    aligned, delay = align_to_reference(shifted, reference, sr)

    corr_before = np.corrcoef(reference[1000:-1000], shifted[1000:-1000])[0, 1]
    corr_after = np.corrcoef(reference[1000:-1000], aligned[1000:-1000])[0, 1]
    assert corr_after > corr_before
