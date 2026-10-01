"""Tests for the flag-gated result cache on classify_ambiguous_stems.

The cache is purely an optimization: with ENABLE_LLM_RESULT_CACHE off the
function must behave exactly as before (one decode per call); with it on, an
identical second call must return the memoized dict without decoding again.
The model itself is never loaded here -- _get_model is monkeypatched to a
fake exposing create_chat_completion, so these tests are fast and offline.
"""

import json

import pytest

from redline import config
from redline import llm_classifier


class _FakeModel:
    def __init__(self, payload):
        self.calls = 0
        self._payload = payload

    def create_chat_completion(self, **kwargs):
        self.calls += 1
        return {"choices": [{"message": {"content": json.dumps(self._payload)}}]}


STEMS = [
    {"name": "track_07", "spectral_hint": "medio", "transient_hint": "percussivo"},
    {"name": "track_08", "spectral_hint": "basso", "transient_hint": "sostenuto"},
]


@pytest.fixture(autouse=True)
def _clean_cache_and_flag():
    llm_classifier._result_cache.clear()
    config.set_override("ENABLE_LLM_RESULT_CACHE", False)
    yield
    llm_classifier._result_cache.clear()
    config.set_override("ENABLE_LLM_RESULT_CACHE", False)


def _install_fake_model(monkeypatch, payload):
    fake = _FakeModel(payload)
    monkeypatch.setattr(llm_classifier, "_get_model", lambda: fake)
    return fake


def test_flag_off_does_not_use_cache(monkeypatch):
    fake = _install_fake_model(monkeypatch, {"track_07": "Drum Bus"})
    config.set_override("ENABLE_LLM_RESULT_CACHE", False)

    first = llm_classifier.classify_ambiguous_stems(STEMS)
    second = llm_classifier.classify_ambiguous_stems(STEMS)

    assert fake.calls == 2  # cache unused: one decode per call
    assert first == second


def test_flag_on_caches_identical_calls(monkeypatch):
    fake = _install_fake_model(monkeypatch, {"track_07": "Drum Bus"})
    config.set_override("ENABLE_LLM_RESULT_CACHE", True)

    first = llm_classifier.classify_ambiguous_stems(STEMS)
    second = llm_classifier.classify_ambiguous_stems(STEMS)

    assert fake.calls == 1  # second call served from cache, no decode
    assert second == first


def test_cache_miss_on_different_input(monkeypatch):
    fake = _install_fake_model(monkeypatch, {"track_07": "Drum Bus"})
    config.set_override("ENABLE_LLM_RESULT_CACHE", True)

    first = llm_classifier.classify_ambiguous_stems(STEMS)
    other = [{"name": "track_09", "spectral_hint": "alto", "transient_hint": "sostenuto"}]
    second = llm_classifier.classify_ambiguous_stems(other)

    assert fake.calls == 2  # different inputs => cache miss
    assert first == second  # same fake payload, equal result


def test_cache_miss_when_hint_changes(monkeypatch):
    fake = _install_fake_model(monkeypatch, {"track_07": "Drum Bus"})
    config.set_override("ENABLE_LLM_RESULT_CACHE", True)

    llm_classifier.classify_ambiguous_stems(STEMS)
    changed = [dict(STEMS[0], spectral_hint="alto"), STEMS[1]]
    llm_classifier.classify_ambiguous_stems(changed)

    assert fake.calls == 2


def test_cache_is_fail_safe_when_flag_lookup_raises(monkeypatch):
    fake = _install_fake_model(monkeypatch, {"track_07": "Drum Bus"})

    def _boom(_flag):
        raise RuntimeError("flag backend exploded")

    monkeypatch.setattr(config, "is_enabled", _boom)

    # Must never raise; falls back to the uncached path.
    result = llm_classifier.classify_ambiguous_stems(STEMS)
    assert result == {"track_07": "Drum Bus"}
    assert fake.calls == 1
