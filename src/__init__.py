"""Core package for professor research system."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from rich.logging import RichHandler

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "research.log"
THIRD_PARTY_LOG_FILE = LOG_DIR / "third_party.log"

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

# Configure root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)

if not root_logger.handlers:
    # Rich console handler - respects LOG_LEVEL env var
    console_level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
    rich_handler = RichHandler(
        rich_tracebacks=True,
        markup=True,
        show_path=False,
    )
    rich_handler.setLevel(console_level)
    rich_handler.setFormatter(
        logging.Formatter(LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
    )

    # Main file handler - DEBUG level for your code only
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter(LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
    )
    # Filter to only log messages from 'src.*' loggers and __main__
    file_handler.addFilter(
        lambda record: record.name.startswith("src.") or record.name == "__main__"
    )

    root_logger.addHandler(rich_handler)
    root_logger.addHandler(file_handler)

# Third-party logger configuration
third_party_handler = RotatingFileHandler(
    THIRD_PARTY_LOG_FILE,
    maxBytes=2 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)
third_party_handler.setLevel(logging.DEBUG)
third_party_handler.setFormatter(
    logging.Formatter(LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
)

# Add third-party handler to specific loggers
for logger_name in ["httpx", "httpcore", "openai", "crawl4ai", "google_genai"]:
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(third_party_handler)
    logger.propagate = False  # Don't propagate to root logger
