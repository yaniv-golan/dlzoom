"""
Logging configuration for dlzoom
"""

import logging
import sys


def setup_logging(level: str = "INFO", verbose: bool = False) -> None:
    """
    Configure logging for the application

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        verbose: Enable verbose logging (DEBUG level)
    """
    # Use DEBUG if verbose flag is set
    if verbose:
        level = "DEBUG"

    # Convert string to logging level
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Configure root logger
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stderr)],
    )

    # Reduce noise from requests library
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
