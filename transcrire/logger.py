# ============================================================
# Transcrire — Structured Logging
# ============================================================
# In production (launched via Transcrire.cmd):
#   - TRANSCRIRE_APPDATA is set
#   - Logs are written to %APPDATA%\Transcrire\transcrire.log
#   - Nothing is printed to the terminal
#
# In development (VS Code, no env var):
#   - Logs are written to stdout
#   - JSON format for machine-readable output
#
# Usage in any module:
#   import logging
#   logger = logging.getLogger(__name__)
#   logger.info("Stage started", extra={"stage": "FETCH"})
#
# No print() calls in business logic — use logger instead.
# ============================================================

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


class JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level":     record.levelname,
            "logger":    record.name,
            "message":   record.getMessage(),
        }

        # Include any extra fields passed via extra= kwarg
        skip = {
            "name", "msg", "args", "levelname", "levelno",
            "pathname", "filename", "module", "exc_info",
            "exc_text", "stack_info", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread",
            "threadName", "processName", "process", "message",
            "taskName",
        }
        for key, value in record.__dict__.items():
            if key not in skip:
                log_obj[key] = value

        if record.exc_info:
            log_obj["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(log_obj, default=str)


def _resolve_log_path() -> Path | None:
    """
    Returns the log file path when running in production.
    Returns None when running in development (logs to stdout).
    """
    app_data = os.environ.get("TRANSCRIRE_APPDATA")
    if not app_data:
        return None
    return Path(app_data) / "transcrire.log"


def setup_logging(level: int = logging.INFO) -> None:
    """
    Configures the root logger.

    Production (TRANSCRIRE_APPDATA set):
      - Writes JSON logs to %APPDATA%\Transcrire\\transcrire.log
      - No terminal output

    Development (no env var):
      - Writes JSON logs to stdout

    Call once at application startup in cli/main.py.
    """
    log_path = _resolve_log_path()
    formatter = JsonFormatter()

    if log_path:
        # ---- Production: log to file only ----
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_path, encoding="utf-8")
    else:
        # ---- Development: log to stdout ----
        handler = logging.StreamHandler(sys.stdout)

    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)
