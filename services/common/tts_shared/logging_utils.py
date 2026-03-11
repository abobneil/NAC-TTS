from __future__ import annotations

from datetime import datetime, UTC
import json
import logging
import sys


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(getattr(record, "fields", {}))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_json_logging(service_name: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
    root_logger.propagate = False

    logging.getLogger(service_name).info("logging-configured", extra={"fields": {"service": service_name, "event": "logging_configured"}})


def log_event(logger: logging.Logger, event: str, **fields) -> None:
    logger.info(event, extra={"fields": {"event": event, **fields}})
