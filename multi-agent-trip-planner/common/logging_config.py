"""Shared logging configuration used by every process of the use case.

Each process (the orchestrator and the three specialist agents) calls
`setup_logging(...)` with its own file name. Logs go simultaneously to:

- the console (to follow the A2A discovery and delegation moments in real time),
  and
- a file under logs/ (for later inspection).

The level is taken from the LOG_LEVEL environment variable (default INFO).
"""

import logging
import os
from pathlib import Path

# logs/ lives at the case root (one level up from common/)
_LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


def setup_logging(log_file: str, logger_name: str) -> logging.Logger:
    """Configure and return a logger that writes to the console and logs/<log_file>.

    Args:
        log_file: file name inside logs/ (e.g. "orchestrator.log").
        logger_name: logger name (e.g. "orchestrator").

    Returns:
        The configured logger.
    """
    _LOGS_DIR.mkdir(parents=True, exist_ok=True)

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    formatter = logging.Formatter(_FORMAT)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(_LOGS_DIR / log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)

    logger = logging.getLogger(logger_name)
    logger.setLevel(level)
    # Avoid duplicate handlers if setup_logging is called more than once.
    if not logger.handlers:
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)
    logger.propagate = False

    return logger
