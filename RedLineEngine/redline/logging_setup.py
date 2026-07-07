"""Structured logging with console + rotating JSON file handlers.

Usage:
    from redline.logging_setup import get_logger

    logger = get_logger(__name__)
    logger.warning("something happened", exc_info=True)
    logger.exception("unexpected failure")
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
import traceback
from datetime import datetime, timezone
from typing import Any

_LOG_DIR_DEFAULT = None  # None = console-only
_LOG_LEVEL_DEFAULT = "WARNING"

_initialized = False


class JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects.

    Fields: timestamp (ISO-8601 UTC), level, logger, message, module,
    function, line, and exception (if present).
    """

    def format(self, record: logging.LogRecord) -> str:
        obj: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info and record.exc_info[0] is not None:
            obj["exception"] = {
                "type": record.exc_info[0].__name__,
                "value": str(record.exc_info[1]),
                "traceback": "".join(
                    traceback.format_exception(*record.exc_info)
                ).rstrip(),
            }
        return json.dumps(obj, ensure_ascii=False, default=str)


def setup_logging(
    log_dir: str | None = _LOG_DIR_DEFAULT,
    level: str = _LOG_LEVEL_DEFAULT,
) -> None:
    """Configure the root logger with console + optional rotating JSON file.

    Args:
        log_dir: Directory for log files. If None, only console logging is
            configured. Created automatically if it does not exist.
        level: One of "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL".
    """
    global _initialized
    if _initialized:
        return  # idempotent — only configure once

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.WARNING))

    # --- Console handler (human-readable text) ---
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.WARNING)
    console.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    root.addHandler(console)

    # --- Rotating JSON file handler ---
    if log_dir is not None:
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "redline.log")
        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(getattr(logging, level.upper(), logging.WARNING))
        file_handler.setFormatter(JsonFormatter())
        root.addHandler(file_handler)

    _initialized = True


def get_logger(name: str) -> logging.Logger:
    """Convenience: returns a child logger of the given *name*.

    Typical usage::

        logger = get_logger(__name__)
    """
    return logging.getLogger(name)
