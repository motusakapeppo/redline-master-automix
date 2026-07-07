from redline.director_safety import validate_classification, clamp_params, validate_dsp_automation
from redline.llm_classifier import BUS_CATEGORIES

_STRUCTURE = [{"name": "chorus_1", "start": 30.0, "end": 60.0}]
_SUGGESTION = {
    "target_section": "chorus_1",
    "dsp_updates": {"eq_adjustments": [{"type": "bell", "freq": 3000, "gain_db": 2.0}]},
}


def test_validate_classification_keeps_valid_entries():
    suggestion = {"track_07": BUS_CATEGORIES[0], "track_08": BUS_CATEGORIES[1]}
    result = validate_classification(suggestion)
    assert result == suggestion


def test_validate_classification_drops_hallucinated_category():
    suggestion = {"track_07": "Spaceship Bus", "track_08": BUS_CATEGORIES[0]}
    result = validate_classification(suggestion)
    assert result == {"track_08": BUS_CATEGORIES[0]}


def test_validate_classification_drops_names_outside_allowed_set():
    # Observed in practice: the model echoing a literal "categoria" key
    # instead of the real stem name it was asked about.
    suggestion = {"categoria": BUS_CATEGORIES[0]}
    result = validate_classification(suggestion, allowed_names={"track_07"})
    assert result == {}


def test_clamp_params_clamps_out_of_range_gain():
    clamped, corrections = clamp_params({"gain_db": 15.0})
    assert clamped["gain_db"] == 12.0
    assert len(corrections) == 1


def test_clamp_params_drops_unknown_param():
    clamped, corrections = clamp_params({"totally_made_up_param": 5.0})
    assert clamped == {}
    assert "sconosciuto" in corrections[0]


def test_clamp_params_leaves_in_range_values_untouched():
    clamped, corrections = clamp_params({"pan": 0.3, "compressor_ratio": 4.0})
    assert clamped == {"pan": 0.3, "compressor_ratio": 4.0}
    assert corrections == []


def test_clamp_params_clamps_creative_brief_knobs():
    # These are the 3 wizard-facing knobs interpret_creative_brief() is
    # allowed to nudge -- an over-eager LLM interpretation ("make it sound
    # like a monster") must never push them past what the wizard's own
    # sliders already allow.
    clamped, corrections = clamp_params({"aggressiveness": 9, "warmth": 5.0, "vocal_prominence": -3.0})
    assert clamped == {"aggressiveness": 5.0, "warmth": 1.0, "vocal_prominence": -1.0}
    assert len(corrections) == 3


def test_validate_dsp_automation_accepts_literal_acoustic_term():
    result = validate_dsp_automation(_SUGGESTION, _STRUCTURE, 180.0, user_text="nel ritornello vorrei più presenza")
    assert result is not None


def test_validate_dsp_automation_accepts_color_metaphor():
    # Same color vocabulary Module 1 (interpret_creative_brief) already
    # treats as a real request -- Module 2 must not reject it just because
    # it landed in the section-scoped feature instead.
    result = validate_dsp_automation(_SUGGESTION, _STRUCTURE, 180.0, user_text="rendi il ritornello più dorato")
    assert result is not None


def test_validate_dsp_automation_rejects_untranslatable_metaphor():
    result = validate_dsp_automation(
        _SUGGESTION, _STRUCTURE, 180.0,
        user_text="fai suonare la voce come un elefante che vola nello spazio",
    )
    assert result is None


def test_validate_dsp_automation_rejects_unrelated_text():
    result = validate_dsp_automation(_SUGGESTION, _STRUCTURE, 180.0, user_text="che tempo fa oggi a Milano?")
    assert result is None
