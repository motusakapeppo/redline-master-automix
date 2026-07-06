from redline.vocalstack import classify_register, LOW, UNISON, HIGH, FALSETTO, RECIPES


def test_classify_register_low_octave():
    assert classify_register(double_f0=110.0, lead_f0=220.0) == LOW


def test_classify_register_unison():
    assert classify_register(double_f0=215.0, lead_f0=220.0) == UNISON


def test_classify_register_high_harmony():
    assert classify_register(double_f0=330.0, lead_f0=220.0) == HIGH  # a fifth above


def test_classify_register_falsetto():
    # High pitch ratio + real HF energy -> genuine falsetto
    assert classify_register(double_f0=500.0, lead_f0=220.0, hf_ratio=0.12) == FALSETTO


def test_octave_error_falsetto_without_hf_energy_is_downranked():
    # A "falsetto" pitch ratio but almost no high-frequency energy is a
    # classic octave error — must NOT be routed to the falsetto bus.
    assert classify_register(double_f0=500.0, lead_f0=220.0, hf_ratio=0.01) == UNISON
    # a middling amount of HF energy lands it on "high" instead of falsetto
    assert classify_register(double_f0=500.0, lead_f0=220.0, hf_ratio=0.04) == HIGH


def test_high_harmony_without_hf_energy_is_downranked():
    assert classify_register(double_f0=330.0, lead_f0=220.0, hf_ratio=0.01) == UNISON


def test_no_hf_ratio_keeps_pitch_only_behavior():
    # Backward-compatible: without the spectral hint, classify on pitch alone.
    assert classify_register(double_f0=500.0, lead_f0=220.0) == FALSETTO


def test_classify_register_handles_silence_gracefully():
    assert classify_register(double_f0=0.0, lead_f0=220.0) == UNISON
    assert classify_register(double_f0=220.0, lead_f0=0.0) == UNISON


def test_all_registers_have_recipes():
    for register in (LOW, UNISON, HIGH, FALSETTO):
        assert register in RECIPES
        assert RECIPES[register].pan_magnitude > 0
