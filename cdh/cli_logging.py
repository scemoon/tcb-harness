from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


LOG_DIR = Path.home() / ".cdh" / "logs"
LOG_FILE = LOG_DIR / "cdh.log"
LOG_BACKUP_COUNT = 7

_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    level = log_level.upper()
    if level not in _VALID_LOG_LEVELS:
        level = "INFO"
    numeric_level = getattr(logging, level)

    handler = TimedRotatingFileHandler(
        LOG_FILE,
        when="midnight",
        interval=1,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
        utc=False,
    )
    handler.suffix = "%Y-%m-%d"
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    )

    root = logging.getLogger()
    root.setLevel(numeric_level)
    for h in list(root.handlers):
        if isinstance(h, TimedRotatingFileHandler) and getattr(h, "baseFilename", "") == str(LOG_FILE):
            root.removeHandler(h)
    root.addHandler(handler)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    return root
