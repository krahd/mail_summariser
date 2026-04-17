"""
modelito/anthropic.py

Anthropic provider implementation for the LLM provider library.
Supports both synchronous and asynchronous operation.
"""

from typing import Any, Dict, List, Optional

import json
import asyncio
from urllib.request import Request, urlopen
from urllib.error import URLError


from .base import LLMProvider, AsyncLLMProvider
from .exceptions import LLMProviderError
from .utils import get_env_setting, setup_logger, mask_api_key, RateLimiter

_logger = setup_logger("modelito.anthropic")

class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or get_env_setting("ANTHROPIC_API_KEY")
        self.endpoint = "https://api.anthropic.com/v1/messages"
        self.default_model = "claude-3-5-haiku-latest"
        try:
            rl = int(get_env_setting("MODELITO_RATE_LIMIT", 60))
        except (ValueError, TypeError):
            rl = 60
        self.rate_limiter = RateLimiter(max_calls=rl, period=60.0)

    def summarize(self, messages: List[Dict[str, Any]], settings: Optional[Dict[str, Any]] = None) -> str:
        model = (settings or {}).get("modelName", self.default_model)
        system_message = (settings or {}).get("anthropicSystemMessage", "")
        messages_payload = self._build_messages_payload(messages, (settings or {}).get("prompt"), system_message)

        payload = {"model": model, "system": system_message, "messages": messages_payload, "max_tokens": 1024}
        api_key = (settings or {}).get("apiKey") or self.api_key
        headers = {"x-api-key": api_key, "Content-Type": "application/json"}
        _logger.debug("Anthropic request model=%s api_key=%s", model, mask_api_key(api_key))
        try:
            self.rate_limiter.acquire()
            resp = self._call_post_json(self.endpoint, payload, headers,
                                        timeout=45.0, settings=settings)
            content = resp.get("content", "")
            if not content:
                raise LLMProviderError(f"Empty Anthropic response: {resp}")
            # Support multiple response shapes: string or list of text blocks
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                # find first textual element
                for item in content:
                    if isinstance(item, dict) and "text" in item:
                        return str(item.get("text", "")).strip()
                # fallback: concatenate any text fields
                parts = [str(item.get("text", ""))
                         for item in content if isinstance(item, dict) and item.get("text")]
                joined = "".join(parts).strip()
                if joined:
                    return joined
                raise LLMProviderError(f"Anthropic returned unexpected content shape: {resp}")
        except (OSError, URLError, json.JSONDecodeError) as exc:
            raise LLMProviderError(f"Anthropic summarize failed: {exc}") from exc

    def _build_messages_payload(self, messages: List[Dict[str, Any]], provided_prompt: Optional[str], system_message: str) -> List[Dict[str, Any]]:
        if provided_prompt:
            return [{"role": "system", "content": system_message}, {"role": "user", "content": provided_prompt}]
        return [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]

    def _call_post_json(self, url: str, payload: dict, headers: dict, timeout: float = 15.0, settings: Optional[Dict[str, Any]] = None) -> dict:
        hook = (settings or {}).get("_post_json")
        if callable(hook):
            return hook(url, payload)
        return self._post_json(url, payload, headers, timeout)

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
    def __init__(self, api_key: Optional[str] = None):
        self._sync = AnthropicProvider(api_key=api_key)

    async def summarize(self, messages: List[Dict[str, Any]], settings: Optional[Dict[str, Any]] = None) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync.summarize, messages, settings)

    async def list_models(self) -> List[str]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync.list_models)

    async def download_model(self, model_name: str) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync.download_model, model_name)

    async def get_model_status(self, model_name: str) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync.get_model_status, model_name)

    async def start(self) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync.start)

    async def stop(self) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync.stop)

    async def get_runtime_status(self) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync.get_runtime_status)
