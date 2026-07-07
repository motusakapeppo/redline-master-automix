"""Automatic rollback for pipeline steps: snapshots the audio state before
each step and, if the step raises, restores the last-known-good state and
lets the pipeline continue instead of aborting the whole render."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from redline.logging_setup import get_logger

logger = get_logger(__name__)

StepCallback = Callable[[str], None]


@dataclass
class PipelineState:
    step_name: str
    audio: np.ndarray | None
    params: dict = field(default_factory=dict)


class PipelineRollback:
    def __init__(self, on_step: StepCallback | None = None) -> None:
        self._on_step = on_step or (lambda _msg: None)
        self._stack: list[PipelineState] = []

    def snapshot(self, step_name: str, audio: np.ndarray | None, params: dict | None = None) -> None:
        self._stack.append(PipelineState(step_name=step_name, audio=audio, params=params or {}))

    def rollback(self) -> PipelineState | None:
        if not self._stack:
            return None
        return self._stack.pop()

    @contextmanager
    def guard(self, step_name: str, fallback_audio: np.ndarray | None = None):
        try:
            yield
        except Exception as exc:
            message = f"Rollback: passo '{step_name}' fallito ({exc}), ripristino stato precedente"
            logger.warning(message, exc_info=True)
            self._on_step(message)
            self.rollback()
