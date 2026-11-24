"""Allowlisted structured logging: callers cannot accidentally log a URL payload."""

import json
import logging
from datetime import datetime, timezone

ALLOWED = {"event", "count", "duration_ms", "status", "model_version", "batch_id"}


def event(logger, name, **fields):
    record = {"timestamp": datetime.now(timezone.utc).isoformat(), "event": name}
    record.update({k: v for k, v in fields.items() if k in ALLOWED})
    logger.info(json.dumps(record, sort_keys=True))


def configure():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    # Uvicorn access logging should also be disabled on its command line.
    logging.getLogger("uvicorn.access").disabled = True
