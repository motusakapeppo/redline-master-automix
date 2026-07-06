"""Director Mode: pauses the mix pipeline at a checkpoint and waits for a
human to approve before continuing, instead of trusting the naming/Z-axis
heuristics blind all the way through. A threading.Event is the actual gate:
render_mix runs on a worker thread (see app/api.py), the GUI thread stays
fully responsive at 60fps while the gate is closed, and approving from the
GUI is just setting the event from the other thread."""

from __future__ import annotations

import threading
from typing import Callable

EventCallback = Callable[[dict], None]


class DirectorGate:
    """One instance per running pipeline. Reusable across multiple
    checkpoints in the same render -- each call to request_approval()
    clears the event first, so an earlier approval can't accidentally
    skip a later checkpoint."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def request_approval(self, checkpoint: str, payload: dict, on_event: EventCallback, timeout: float | None = None) -> bool:
        """Blocks the calling (pipeline) thread until approve() is called
        from elsewhere (the GUI thread), or `timeout` seconds elapse.
        Returns True if approved, False if it timed out -- callers should
        treat a timeout as "proceed anyway" (never lock up the render
        forever over a user who stepped away, especially with no timeout
        set for automated/headless callers)."""
        self._event.clear()
        on_event({"type": "director_checkpoint", "checkpoint": checkpoint, **payload})
        return self._event.wait(timeout=timeout)

    def approve(self) -> None:
        """Called from the GUI thread (app/api.py) when the user confirms
        the current checkpoint -- unblocks whichever request_approval()
        call is currently waiting."""
        self._event.set()
