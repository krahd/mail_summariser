"""
modelito/openai.py

OpenAI provider implementation for the LLM provider library.
Supports both synchronous and asynchronous operation.
"""


import json
import asyncio
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

from .base import LLMProvider, AsyncLLMProvider
from .exceptions import LLMProviderError
from .utils import get_env_setting, setup_logger, mask_api_key, RateLimiter

_logger = setup_logger("modelito.openai")

class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or get_env_setting("OPENAI_API_KEY")
        self.endpoint = "https://api.openai.com/v1/chat/completions"
        self.default_model = "gpt-4.1"
        # Per-instance rate limiter (calls per minute)
        try:
            rl = int(get_env_setting("MODELITO_RATE_LIMIT", 60))
        except (ValueError, TypeError):
            rl = 60
        self.rate_limiter = RateLimiter(max_calls=rl, period=60.0)

    def summarize(self, messages: List[Dict[str, Any]], settings: Optional[Dict[str, Any]] = None) -> str:
        model = (settings or {}).get("modelName", self.default_model)
        system_message = (settings or {}).get("openaiSystemMessage", "")
        provided_prompt = (settings or {}).get("prompt")

        if provided_prompt:
            messages_payload = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": provided_prompt},
            ]
        else:
            messages_payload = [
                {"role": "system", "content": system_message},
                *[{"role": m.get("role", "user"), "content": m.get("content", "")}
                  for m in messages],
            ]

        payload = {
            "model": model,
            "messages": messages_payload,
            "temperature": 0.2,
            "max_tokens": 1024,
        }
        api_key = (settings or {}).get("apiKey") or self.api_key
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        _logger.debug("OpenAI request model=%s api_key=%s", model, mask_api_key(api_key))
        try:
            # rate limit external calls
            self.rate_limiter.acquire()
            resp = self._call_post_json(self.endpoint, payload, headers,
                                        timeout=45.0, settings=settings)
            choices = resp.get("choices", [])
            if not choices:
                raise LLMProviderError(f"Empty OpenAI response: {resp}")
            return choices[0]["message"]["content"].strip()
        except (OSError, URLError, json.JSONDecodeError) as exc:
            raise LLMProviderError(f"OpenAI summarize failed: {exc}") from exc

    def _call_post_json(self, url: str, payload: dict, headers: dict, timeout: float = 15.0, settings: Optional[Dict[str, Any]] = None) -> dict:
        """Delegate posting to a provided hook in settings when available (for tests) or use internal _post_json."""
        hook = (settings or {}).get("_post_json")
        if callable(hook):
            # Tests expect signature (url, payload)
            return hook(url, payload)
        return self._post_json(url, payload, headers, timeout)

    def list_models(self) -> List[str]:
        # Hardcoded for now; can be extended to fetch from OpenAI API
        return ["gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini", "o3-mini"]

    def download_model(self, model_name: str) -> str:
        raise NotImplementedError("Model download not supported for OpenAI.")

    def get_model_status(self, model_name: str) -> Dict[str, Any]:
        return {"available": model_name in self.list_models()}

    def start(self) -> str:
        return "No start required for OpenAI."

    def stop(self) -> str:
        return "No stop required for OpenAI."

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
        return "\n".join(m.get("content", "") for m in messages)

# Async implementation stub (to be completed)
class AsyncOpenAIProvider(AsyncLLMProvider):
    def __init__(self, api_key: Optional[str] = None):
        self._sync = OpenAIProvider(api_key=api_key)

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
