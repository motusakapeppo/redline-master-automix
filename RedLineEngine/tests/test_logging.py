"""Tests for structured logging setup — setup_logging, JSON format, rotation,
and verification that no bare `except ...: pass` remains in the codebase.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile

import pytest

from redline.logging_setup import JsonFormatter, get_logger, setup_logging


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_logging():
    """Remove all handlers from the root logger so tests are isolated."""
    root = logging.getLogger()
    for h in list(root.handlers):
        h.close()
        root.removeHandler(h)
    # Re-import to reset the _initialized flag
    import importlib
    import redline.logging_setup as ls
    importlib.reload(ls)


@pytest.fixture
def tmp_log_dir():
    """Yield a temp dir for log files, ensuring handlers are closed before cleanup."""
    tmp = tempfile.mkdtemp()
    log_dir = os.path.join(tmp, "logs")
    try:
        yield log_dir
    finally:
        # Close all file handlers before cleaning up (Windows file lock)
        root = logging.getLogger()
        for h in list(root.handlers):
            h.close()
            root.removeHandler(h)
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------


def test_setup_logging_console_only():
    """With log_dir=None, only a console handler is added (no file handler)."""
    _reset_logging()
    setup_logging(log_dir=None, level="DEBUG")
    root = logging.getLogger()
    handler_types = [type(h).__name__ for h in root.handlers]
    assert "StreamHandler" in handler_types
    assert "RotatingFileHandler" not in handler_types


def test_setup_logging_creates_log_dir(tmp_log_dir):
    """With log_dir set, the directory is created and a file handler added."""
    _reset_logging()
    setup_logging(log_dir=tmp_log_dir, level="DEBUG")
    assert os.path.isdir(tmp_log_dir)
    root = logging.getLogger()
    assert any(
        type(h).__name__ == "RotatingFileHandler" for h in root.handlers
    )


def test_setup_logging_writes_log_file(tmp_log_dir):
    """A log message actually lands in the file."""
    _reset_logging()
    setup_logging(log_dir=tmp_log_dir, level="DEBUG")
    logger = get_logger("test_writes")
    logger.info("hello world")
    # Close handlers so the file is released on Windows
    root = logging.getLogger()
    for h in list(root.handlers):
        h.close()
    log_path = os.path.join(tmp_log_dir, "redline.log")
    assert os.path.exists(log_path)
    with open(log_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "hello world" in content


def test_setup_logging_idempotent(tmp_log_dir):
    """Calling setup_logging twice does not add duplicate handlers."""
    _reset_logging()
    setup_logging(log_dir=tmp_log_dir, level="DEBUG")
    n_handlers = len(logging.getLogger().handlers)
    setup_logging(log_dir=tmp_log_dir, level="DEBUG")
    assert len(logging.getLogger().handlers) == n_handlers


# ---------------------------------------------------------------------------
# JSON format
# ---------------------------------------------------------------------------


def test_json_format_is_valid(tmp_log_dir):
    """Each log line written to the file is valid JSON."""
    _reset_logging()
    setup_logging(log_dir=tmp_log_dir, level="DEBUG")
    logger = get_logger("test_json")
    logger.info("info msg")
    logger.warning("warn msg")
    logger.error("error msg")

    root = logging.getLogger()
    for h in list(root.handlers):
        h.close()

    log_path = os.path.join(tmp_log_dir, "redline.log")
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)  # raises on invalid JSON
            assert "timestamp" in obj
            assert "level" in obj
            assert "logger" in obj
            assert "message" in obj


def test_json_format_required_fields(tmp_log_dir):
    """Every JSON record has timestamp, level, logger, message."""
    _reset_logging()
    setup_logging(log_dir=tmp_log_dir, level="DEBUG")
    logger = get_logger("test_fields")
    logger.info("check fields")

    root = logging.getLogger()
    for h in list(root.handlers):
        h.close()

    log_path = os.path.join(tmp_log_dir, "redline.log")
    with open(log_path, "r", encoding="utf-8") as f:
        obj = json.loads(f.readline().strip())

    assert "timestamp" in obj
    assert "level" in obj
    assert "logger" in obj
    assert "message" in obj
    assert obj["level"] == "INFO"
    assert obj["logger"] == "test_fields"
    assert obj["message"] == "check fields"


def test_json_format_exception(tmp_log_dir):
    """When exc_info=True, the JSON record includes an exception field."""
    _reset_logging()
    setup_logging(log_dir=tmp_log_dir, level="DEBUG")
    logger = get_logger("test_exc")
    try:
        raise ValueError("boom")
    except ValueError:
        logger.warning("caught something", exc_info=True)

    root = logging.getLogger()
    for h in list(root.handlers):
        h.close()

    log_path = os.path.join(tmp_log_dir, "redline.log")
    with open(log_path, "r", encoding="utf-8") as f:
        obj = json.loads(f.readline().strip())

    assert "exception" in obj
    assert obj["exception"]["type"] == "ValueError"
    assert "boom" in obj["exception"]["value"]
    assert "Traceback" in obj["exception"]["traceback"]


def test_json_formatter_direct():
    """Unit-test the JsonFormatter class directly."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test.direct",
        level=logging.WARNING,
        pathname=__file__,
        lineno=42,
        msg="direct test",
        args=(),
        exc_info=None,
    )
    output = formatter.format(record)
    obj = json.loads(output)
    assert obj["logger"] == "test.direct"
    assert obj["level"] == "WARNING"
    assert obj["message"] == "direct test"
    assert obj["module"] == "test_logging"


# ---------------------------------------------------------------------------
# Rotation
# ---------------------------------------------------------------------------


def test_rotation_works(tmp_log_dir):
    """When the log file exceeds maxBytes, it rotates (creates .1, .2, ...)."""
    _reset_logging()
    import logging.handlers
    from redline.logging_setup import JsonFormatter

    os.makedirs(tmp_log_dir, exist_ok=True)
    log_path = os.path.join(tmp_log_dir, "redline.log")

    handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=200, backupCount=3, encoding="utf-8",
    )
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)

    logger = logging.getLogger("test_rotation")
    # Write enough to trigger at least one rotation
    for i in range(50):
        logger.warning("message number %d", i)

    handler.close()
    root.removeHandler(handler)

    # Should have the main log + at least one backup
    files = os.listdir(tmp_log_dir)
    log_files = [f for f in files if f.startswith("redline.log")]
    assert len(log_files) >= 2, f"Expected at least 2 log files, got {log_files}"


# ---------------------------------------------------------------------------
# No bare except:pass in the codebase
# ---------------------------------------------------------------------------


def test_no_bare_except_pass():
    """No file under redline/ contains 'except ...:' followed by 'pass'
    (the pattern we set out to eliminate)."""
    redline_dir = os.path.join(os.path.dirname(__file__), "..", "redline")
    pattern = re.compile(r"except\s+\w+\s*:\s*\n\s*pass")
    found = []
    for root, _dirs, files in os.walk(redline_dir):
        for fname in files:
            if not fname.endswith(".py"):
                continue
            path = os.path.join(root, fname)
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            if pattern.search(content):
                found.append(path)
    assert not found, f"Files still containing bare except:pass: {found}"

