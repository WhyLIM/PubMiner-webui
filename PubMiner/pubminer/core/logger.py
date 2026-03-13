"""Structured logging configuration for PubMiner."""

import logging
import sys
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.logging import RichHandler


# Global console instance
_console: Optional[Console] = None
_logger: Optional[logging.Logger] = None


def setup_logger(
    level: str = "INFO",
    log_file: Optional[str] = None,
    rich_output: bool = True,
) -> logging.Logger:
    """
    Setup the global logger.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional log file path
        rich_output: Use rich formatting for console output

    Returns:
        Configured logger instance
    """
    global _logger, _console

    _logger = logging.getLogger("pubminer")
    _logger.setLevel(getattr(logging, level.upper()))

    # Clear existing handlers
    _logger.handlers.clear()

    # Console handler
    if rich_output:
        _console = Console(stderr=True)
        console_handler = RichHandler(
            console=_console,
            show_time=True,
            show_path=False,
            rich_tracebacks=True,
            markup=True,
        )
        console_handler.setFormatter(logging.Formatter("%(message)s"))
    else:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(
            logging.Formatter(
                "[%(asctime)s] %(levelname)s - %(name)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    _logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter(
                "[%(asctime)s] %(levelname)s - %(name)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        _logger.addHandler(file_handler)

    return _logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Get a logger instance.

    Args:
        name: Optional sub-logger name

    Returns:
        Logger instance
    """
    global _logger

    if _logger is None:
        _logger = setup_logger()

    if name:
        return _logger.getChild(name)

    return _logger


def get_console() -> Console:
    """Get the global console instance."""
    global _console

    if _console is None:
        _console = Console(stderr=True)

    return _console
