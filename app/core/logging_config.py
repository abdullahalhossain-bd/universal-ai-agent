"""
Structured logging.

Every log record is emitted as one JSON object per line — the shape
CloudWatch / Datadog / Loki / etc. expect, and the shape that lets you
`grep`/`jq` a single request's full trace out of a firehose of mixed
output from a dozen modules (chat, rate_limit, sync workers, ...).

Set LOG_JSON=false for plain-text output in local dev, where a human
is reading the terminal directly and JSON is just noise.
"""

import json
import logging
import sys
from datetime import datetime, timezone

from app.core.request_context import get_request_id


# Standard LogRecord attributes — anything else on the record was
# passed via `extra={...}` at the call site and should ride along
# as its own top-level JSON field (store_id, path, duration_ms, ...).
_STANDARD_RECORD_KEYS = {
    "name", "msg", "args", "levelname", "levelno", "pathname",
    "filename", "module", "exc_info", "exc_text", "stack_info",
    "lineno", "funcName", "created", "msecs", "relativeCreated",
    "thread", "threadName", "processName", "process", "message",
    "request_id", "taskName",
}


class RequestIdFilter(logging.Filter):
    """Attaches the current request's correlation ID to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        return True


class JsonFormatter(logging.Formatter):

    def format(self, record: logging.LogRecord) -> str:

        payload = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key in _STANDARD_RECORD_KEYS:
                continue
            try:
                json.dumps(value)
            except TypeError:
                value = str(value)
            payload[key] = value

        return json.dumps(payload, default=str)


def configure_logging(
    *,
    json_logs: bool = True,
    level: int = logging.INFO,
) -> None:
    """
    Call once at startup, before any other module-level `logger =
    logging.getLogger(...)` call emits anything. Replaces whatever
    handlers are on the root logger, so every existing
    `logging.getLogger("app.<module>")` call site across the codebase
    picks this up automatically — no per-module changes needed.
    """

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())

    if json_logs:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s "
                "[req=%(request_id)s]: %(message)s"
            )
        )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # uvicorn's own loggers install their own handlers by default;
    # route them through the same structured pipeline instead of
    # letting access logs print in a different, unparseable format.
    for noisy in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(noisy)
        uv_logger.handlers = []
        uv_logger.propagate = True
