"""Session history: a persisted log of past renders (timestamp, input,
output folder, key results) so the user can see what they've done across
app restarts, instead of every run being a one-off with nothing kept once
the window closes. Presets already persist mix *parameters*; this persists
render *outcomes* -- the two are complementary, neither replaces the other.

Stored as a single JSON file in ~/.redline/sessions.json (append-only list,
capped at _MAX_ENTRIES so the file can't grow unbounded over months of use).
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path

log = logging.getLogger(__name__)

_MAX_ENTRIES = 200


def _sessions_path() -> Path:
    d = Path.home() / ".redline"
    d.mkdir(parents=True, exist_ok=True)
    return d / "sessions.json"


class SessionHistory:
    """Append-only log of past renders."""

    @staticmethod
    def add(record: dict) -> dict:
        """Append a new session record (timestamp + id added automatically)
        and return it. Never raises -- a history-write failure must not take
        down a render that already succeeded."""
        entry = {
            "id": uuid.uuid4().hex[:12],
            "timestamp": time.time(),
            **record,
        }
        try:
            path = _sessions_path()
            entries = SessionHistory._read_all(path)
            entries.append(entry)
            if len(entries) > _MAX_ENTRIES:
                entries = entries[-_MAX_ENTRIES:]
            path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError as exc:
            log.error("Impossibile salvare la cronologia sessione: %s", exc)
        return entry

    @staticmethod
    def list() -> list[dict]:
        """Return all sessions, most recent first."""
        entries = SessionHistory._read_all(_sessions_path())
        return sorted(entries, key=lambda e: e.get("timestamp", 0), reverse=True)

    @staticmethod
    def get(session_id: str) -> dict | None:
        for entry in SessionHistory._read_all(_sessions_path()):
            if entry.get("id") == session_id:
                return entry
        return None

    @staticmethod
    def _read_all(path: Path) -> list[dict]:
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError) as exc:
            log.error("Errore leggendo la cronologia sessione: %s", exc)
            return []
