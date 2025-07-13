"""Logging module."""

import logging
import os
from datetime import datetime

import pytz
from colorlog import ColoredFormatter

log_level = os.getenv("LOG_LEVEL", "info").upper()
log_tz_name = os.getenv("LOG_TZ", "UTC")
try:
    log_tz = pytz.timezone(log_tz_name)
except pytz.UnknownTimeZoneError:
    logger = logging.getLogger("commit_to_discord")
    logger.warning("Unknown timezone `%s`, defaulting to `UTC`.", log_tz_name)
    log_tz = pytz.utc

LOG_COLORS = {
    "DEBUG": "white",
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "bold_red",
}


def configure_logging(logger_name: str = "commit_to_discord") -> logging.Logger:
    """Set up logging with colorized output and a configurable timezone."""
    logger = logging.getLogger(logger_name)
    if logger.hasHandlers():
        # Avoid re-adding handlers if the logger is already configured
        return logger

    logger.setLevel(getattr(logging, log_level, logging.INFO))

    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level, logging.INFO))

    class TimezoneFormatter(
        ColoredFormatter,
    ):
        """Custom log formatter to display timestamps in a specific timezone.

        Uses colorized output.
        """

        def format_time(self, record: logging.LogRecord) -> str:
            """Convert record time to the configured timezone."""
            utc_dt = datetime.fromtimestamp(record.created, tz=pytz.utc)
            local_dt = utc_dt.astimezone(log_tz)
            # Use ISO 8601 format
            return local_dt.isoformat()

    # Define the formatter with color and PID
    formatter = TimezoneFormatter(
        "%(log_color)s%(asctime)s - PID %(process)d - %(name)s - %(levelname)s - "
        "%(message)s",
        log_colors=LOG_COLORS,
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Also configure the Werkzeug logger
    werkzeug_logger = logging.getLogger("werkzeug")
    if not werkzeug_logger.hasHandlers():  # Avoid duplicates
        werkzeug_logger.setLevel(logging.INFO)
        werkzeug_logger.addHandler(console_handler)

    return logger
