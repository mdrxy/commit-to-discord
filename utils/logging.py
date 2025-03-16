"""
Logging module.
"""

import logging
import os
from datetime import datetime, timezone

import pytz
from colorlog import ColoredFormatter

log_level = os.getenv("LOG_LEVEL", "info").upper()


def configure_logging(logger_name="commit_to_discord"):
    """
    Set up logging with colorized output and timestamps in Eastern Time.
    """
    logger = logging.getLogger(logger_name)
    if logger.hasHandlers():
        # Avoid re-adding handlers if the logger is already configured
        return logger

    logger.setLevel(getattr(logging, log_level, logging.INFO))

    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level, logging.INFO))

    class EasternTimeFormatter(ColoredFormatter):
        """Custom log formatter to display timestamps in Eastern Time
        with colorized output"""

        def formatTime(self, record, datefmt=None):
            # Convert UTC to Eastern Time
            eastern = pytz.timezone("America/New_York")
            utc_dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
            eastern_dt = utc_dt.astimezone(eastern)
            # Use ISO 8601 format
            return eastern_dt.isoformat()

    # Define the formatter with color and PID
    formatter = EasternTimeFormatter(
        "%(log_color)s%(asctime)s - PID %(process)d - %(name)s - %(levelname)s - %(message)s",
        log_colors={
            "DEBUG": "white",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "bold_red",
        },
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Also configure the Werkzeug logger
    werkzeug_logger = logging.getLogger("werkzeug")
    if not werkzeug_logger.hasHandlers():  # Avoid duplicates
        werkzeug_logger.setLevel(logging.INFO)
        werkzeug_logger.addHandler(console_handler)

    return logger
