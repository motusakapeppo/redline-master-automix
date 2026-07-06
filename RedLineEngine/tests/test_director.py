import threading
import time

from redline.director import DirectorGate


def test_request_approval_blocks_until_approve_called():
    gate = DirectorGate()
    events = []
    order = []

    def worker():
        order.append("waiting")
        approved = gate.request_approval("test_checkpoint", {"foo": "bar"}, events.append)
        order.append("resumed" if approved else "timed_out")

    t = threading.Thread(target=worker)
    t.start()
    time.sleep(0.1)
    assert order == ["waiting"]  # still blocked

    gate.approve()
    t.join(timeout=2)
    assert order == ["waiting", "resumed"]
    assert events[0]["type"] == "director_checkpoint"
    assert events[0]["checkpoint"] == "test_checkpoint"
    assert events[0]["foo"] == "bar"


def test_request_approval_times_out_if_never_approved():
    gate = DirectorGate()
    approved = gate.request_approval("test_checkpoint", {}, lambda evt: None, timeout=0.2)
    assert approved is False


def test_gate_is_reusable_across_checkpoints():
    gate = DirectorGate()
    gate.approve()
    # A stale approval from a previous checkpoint must not leak into the next one.
    approved = gate.request_approval("second_checkpoint", {}, lambda evt: None, timeout=0.2)
    assert approved is False
