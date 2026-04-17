"""
modelito/__init__.py

Provider registry and main API entry points.
"""

from .anthropic import AnthropicProvider
from .openai import OpenAIProvider
from .ollama import OllamaProvider
from .base import LLMProvider, AsyncLLMProvider
from .exceptions import *
from .translation import translate_text
from .scheduler import manager as scheduler

# Provider registry for extensibility
PROVIDER_REGISTRY = {}


def register_provider(name: str, provider_cls):
    PROVIDER_REGISTRY[name.lower()] = provider_cls


def get_provider(name: str, **kwargs):
    cls = PROVIDER_REGISTRY.get(name.lower())
    if not cls:
        raise LLMProviderError(f"Provider '{name}' not registered.")
    return cls(**kwargs)


# Register built-in providers
register_provider("ollama", OllamaProvider)
register_provider("openai", OpenAIProvider)
register_provider("anthropic", AnthropicProvider)
