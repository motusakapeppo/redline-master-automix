import time

import pytest

from redline.watchdog import WatchdogTimer, WatchdogTimeout


def test_guard_passes_fast_step():
    wd = WatchdogTimer(timeout_multiplier=5.0)
    with wd.guard("fast_step", audio_duration_sec=1.0):
        time.sleep(0.05)
    assert True


def test_guard_timeout_slow_step():
    wd = WatchdogTimer(timeout_multiplier=1.0)
    with pytest.raises(WatchdogTimeout):
        with wd.guard("slow_step", audio_duration_sec=0.1):
            # timeout = max(1.0*0.1, 5.0) is clamped to 5.0 minimum, so use
            # a custom multiplier scenario handled by test_custom_multiplier;
            # here just force a real overrun window via a short sleep loop.
            for _ in range(200):
                time.sleep(0.05)


def test_zero_duration_audio():
    wd = WatchdogTimer(timeout_multiplier=5.0)
    assert wd._compute_timeout(0.0) == 5.0


def test_custom_multiplier():
    wd = WatchdogTimer(timeout_multiplier=2.0)
    assert wd._compute_timeout(10.0) == 20.0
