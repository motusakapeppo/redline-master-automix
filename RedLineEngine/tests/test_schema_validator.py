from redline.schema_validator import SchemaValidator, PRESET_SCHEMA


def _full_valid_preset():
    return {
        "aggressiveness": 3,
        "warmth": 0.0,
        "vocal_prominence": 0.0,
        "genre_override": None,
        "do_mastering": True,
        "platform": "auto",
        "stereo_width": 0.0,
        "transient_attack": 0.0,
        "transient_sustain": 0.0,
    }


def test_valid_preset_passes():
    result = SchemaValidator.validate_preset(_full_valid_preset(), PRESET_SCHEMA)
    assert result.valid is True
    assert result.errors == []


def test_missing_field_gets_default():
    data = _full_valid_preset()
    del data["aggressiveness"]
    result = SchemaValidator.validate_preset(data, PRESET_SCHEMA)
    assert result.valid is True
    assert result.fixed["aggressiveness"] == 3


def test_out_of_range_clamped():
    data = _full_valid_preset()
    data["aggressiveness"] = 10
    result = SchemaValidator.validate_preset(data, PRESET_SCHEMA)
    assert result.valid is True
    assert result.fixed["aggressiveness"] == 5


def test_invalid_type_rejected():
    data = _full_valid_preset()
    data["do_mastering"] = "yes"
    result = SchemaValidator.validate_preset(data, PRESET_SCHEMA)
    assert result.valid is False
    assert any("do_mastering" in e for e in result.errors)


def test_unknown_field_ignored():
    data = _full_valid_preset()
    data["not_a_real_field"] = 42
    result = SchemaValidator.validate_preset(data, PRESET_SCHEMA)
    assert result.valid is True
    assert "not_a_real_field" not in result.fixed


def test_apply_defaults_merges_correctly():
    data = {"aggressiveness": 5}
    merged = SchemaValidator.apply_defaults(data, PRESET_SCHEMA)
    assert merged["aggressiveness"] == 5
    assert merged["warmth"] == 0.0
    assert merged["platform"] == "auto"
