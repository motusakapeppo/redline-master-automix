from redline.director_safety import validate_classification, clamp_params
from redline.llm_classifier import BUS_CATEGORIES


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
