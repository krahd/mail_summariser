"""
modelito/utils.py

Shared utility functions for the LLM provider library.
"""

import os
import logging
from typing import Any

def mask_api_key(key: str) -> str:
    if not key or len(key) < 8:
        return "***"
    return key[:3] + "..." + key[-3:]

def get_env_setting(name: str, default: Any = None) -> Any:
    return os.getenv(name, default)

def setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter('[%(levelname)s] %(name)s: %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger
