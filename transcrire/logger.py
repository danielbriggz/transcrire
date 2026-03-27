# ============================================================
# Transcrire — Structured Logging
# ============================================================
# Configures Python's logging module with a JSON formatter
# for machine-readable, field-debuggable output.
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
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level":     record.levelname,
            "logger":    record.name,
            "message":   record.getMessage(),
        }

        # Include any extra fields passed via the extra= kwarg
        for key, value in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "levelname", "levelno",
                "pathname", "filename", "module", "exc_info",
                "exc_text", "stack_info", "lineno", "funcName",
                "created", "msecs", "relativeCreated", "thread",
                "threadName", "processName", "process", "message",
                "taskName",
            }:
                log_obj[key] = value

        if record.exc_info:
            log_obj["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(log_obj, default=str)


def setup_logging(level: int = logging.INFO) -> None:
    """
    Configures the root logger with a JSON formatter.
    Call once at application startup in cli/main.py.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)
