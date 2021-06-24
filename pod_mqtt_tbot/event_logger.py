"""
Create logger to handle events.
Important messages and errors are recorded in the corresponding logs.
Other messages are printed to the console
 """
import logging
import sys
from config import get_full_path

FORMATTER = logging.Formatter("%(asctime)s — %(name)s — %(levelname)s — %(message)s")
SHORT_FORMATTER = logging.Formatter("%(levelname)s — %(message)s")
EVENT_LOG_FILE = get_full_path("logs/events.log")
ERROR_LOG_FILE = get_full_path("logs/error.log")


def _get_debug_handler():
    """Messages are printed to console"""
    console_handler = logging.StreamHandler(stream=sys.stdout)
    console_handler.setFormatter(SHORT_FORMATTER)
    console_handler.setLevel(logging.DEBUG)
    return console_handler


def _get_event_handler():
    """Event messages are written to file"""
    file_handler = logging.FileHandler(filename=EVENT_LOG_FILE)
    file_handler.setFormatter(FORMATTER)
    file_handler.setLevel(logging.INFO)
    return file_handler


def _get_error_handler():
    """Error messages are written to file"""
    file_handler = logging.FileHandler(filename=ERROR_LOG_FILE)
    file_handler.setFormatter(FORMATTER)
    file_handler.setLevel(logging.ERROR)
    return file_handler


def get_logger(logger_name):
    """Create logger"""
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(_get_debug_handler())
    logger.addHandler(_get_event_handler())
    logger.addHandler(_get_error_handler())
    return logger
