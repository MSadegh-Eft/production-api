"""
Monitoring & Structured Logging
Production-grade metrics collection and JSON logging.
"""

import logging
import json
import time
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable


# === Structured JSON Logger ===

class JSONFormatter(logging.Formatter):
    """Format log records as JSON for log aggregation (ELK, Datadog, etc.)."""

    def format(self, record):
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
        }
        # Merge any extra data attached to the record
        if hasattr(record, "extra_data"):
            log_obj.update(record.extra_data)
        return json.dumps(log_obj)
    
def get_logger(name: str = "production-api") -> logging.Logger:
    """Create a structured JSON logger."""
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    return logger
    