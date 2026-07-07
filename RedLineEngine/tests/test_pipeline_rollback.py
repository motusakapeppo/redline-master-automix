import numpy as np

from redline.pipeline_rollback import PipelineRollback


def test_guard_catches_exception():
    rb = PipelineRollback()
    audio_before = np.zeros(4)
    rb.snapshot("step1", audio_before)

    with rb.guard("step1", fallback_audio=audio_before):
        raise ValueError("boom")

    # exception was swallowed, pipeline can continue
    assert True


def test_guard_passes_through_success():
    rb = PipelineRollback()
    audio = np.ones(4)
    rb.snapshot("step1", audio)

    with rb.guard("step1"):
        pass  # success

    # snapshot still present since no rollback occurred
    state = rb.rollback()
    assert state is not None
    assert np.array_equal(state.audio, audio)


def test_snapshot_and_rollback():
    rb = PipelineRollback()
    audio = np.array([1.0, 2.0, 3.0])
    rb.snapshot("step1", audio, params={"gain": 1.0})

    state = rb.rollback()
    assert state.step_name == "step1"
    assert np.array_equal(state.audio, audio)
    assert state.params == {"gain": 1.0}


def test_nested_guards():
    rb = PipelineRollback()
    audio1 = np.array([1.0])
    audio2 = np.array([2.0])

    rb.snapshot("step1", audio1)
    with rb.guard("step1"):
        rb.snapshot("step2", audio2)
        with rb.guard("step2"):
            raise RuntimeError("inner fails")

    # inner snapshot was rolled back and popped, only step1 remains
    state = rb.rollback()
    assert state.step_name == "step1"
    assert np.array_equal(state.audio, audio1)


def test_rollback_without_snapshot():
    rb = PipelineRollback()
    assert rb.rollback() is None
