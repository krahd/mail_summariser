"""
modelito/exceptions.py

Unified exception hierarchy for LLM provider library.
"""

class LLMProviderError(Exception):
    """Base exception for all provider errors."""

class ModelNotFoundError(LLMProviderError):
    pass

class ProviderUnavailableError(LLMProviderError):
    pass

class ModelDownloadError(LLMProviderError):
    pass

class ConfigurationError(LLMProviderError):
    pass
