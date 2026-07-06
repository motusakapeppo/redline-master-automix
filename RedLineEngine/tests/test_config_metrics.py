import json
import os

from redline import config
from redline.metrics import Metrics


def test_all_flags_off_by_default(monkeypatch, tmp_path):
    # Isolated from the real .flags.json -- a machine that ran the CI
    # auto-enable script (ci_check.py) would otherwise have every flag set
    # to true locally, which tests the CI script's behavior, not the code's
    # actual default. This checks config.DEFAULTS itself.
    monkeypatch.setattr(config, "_FLAGS_PATH", str(tmp_path / "nonexistent.flags.json"))
    config.reload()
    for flag in config.DEFAULTS:
        assert config.is_enabled(flag) is False
    config.reload()  # leave global state clean for other tests


def test_env_var_override(monkeypatch):
    monkeypatch.setenv("REDLINE_ENABLE_LTAS_MATCHING", "1")
    config.reload()
    assert config.is_enabled("ENABLE_LTAS_MATCHING") is True
    config.reload()  # leave global state clean for other tests


def test_metrics_records_stage_timing():
    m = Metrics()
    with m.stage("fake_stage"):
        pass
    assert len(m.records) == 1
    assert m.records[0][0] == "fake_stage"
    assert m.records[0][1] >= 0.0


def test_metrics_slowest_orders_correctly():
    m = Metrics()
    m.records = [("a", 1.0), ("b", 5.0), ("c", 2.0)]
    assert [name for name, _ in m.slowest(2)] == ["b", "c"]
