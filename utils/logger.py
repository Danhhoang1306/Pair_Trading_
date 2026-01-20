"""
Logging utilities
"""

import logging
import logging.config
from config import LOGGING_CONFIG


def setup_logging():
    """Setup logging configuration"""
    logging.config.dictConfig(LOGGING_CONFIG)
    logger = logging.getLogger(__name__)
    logger.info("Logging system initialized")


def get_logger(name: str) -> logging.Logger:
    """Get logger instance"""
    return logging.getLogger(name)
