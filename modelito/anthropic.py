"""
modelito/anthropic.py

Anthropic provider implementation for the LLM provider library.
Supports both synchronous and asynchronous operation.
"""

from typing import Any, Dict, List, Optional

import json
from urllib.request import Request, urlopen


from .base import LLMProvider, AsyncLLMProvider
from .exceptions import LLMProviderError
from .utils import get_env_setting, setup_logger

_logger = setup_logger("modelito.anthropic")

class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or get_env_setting("ANTHROPIC_API_KEY")
        self.endpoint = "https://api.anthropic.com/v1/messages"
        self.default_model = "claude-3-5-haiku-latest"

    def summarize(self, messages: List[Dict[str, Any]], settings: Optional[Dict[str, Any]] = None) -> str:
        model = (settings or {}).get("modelName", self.default_model)
        system_message = (settings or {}).get("anthropicSystemMessage", "")
        # prompt = self._build_prompt(messages, settings)  # Unused variable
        payload = {
            "model": model,
            "system": system_message,
            "messages": [
                *[{"role": m.get("role", "user"), "content": m.get("content", "")}
                  for m in messages],
            ],
            "max_tokens": 1024,
        }
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        try:
            resp = self._post_json(self.endpoint, payload, headers, timeout=45.0)
            content = resp.get("content", "")
            if not content:
                raise LLMProviderError(f"Empty Anthropic response: {resp}")
            return content.strip()
        except Exception as exc:
            raise LLMProviderError(f"Anthropic summarize failed: {exc}") from exc

    def list_models(self) -> List[str]:
        # Hardcoded for now; can be extended to fetch from Anthropic API
        return ["claude-3-5-haiku-latest", "claude-3-5-sonnet-latest", "claude-3-7-sonnet-latest"]

    def download_model(self, model_name: str) -> str:
        raise NotImplementedError("Model download not supported for Anthropic.")

    def get_model_status(self, model_name: str) -> Dict[str, Any]:
        return {"available": model_name in self.list_models()}

    def start(self) -> str:
        return "No start required for Anthropic."

    def stop(self) -> str:
        return "No stop required for Anthropic."

    def get_runtime_status(self) -> Dict[str, Any]:
        return {"available": True}

    def _post_json(self, url: str, payload: dict, headers: dict, timeout: float = 15.0) -> dict:
        body = json.dumps(payload).encode("utf-8")
        req = Request(url=url, data=body, headers=headers, method="POST")
        with urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            if not raw.strip():
                return {}
            return json.loads(raw)

    def _build_prompt(self, messages: List[Dict[str, Any]], _settings: Optional[Dict[str, Any]]) -> str:
        # _settings argument is unused but kept for interface compatibility
        _ = _settings  # explicitly ignore unused argument
        return "\n".join(m.get("content", "") for m in messages)

# Async implementation stub (to be completed)
class AsyncAnthropicProvider(AsyncLLMProvider):
    async def summarize(self, messages: List[Dict[str, Any]], settings: Optional[Dict[str, Any]] = None) -> str:
        raise NotImplementedError("Async Anthropic not yet implemented")
    async def list_models(self) -> List[str]:
        raise NotImplementedError("Async Anthropic not yet implemented")
    async def download_model(self, model_name: str) -> str:
        raise NotImplementedError("Async Anthropic not yet implemented")
    async def get_model_status(self, model_name: str) -> Dict[str, Any]:
        raise NotImplementedError("Async Anthropic not yet implemented")
    async def start(self) -> str:
        raise NotImplementedError("Async Anthropic not yet implemented")
    async def stop(self) -> str:
        raise NotImplementedError("Async Anthropic not yet implemented")
    async def get_runtime_status(self) -> Dict[str, Any]:
        raise NotImplementedError("Async Anthropic not yet implemented")
