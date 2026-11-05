#!/usr/bin/env python3
"""Layer 0 (THE): Structured UTC ISO-8601 logging with unique event codes and zero internal dependencies."""

import json
import logging
import os
import sys
import time
from typing import Any


class _FiltroCodiceDefault(logging.Filter):
    """Ensures every LogRecord always carries the 'code' attribute."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "code"):
            record.code = "-"
        return True


class FormatterJSON(logging.Formatter):
    """Formats log records as single-line JSON objects with UTC ISO-8601 timestamps."""

    converter = time.gmtime

    def format(self, record: logging.LogRecord) -> str:
        base: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "code": getattr(record, "code", "-"),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            base["exc"] = self.formatException(record.exc_info)
        return json.dumps(base, ensure_ascii=False, default=str)


def configura_logger(nome: str = "bottega") -> logging.Logger:
    """Configures a stdout logger in UTC ('text' or 'json' via BOTTEGA_LOG_FORMAT)."""
    logger = logging.getLogger(nome)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_FiltroCodiceDefault())

    formato = (os.getenv("BOTTEGA_LOG_FORMAT") or "text").strip().lower()
    if formato == "json":
        handler.setFormatter(FormatterJSON())
    else:
        fmt = logging.Formatter(
            "%(asctime)sZ [%(levelname)s] [%(code)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        fmt.converter = time.gmtime
        handler.setFormatter(fmt)

    logger.addHandler(handler)
    logger.propagate = False
    return logger


log = configura_logger()


def log_exception(messaggio: str, code: str = "GEN_ERR_001", *args: Any) -> None:
    """Logs an error with full stack trace and explicit diagnostic event code."""
    log.error(messaggio, *args, exc_info=True, extra={"code": code})