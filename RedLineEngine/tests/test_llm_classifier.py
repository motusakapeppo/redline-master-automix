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


def test_interpret_creative_brief_neutral_text_yields_no_changes():
    # Confirmed in practice against the real model: a small 1.5B model
    # reliably invents "courtesy" adjustments even when the user explicitly
    # says nothing needs to change. This is the case the keyword-relevance
    # gate (_BRIEF_RELEVANCE_KEYWORDS) exists to catch.
    if is_available():
        result = interpret_creative_brief("niente di che, va bene così")
        assert result == {}


def test_interpret_creative_brief_only_returns_keys_the_text_actually_mentions():
    if is_available():
        result = interpret_creative_brief("vorrei un suono più caldo, quasi da vinile")
        assert set(result.keys()) <= {"warmth"}
        if "warmth" in result:
            assert result["warmth"] > 0  # warm, not cold


def test_interpret_creative_brief_gets_vocal_prominence_sign_right():
    if is_available():
        result = interpret_creative_brief("la voce deve stare più indietro, meno protagonista")
        assert set(result.keys()) <= {"vocal_prominence"}
        if "vocal_prominence" in result:
            assert result["vocal_prominence"] < 0  # "indietro" = less prominent = negative


def test_interpret_creative_brief_handles_color_and_element_metaphors():
    # Real, if unusual, mixing requests -- producers do talk like this.
    # Rejecting them outright would be wrong; the fix was a small
    # documented color->knob mapping (_COLOR_TO_KNOB_HINTS) injected into
    # the prompt, not a keyword blocklist.
    if is_available():
        fire = interpret_creative_brief("incendia il brano")
        assert set(fire.keys()) <= {"aggressiveness"}
        if "aggressiveness" in fire:
            assert fire["aggressiveness"] > 3  # "fire" reads as more aggressive, not less

        purple = interpret_creative_brief("lo voglio più viola")
        assert set(purple.keys()) <= {"warmth"}

        icy = interpret_creative_brief("voglio che sia più blu, freddo e metallico")
        assert set(icy.keys()) <= {"warmth"}
        if "warmth" in icy:
            assert icy["warmth"] < 0  # cold/metallic reads as less warm, not more

        dreamy = interpret_creative_brief("rendilo eterei e sognante")
        assert set(dreamy.keys()) <= {"aggressiveness"}
        if "aggressiveness" in dreamy:
            assert dreamy["aggressiveness"] < 3  # dreamy/ethereal reads as gentler, not harder
