import logging
from typing import Optional

from src.config.settings import settings, BASE_DIR


def setup_logging(
    log_level: Optional[str] = None,
    save_to_file: Optional[bool] = None,
    log_file: Optional[str] = None,
) -> None:
    """
    Setup basic logging configuration

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        save_to_file: Whether to save logs to file
        log_file: Path to log file (if save_to_file is True)
    """
    # Get settings from environment or use defaults
    if log_level is None:
        log_level = getattr(settings, "LOG_LEVEL", "INFO")

    if save_to_file is None:
        save_to_file = getattr(settings, "LOG_SAVE_TO_FILE", False)

    if log_file is None:
        log_file = getattr(settings, "LOG_FILE", "src/logs/app.log")

    # Convert log level string to logging constant
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Create logs directory if it doesn't exist
    if save_to_file:
        # Convert to absolute path relative to project root
        log_path = BASE_DIR / log_file
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = str(log_path)  # Update log_file to absolute path

    # Configure logging
    handlers = []

    # Console handler (always enabled)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(console_formatter)
    handlers.append(console_handler)

    # File handler (if enabled)
    if save_to_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(file_formatter)
        handlers.append(file_handler)

    # Configure root logger
    logging.basicConfig(
        level=level,
        handlers=handlers,
        force=True,  # Override any existing handlers
    )

    # Set specific log levels for noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured. Level: {log_level}, Save to file: {save_to_file}")
    if save_to_file:
        logger.info(f"Log file: {log_file}")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the specified name

    Args:
        name: Logger name (usually __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


# Auto-setup logging on import if enabled
auto_setup = getattr(settings, "LOG_AUTO_SETUP", True)
if auto_setup:
    setup_logging()
