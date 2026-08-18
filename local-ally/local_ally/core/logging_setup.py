"""Logging-Konfiguration: Konsole plus rotierende Datei im Datenverzeichnis."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .paths import log_path

_CONFIGURED = False


def setup_logging(level: int = logging.INFO) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)-28s %(message)s")

    console = logging.StreamHandler()
    console.setFormatter(fmt)

    handlers: list[logging.Handler] = [console]
    try:
        file_handler = RotatingFileHandler(
            log_path(), maxBytes=1_000_000, backupCount=2, encoding="utf-8"
        )
        file_handler.setFormatter(fmt)
        handlers.append(file_handler)
    except OSError:  # z.B. schreibgeschuetztes Verzeichnis - dann nur Konsole
        pass

    root = logging.getLogger()
    root.setLevel(level)
    for handler in handlers:
        root.addHandler(handler)

    _CONFIGURED = True
