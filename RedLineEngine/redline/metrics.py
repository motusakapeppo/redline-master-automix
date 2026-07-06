"""In-memory timing logger: records how long each named stage takes so a
slow render can be diagnosed ("[METRIC] denoise: 8.7s") instead of guessed
at — this is exactly how the 11-minute analysis regression earlier this
session got found and fixed, formalized as a reusable tool instead of an
ad-hoc timing script."""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field


@dataclass
class Metrics:
    records: list[tuple[str, float]] = field(default_factory=list)

    @contextmanager
    def stage(self, name: str, on_step=None):
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - start
            self.records.append((name, elapsed))
            if on_step is not None:
                on_step(f"[METRIC] {name}: {elapsed:.2f}s")

    def total_seconds(self) -> float:
        return sum(seconds for _, seconds in self.records)

    def as_dict(self) -> dict[str, float]:
        return {name: seconds for name, seconds in self.records}

    def slowest(self, n: int = 5) -> list[tuple[str, float]]:
        return sorted(self.records, key=lambda r: r[1], reverse=True)[:n]
