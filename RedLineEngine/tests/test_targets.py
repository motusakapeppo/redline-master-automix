import json
import os

from redline.targets import genre_slug, target_path, load_measured_target
from redline.qc import resolve_target, TARGET_BAND_RATIOS


def test_genre_slug_is_filesystem_safe():
    assert genre_slug("EDM / Urban") == "edm_urban"
    assert genre_slug("Pop / Rock") == "pop_rock"


def test_load_measured_target_missing_returns_none():
    assert load_measured_target("Some Genre Nobody Profiled") is None


def test_load_measured_target_reads_valid_json(tmp_path, monkeypatch):
    import redline.targets as targets_mod

    monkeypatch.setattr(targets_mod, "TARGETS_DIR", str(tmp_path))
    path = os.path.join(str(tmp_path), "target_test_genre.json")
    with open(path, "w") as f:
        json.dump({"band_ratios": {"sub_bass": 0.3, "bass": 0.2}}, f)

    result = targets_mod.load_measured_target("Test Genre")
    assert result == {"sub_bass": 0.3, "bass": 0.2}


def test_resolve_target_falls_back_to_builtin_when_unmeasured():
    target = resolve_target("Pop / Rock")
    assert target == TARGET_BAND_RATIOS["Pop / Rock"]


def test_resolve_target_falls_back_to_balanced_for_unknown_genre():
    target = resolve_target("Some Made Up Genre")
    assert target == TARGET_BAND_RATIOS["Balanced"]
