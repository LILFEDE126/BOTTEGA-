#!/usr/bin/env python3
"""Logging applicativo: coda in memoria, scrittura su stdout in un thread proprio."""

import atexit
import json
import logging
import logging.handlers
import os
from queue import SimpleQueue
import sys
import time
from typing import Any

_FORMATI_VALIDI = frozenset({"text", "json"})

_CAMPI_RECORD_STANDARD = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
) | {"message", "asctime", "code"}


class _FiltroCodiceDefault(logging.Filter):
    """Garantisce che ogni LogRecord esponga sempre l'attributo 'code'."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "code"):
            record.code = "-"
        return True


def resolver_log_format(valore: Any = None) -> str:
    """Normalizza e mette in whitelist il formato di log ('text' o 'json') senza sollevare mai."""
    try:
        grezzo = valore
        if grezzo is None:
            grezzo = os.getenv("BOTTEGA_LOG_FORMAT") or os.getenv("JISO_LOG_FORMAT") or "text"
        normalizzato = str(grezzo).strip().lower()
        if normalizzato in _FORMATI_VALIDI:
            return normalizzato
    except (TypeError, ValueError, AttributeError, OSError):
        return "text"
    return "text"


class FormatterJSON(logging.Formatter):
    """Emette un oggetto JSON per riga con 7 chiavi fisse in UTC e promuove gli extra a primo livello."""

    def format(self, record: logging.LogRecord) -> str:
        self.converter = time.gmtime
        base: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "code": getattr(record, "code", "-"),
            "logger": record.name,
            "process": record.process,
            "thread": record.thread,
            "msg": record.getMessage(),
        }
        for chiave, valore in record.__dict__.items():
            if chiave not in _CAMPI_RECORD_STANDARD and not chiave.startswith("_"):
                base.setdefault(chiave, valore)
        if record.exc_info:
            base["exc"] = self.formatException(record.exc_info)
        elif record.exc_text:
            base["exc"] = record.exc_text
        return json.dumps(base, ensure_ascii=False, default=str)


def _ferma_listener_sicuro(listener: logging.handlers.QueueListener | None) -> None:
    """Arresta il QueueListener in modo idempotente solo se il thread e' ancora attivo."""
    if listener is not None and getattr(listener, "_thread", None) is not None:
        try:
            listener.stop()
        except (OSError, RuntimeError, ValueError):
            pass


def configura_logger(nome: str = "bottega") -> logging.Logger:
    """Il logger applicativo non scrive: mette in coda."""
    logger = logging.getLogger(nome)
    if (
        len(logger.handlers) == 1
        and isinstance(logger.handlers[0], logging.handlers.QueueHandler)
    ):
        return logger

    listener_precedente = getattr(logger, "_queue_listener", None)
    _ferma_listener_sicuro(listener_precedente)

    logger.handlers.clear()
    logger.setLevel(logging.INFO)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.addFilter(_FiltroCodiceDefault())

    formato = resolver_log_format()
    if formato == "json":
        fmt_json = FormatterJSON()
        fmt_json.converter = time.gmtime
        stream_handler.setFormatter(fmt_json)
    else:
        fmt_text = logging.Formatter(
            "%(asctime)sZ [%(levelname)s] [%(code)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        fmt_text.converter = time.gmtime
        stream_handler.setFormatter(fmt_text)

    coda: SimpleQueue[logging.LogRecord] = SimpleQueue()
    queue_handler = logging.handlers.QueueHandler(coda)
    queue_handler.addFilter(_FiltroCodiceDefault())

    listener = logging.handlers.QueueListener(
        coda, stream_handler, respect_handler_level=True
    )
    listener.start()
    atexit.register(_ferma_listener_sicuro, listener)
    setattr(logger, "_queue_listener", listener)

    logger.addHandler(queue_handler)
    logger.propagate = False
    return logger


setup_logging = configura_logger
log = configura_logger()


def log_exception(messaggio: str, code: str = "GEN_ERR_001", *args: Any) -> None:
    """Registra un errore con stack trace completo e codice evento come secondo argomento posizionale."""
    log.error(messaggio, *args, exc_info=True, extra={"code": code})
