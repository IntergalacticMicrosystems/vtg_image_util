"""
Logging configuration for the Victor 9000 Disk Image Utility.

Provides configurable logging with support for verbose and quiet modes.
"""

import logging
import sys
from typing import TextIO

# Log levels for the application
QUIET = logging.WARNING
NORMAL = logging.INFO
VERBOSE = logging.DEBUG

# Create a custom logger for the application
logger = logging.getLogger('vtg_image_util')


class ColorFormatter(logging.Formatter):
    """
    Custom formatter that adds colors for terminal output.

    Falls back to plain text if colors are not supported.
    """

    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
        'RESET': '\033[0m',
    }

    def __init__(self, fmt: str | None = None, use_colors: bool = True):
        super().__init__(fmt)
        self.use_colors = use_colors and self._supports_color()

    def _supports_color(self) -> bool:
        """Check if the terminal supports color."""
        # Windows requires special handling
        if sys.platform == 'win32':
            try:
                import os
                return os.isatty(sys.stderr.fileno()) and 'TERM' in os.environ
            except Exception:
                return False
        return hasattr(sys.stderr, 'isatty') and sys.stderr.isatty()

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with optional colors."""
        message = super().format(record)

        if self.use_colors and record.levelname in self.COLORS:
            color = self.COLORS[record.levelname]
            reset = self.COLORS['RESET']
            return f"{color}{message}{reset}"

        return message


def setup_logging(
    level: int = NORMAL,
    stream: TextIO | None = None,
    use_colors: bool = True,
    format_string: str | None = None
) -> None:
    """
    Configure logging for the application.

    Args:
        level: Logging level (QUIET, NORMAL, or VERBOSE)
        stream: Output stream (defaults to stderr)
        use_colors: Whether to use colored output
        format_string: Custom format string (optional)
    """
    if stream is None:
        stream = sys.stderr

    if format_string is None:
        if level <= logging.DEBUG:
            # Verbose mode: include more details
            format_string = '%(levelname)s: %(name)s: %(message)s'
        else:
            # Normal/quiet mode: just the message
            format_string = '%(message)s'

    # Remove existing handlers
    logger.handlers.clear()

    # Create handler
    handler = logging.StreamHandler(stream)
    handler.setFormatter(ColorFormatter(format_string, use_colors))

    # Configure logger
    logger.addHandler(handler)
    logger.setLevel(level)

    # Don't propagate to root logger
    logger.propagate = False


def set_level(level: int) -> None:
    """
    Change the logging level.

    Args:
        level: New logging level
    """
    logger.setLevel(level)


def get_logger(name: str | None = None) -> logging.Logger:
    """
    Get a logger for a specific module.

    Args:
        name: Module name (optional, uses package logger if not specified)

    Returns:
        Logger instance
    """
    if name is None:
        return logger
    return logger.getChild(name)


# Convenience functions for common log messages
def debug(message: str, *args, **kwargs) -> None:
    """Log a debug message (only shown in verbose mode)."""
    logger.debug(message, *args, **kwargs)


def info(message: str, *args, **kwargs) -> None:
    """Log an info message (shown in normal and verbose modes)."""
    logger.info(message, *args, **kwargs)


def warning(message: str, *args, **kwargs) -> None:
    """Log a warning message (always shown)."""
    logger.warning(message, *args, **kwargs)


def error(message: str, *args, **kwargs) -> None:
    """Log an error message (always shown)."""
    logger.error(message, *args, **kwargs)


# Initialize with default settings
setup_logging()
