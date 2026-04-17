"""
modelito/ollama.py

Ollama provider implementation for the LLM provider library.
Supports both synchronous and asynchronous operation.
"""


import subprocess
import threading
import json
from typing import Any, Dict, List, Optional
from urllib.request import urlopen, Request

from .base import LLMProvider
from .base import AsyncLLMProvider
from .exceptions import LLMProviderError, ProviderUnavailableError, ModelDownloadError
from .utils import setup_logger

_ollama_lock = threading.Lock()
_logger = setup_logger("modelito.ollama")

class OllamaProvider(LLMProvider):
    def __init__(self, host: str = "http://127.0.0.1:11434"):
        self.host = host.rstrip("/")

    def summarize(self, messages: List[Dict[str, Any]], settings: Optional[Dict[str, Any]] = None) -> str:
        prompt = self._build_prompt(messages, settings)
        model = (settings or {}).get("modelName", "llama3.2:latest")
        system_message = (settings or {}).get("ollamaSystemMessage", "")
        payload = {
            "model": model,
            "system": system_message,
            "prompt": prompt,
            "stream": False,
        }
        try:
            resp = self._post_json(f"{self.host}/api/generate", payload, timeout=45.0)
            text = str(resp.get("response", "")).strip()
            if not text:
                raise LLMProviderError(f"Empty Ollama response: {resp}")
            return text
        except (subprocess.CalledProcessError, OSError, json.JSONDecodeError) as exc:
            _logger.error("Ollama summarize failed: %s", exc)
            raise LLMProviderError(f"Ollama summarize failed: {exc}") from exc

    def list_models(self) -> List[str]:
        try:
            payload = self._get_json(f"{self.host}/api/tags", timeout=2.5)
            models = payload.get("models", [])
            return [item.get("name", "").strip() for item in models if item.get("name")]
        except (OSError, json.JSONDecodeError) as exc:
            _logger.warning("Failed to list Ollama models: %s", exc)
            return []

    def download_model(self, model_name: str) -> str:
        try:
            payload = {"name": model_name, "stream": False}
            self._post_json(f"{self.host}/api/pull", payload, timeout=20.0)
            return f"Download requested for {model_name}"
        except Exception as exc:
            raise ModelDownloadError(f"Failed to request model download: {exc}") from exc

    def get_model_status(self, model_name: str) -> Dict[str, Any]:
        try:
            models = self.list_models()
            return {"installed": model_name in models}
        except Exception as exc:
            raise LLMProviderError(f"Failed to get model status: {exc}") from exc

    def start(self) -> str:
        # Try to start Ollama serve if not running
        if self._is_running():
            return f"Ollama already running at {self.host}"
        try:
            import os
            env = os.environ.copy()
            env["OLLAMA_HOST"] = self.host.replace("http://", "").replace("https://", "")
            with _ollama_lock:
                subprocess.Popen([
                    "ollama", "serve"
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True, env=env)
            return f"Ollama started at {self.host}"
        except Exception as exc:
            raise ProviderUnavailableError(f"Failed to start Ollama: {exc}") from exc

    def stop(self) -> str:
        # Not implemented: stopping Ollama is environment-specific
        return "Stop not implemented in library. Use system tools."

    def get_runtime_status(self) -> Dict[str, Any]:
        return {"running": self._is_running(), "host": self.host}

    def _is_running(self) -> bool:
        try:
            self._get_json(f"{self.host}/api/version", timeout=1.2)
            return True
        except (OSError, json.JSONDecodeError):
            return False

    def _get_json(self, url: str, timeout: float = 2.0) -> dict:
        with urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _post_json(self, url: str, payload: dict, timeout: float = 15.0) -> dict:
        body = json.dumps(payload).encode("utf-8")
        req = Request(url=url, data=body, headers={
                      "Content-Type": "application/json"}, method="POST")
        with urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            if not raw.strip():
                return {}
            return json.loads(raw)

    def _build_prompt(self, messages: List[Dict[str, Any]], _settings: Optional[Dict[str, Any]]) -> str:
        # _settings argument is unused but kept for interface compatibility
        return "\n".join(m.get("content", "") for m in messages)

# Async implementation stub (to be completed)
class AsyncOllamaProvider(AsyncLLMProvider):
    async def summarize(self, messages: List[Dict[str, Any]], settings: Optional[Dict[str, Any]] = None) -> str:
        raise NotImplementedError("Async Ollama not yet implemented")
    async def list_models(self) -> List[str]:
        raise NotImplementedError("Async Ollama not yet implemented")
    async def download_model(self, model_name: str) -> str:
        raise NotImplementedError("Async Ollama not yet implemented")
    async def get_model_status(self, model_name: str) -> Dict[str, Any]:
        raise NotImplementedError("Async Ollama not yet implemented")
    async def start(self) -> str:
        raise NotImplementedError("Async Ollama not yet implemented")
    async def stop(self) -> str:
        raise NotImplementedError("Async Ollama not yet implemented")
    async def get_runtime_status(self) -> Dict[str, Any]:
        raise NotImplementedError("Async Ollama not yet implemented")
