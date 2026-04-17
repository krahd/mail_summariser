"""
modelito.base

Abstract base classes and interfaces for LLM provider implementations.
Supports both synchronous and asynchronous operation.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

# Base exception for all provider errors (moved to exceptions.py)


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers (sync interface).
    """
    @abstractmethod
    def summarize(self, messages: List[Dict[str, Any]], settings: Optional[Dict[str, Any]] = None) -> str:
        ...

    @abstractmethod
    def list_models(self) -> List[str]:
        ...

    @abstractmethod
    def download_model(self, model_name: str) -> str:
        ...

    @abstractmethod
    def get_model_status(self, model_name: str) -> Dict[str, Any]:
        ...

    @abstractmethod
    def start(self) -> str:
        ...

    @abstractmethod
    def stop(self) -> str:
        ...

    @abstractmethod
    def get_runtime_status(self) -> Dict[str, Any]:
        ...


class AsyncLLMProvider(ABC):
    """
    Abstract base class for LLM providers (async interface).
    """
    @abstractmethod
    async def summarize(self, messages: List[Dict[str, Any]], settings: Optional[Dict[str, Any]] = None) -> str:
        ...

    @abstractmethod
    async def list_models(self) -> List[str]:
        ...

    @abstractmethod
    async def download_model(self, model_name: str) -> str:
        ...

    @abstractmethod
    async def get_model_status(self, model_name: str) -> Dict[str, Any]:
        ...

    @abstractmethod
    async def start(self) -> str:
        ...

    @abstractmethod
    async def stop(self) -> str:
        ...

    @abstractmethod
    async def get_runtime_status(self) -> Dict[str, Any]:
        ...
