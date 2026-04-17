"""
modelito/openai.py

OpenAI provider implementation for the LLM provider library.
Supports both synchronous and asynchronous operation.
"""


import json
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen

from .base import LLMProvider, AsyncLLMProvider
from .exceptions import LLMProviderError
from .utils import get_env_setting, setup_logger

_logger = setup_logger("modelito.openai")

class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or get_env_setting("OPENAI_API_KEY")
        self.endpoint = "https://api.openai.com/v1/chat/completions"
        self.default_model = "gpt-4.1"

    def summarize(self, messages: List[Dict[str, Any]], settings: Optional[Dict[str, Any]] = None) -> str:
        model = (settings or {}).get("modelName", self.default_model)
        system_message = (settings or {}).get("openaiSystemMessage", "")
        # prompt = self._build_prompt(messages, settings)  # Unused variable
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_message},
                *[{"role": m.get("role", "user"), "content": m.get("content", "")}
                  for m in messages],
            ],
            "temperature": 0.2,
            "max_tokens": 1024,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = self._post_json(self.endpoint, payload, headers, timeout=45.0)
            choices = resp.get("choices", [])
            if not choices:
                raise LLMProviderError(f"Empty OpenAI response: {resp}")
            return choices[0]["message"]["content"].strip()
        except Exception as exc:
            raise LLMProviderError(f"OpenAI summarize failed: {exc}") from exc

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
    async def summarize(self, messages: List[Dict[str, Any]], settings: Optional[Dict[str, Any]] = None) -> str:
        raise NotImplementedError("Async OpenAI not yet implemented")
    async def list_models(self) -> List[str]:
        raise NotImplementedError("Async OpenAI not yet implemented")
    async def download_model(self, model_name: str) -> str:
        raise NotImplementedError("Async OpenAI not yet implemented")
    async def get_model_status(self, model_name: str) -> Dict[str, Any]:
        raise NotImplementedError("Async OpenAI not yet implemented")
    async def start(self) -> str:
        raise NotImplementedError("Async OpenAI not yet implemented")
    async def stop(self) -> str:
        raise NotImplementedError("Async OpenAI not yet implemented")
    async def get_runtime_status(self) -> Dict[str, Any]:
        raise NotImplementedError("Async OpenAI not yet implemented")
