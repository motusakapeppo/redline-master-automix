from redline.llm_classifier import interpret_creative_brief, is_available


def test_interpret_creative_brief_returns_empty_for_blank_text():
    assert interpret_creative_brief("") == {}
    assert interpret_creative_brief("   ") == {}


def test_interpret_creative_brief_returns_empty_when_model_unavailable():
    # In this test environment llama-cpp-python/the model may or may not be
    # installed -- either way, a real brief must never raise, and if the
    # model genuinely isn't available it must return {} so the caller falls
    # back to the wizard's own slider values.
    if not is_available():
        assert interpret_creative_brief("un suono più caldo, per favore") == {}
