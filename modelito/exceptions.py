"""
modelito/exceptions.py

Unified exception hierarchy for LLM provider library.
"""

class LLMProviderError(Exception):
    """Base exception for all provider errors."""


class ModelNotFoundError(LLMProviderError):
    """Raised when a model cannot be located by the provider."""


class ProviderUnavailableError(LLMProviderError):
    """Raised when a provider cannot be reached or used."""


class ModelDownloadError(LLMProviderError):
    """Raised when a model download/pull request fails."""


class ConfigurationError(LLMProviderError):
    """Raised when configuration is invalid or missing for a provider."""


class LLMTimeoutError(LLMProviderError):
    """Raised when a provider call times out or is considered too slow."""
