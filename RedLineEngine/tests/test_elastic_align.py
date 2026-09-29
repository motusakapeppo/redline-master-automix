import numpy as np

from redline.elastic_align import elastic_align, MAX_SAFE_WARP_FRACTION


def _click_track(sr, seconds, click_times, freq=1000.0, click_dur=0.02, amp=0.4):
    n = int(sr * seconds)
    signal = np.zeros(n, dtype=np.float32)
    for ct in click_times:
        start = int(ct * sr)
        dur_samples = int(click_dur * sr)
        end = min(start + dur_samples, n)
        if start >= n:
            continue
        t = np.linspace(0, click_dur, end - start, endpoint=False)
        signal[start:end] += (amp * np.sin(2 * np.pi * freq * t) * np.hanning(end - start)).astype(np.float32)
    return signal


def test_returns_original_length_and_shape():
    sr = 22050
    seconds = 6.0
    lead_clicks = [1.0, 2.0, 3.0, 4.0, 5.0]
    double_clicks = [1.05, 2.05, 3.05, 4.05, 5.05]  # consistently ~50ms late, small/safe drift

    lead = _click_track(sr, seconds, lead_clicks)
    double = _click_track(sr, seconds, double_clicks)
    stereo_double = np.stack([double, double], axis=1)
    stereo_lead = np.stack([lead, lead], axis=1)

    result = elastic_align(stereo_double, stereo_lead, sr)
    assert result.audio.shape == stereo_double.shape
    assert result.windows_total > 0


def test_grossly_mistimed_take_is_mostly_skipped_not_warped():
    # A double that's wildly different in timing from the lead (not a real
    # match) must trigger the safety net, not get aggressively time-stretched.
    sr = 22050
    seconds = 6.0
    lead_clicks = [1.0, 2.0, 3.0, 4.0, 5.0]
    double_clicks = [1.8, 2.2, 4.5, 4.6, 5.9]  # erratic, not a plausible same-phrase take

    lead = _click_track(sr, seconds, lead_clicks)
    double = _click_track(sr, seconds, double_clicks)
    stereo_double = np.stack([double, double], axis=1)
    stereo_lead = np.stack([lead, lead], axis=1)

    result = elastic_align(stereo_double, stereo_lead, sr)
    if result.windows_total > 0:
        skip_ratio = result.windows_skipped_unsafe / result.windows_total
        assert skip_ratio > 0.3  # a meaningful chunk must be refused, not force-warped


def test_short_signal_is_noop():
    sr = 22050
    short = np.zeros((int(sr * 0.5), 2), dtype=np.float32)
    result = elastic_align(short, short, sr)
    assert result.windows_total == 0
    assert np.array_equal(result.audio, short)


def test_time_stretch_failure_is_caught_and_segment_preserved(monkeypatch):
    # Regression test: the except handler around librosa.effects.time_stretch
    # used to log an undefined variable (`w`), so a time-stretch failure
    # raised NameError from inside the handler instead of degrading
    # gracefully. Force the failure and assert the window is left as-is.
    import redline.elastic_align as ea

    sr = 22050
    seconds = 6.0
    t = np.arange(int(sr * seconds), dtype=np.float32) / sr
    # Continuous tone (no silent windows) so every window is eligible for
    # stretching; identical lead/double => safe ~1.0 ratio => the stretch
    # branch is actually entered and the forced failure is hit.
    tone = (0.3 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)
    stereo_double = np.stack([tone, tone], axis=1)
    stereo_lead = np.stack([tone, tone], axis=1)

    # Baseline: a time_stretch that returns the segment unchanged. The
    # failure path must produce byte-identical output to this no-op stretch.
    monkeypatch.setattr(ea.librosa.effects, "time_stretch", lambda seg, rate: seg)
    baseline = elastic_align(stereo_double, stereo_lead, sr)

    def _boom(*args, **kwargs):
        raise RuntimeError("forced time_stretch failure")

    monkeypatch.setattr(ea.librosa.effects, "time_stretch", _boom)

    # Must not propagate the RuntimeError (nor a NameError from the handler).
    result = elastic_align(stereo_double, stereo_lead, sr)

    assert result.audio.shape == stereo_double.shape
    assert result.windows_total > 0
    # Every window failed to stretch, so nothing was actually warped and the
    # signal must come back exactly as the no-op-stretch baseline.
    assert result.windows_stretched == 0
    assert np.array_equal(result.audio, baseline.audio)


def test_transients_survive_window_boundaries():
    # Regression test: the old non-overlapping-window implementation used
    # only the *rising* half of a Hann window as its "fade" (0 -> ~1, never
    # back down), so a transient landing near a ~0.4s window boundary could
    # be attenuated well below its original amplitude -- confirmed in
    # practice via a full-pipeline click-track test where only 6 of 11
    # clicks in a double vocal survived above a 50%-of-peak threshold.
    # Proper overlap-add (50% overlap, full Hann, coverage-normalized) must
    # preserve every click's amplitude regardless of where it falls.
    sr = 22050
    seconds = 8.0
    click_times = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]

    lead = _click_track(sr, seconds, click_times, amp=0.5)
    # Small, consistently-safe timing offset so most windows are eligible
    # to be stretched (exercising the windowing path this test targets).
    double = _click_track(sr, seconds, [c + 0.01 for c in click_times], amp=0.5)
    stereo_double = np.stack([double, double], axis=1)
    stereo_lead = np.stack([lead, lead], axis=1)

    result = elastic_align(stereo_double, stereo_lead, sr)
    out = result.audio[:, 0]

    original_peak = float(np.max(np.abs(double)))
    for ct in click_times:
        center = int(ct * sr)
        window = out[max(0, center - 500): center + 1000]
        assert np.max(np.abs(window)) > 0.5 * original_peak, f"click at {ct}s was attenuated below 50% of its original amplitude"
