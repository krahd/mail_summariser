"""
modelito/ollama.py

Ollama provider implementation for the LLM provider library.
Supports both synchronous and asynchronous operation.
"""


import subprocess
import threading
import json
import asyncio
from typing import Any, Dict, List, Optional, cast
from urllib.request import urlopen, Request
from urllib.parse import urlparse

from . import ollama_service
from .timeout import estimate_remote_timeout

from .base import LLMProvider
from .base import AsyncLLMProvider
from .exceptions import LLMProviderError, ProviderUnavailableError, ModelDownloadError
from .utils import setup_logger, get_env_setting, RateLimiter

_ollama_lock = threading.Lock()
_logger = setup_logger("modelito.ollama")

class OllamaProvider(LLMProvider):
    def __init__(self, host: str = "http://127.0.0.1:11434"):
        self.host = host.rstrip("/")
        try:
            rl = int(get_env_setting("MODELITO_RATE_LIMIT", 60))
        except Exception:
            rl = 60
        self.rate_limiter = RateLimiter(max_calls=rl, period=60.0)

    def summarize(self, messages: List[Dict[str, Any]], settings: Optional[Dict[str, Any]] = None) -> str:
        provided_prompt = (settings or {}).get("prompt")
        prompt = provided_prompt or self._build_prompt(messages, settings)
        model = (settings or {}).get("modelName", "llama3.2:latest")
        system_message = (settings or {}).get("ollamaSystemMessage", "")
        payload = {
            "model": model,
            "system": system_message,
            "prompt": prompt,
            "stream": False,
        }
        try:
            _logger.debug("Calling Ollama host=%s model=%s", self.host, model)
            # apply rate limiting before external request
            self.rate_limiter.acquire()
            resp = self._call_post_json(f"{self.host}/api/generate",
                                        payload, timeout=45.0, settings=settings)
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
            # Prefer the Ollama CLI pull when available, otherwise fall back to HTTP pull
            try:
                # run_ollama_command is provided by the service helper
                ollama_service.run_ollama_command(
                    "pull", model_name, host=self.host.replace("http://", "").replace("https://", ""))
                return f"Download requested for {model_name} (via CLI)"
            except FileNotFoundError:
                payload = {"name": model_name, "stream": False}
                self._post_json(f"{self.host}/api/pull", payload, timeout=20.0)
                return f"Download requested for {model_name} (via HTTP)"
        except (OSError, json.JSONDecodeError) as exc:
            raise ModelDownloadError(f"Failed to request model download: {exc}") from exc

    def get_model_status(self, model_name: str) -> Dict[str, Any]:
        try:
            models = self.list_models()
            return {"installed": model_name in models}
        except (OSError, json.JSONDecodeError) as exc:
            raise LLMProviderError(f"Failed to get model status: {exc}") from exc

    def start(self) -> str:
        # Try to start Ollama serve if not running
        if self._is_running():
            return f"Ollama already running at {self.host}"
        try:
            # Delegate to the consolidated ollama service helper when possible
            parsed = urlparse(self.host)
            scheme = parsed.scheme or "http"
            netloc = parsed.netloc or parsed.path
            if ":" in netloc:
                host, port_s = netloc.split(":", 1)
                port = int(port_s)
            else:
                host = netloc
                port = 11434
            base_url = f"{scheme}://{host}"
            # start a detached serve process
            with _ollama_lock:
                ollama_service.start_detached_ollama_serve(host=f"{base_url}:{port}")
            # wait briefly for readiness
            try:
                ollama_service.wait_until_ready(base_url, port, timeout_seconds=20.0)
            except Exception:
                pass
            return f"Ollama started at {self.host}"
        except (OSError, subprocess.SubprocessError) as exc:
            raise ProviderUnavailableError(f"Failed to start Ollama: {exc}") from exc

    def stop(self) -> str:
        # Attempt a graceful stop via the service helper
        try:
            parsed = urlparse(self.host)
            scheme = parsed.scheme or "http"
            netloc = parsed.netloc or parsed.path
            if ":" in netloc:
                host, port_s = netloc.split(":", 1)
                port = int(port_s)
            else:
                host = netloc
                port = 11434
            base_url = f"{scheme}://{host}"
            rc = ollama_service.stop_service(base_url, port, verbose=False)
            if rc == 0:
                return f"Ollama stopped at {self.host}"
            return f"Stop returned code {rc} for {self.host}"
        except Exception as exc:
            raise ProviderUnavailableError(f"Failed to stop Ollama: {exc}") from exc

    def get_runtime_status(self) -> Dict[str, Any]:
        return {"running": self._is_running(), "host": self.host}

    def _is_running(self) -> bool:
        try:
            # prefer service helper check
            parsed = urlparse(self.host)
            scheme = parsed.scheme or "http"
            netloc = parsed.netloc or parsed.path
            if ":" in netloc:
                host, port_s = netloc.split(":", 1)
                port = int(port_s)
            else:
                host = netloc
                port = 11434
            base_url = f"{scheme}://{host}"
            return ollama_service.server_is_up(base_url, port)
        except Exception:
            return False

    def _get_json(self, url: str, timeout: float = 2.0) -> dict[str, Any]:
        with urlopen(url, timeout=timeout) as response:
            return cast(Dict[str, Any], json.loads(response.read().decode("utf-8")))

    def _post_json(self, url: str, payload: dict, timeout: float = 15.0) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = Request(url=url, data=body, headers={
                      "Content-Type": "application/json"}, method="POST")
        with urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            if not raw.strip():
                return {}
            return cast(Dict[str, Any], json.loads(raw))

    def _call_post_json(self, url: str, payload: dict, timeout: float = 15.0, settings: Optional[Dict[str, Any]] = None) -> dict[str, Any]:
        hook = (settings or {}).get("_post_json")
        if callable(hook):
            return cast(Dict[str, Any], hook(url, payload))
        # Determine timeout: explicit setting -> estimator -> default
        t = None
        if settings:
            t = settings.get("timeout_seconds")
        if t is None:
            model = (settings or {}).get("modelName") or (payload or {}).get("model")
            try:
                t = estimate_remote_timeout(model)
            except Exception:
                t = timeout
        return self._post_json(url, payload, timeout=float(t))

    def _build_prompt(self, messages: List[Dict[str, Any]], _settings: Optional[Dict[str, Any]]) -> str:
        # _settings argument is unused but kept for interface compatibility
        return "\n".join(m.get("content", "") for m in messages)

class AsyncOllamaProvider(AsyncLLMProvider):
    def __init__(self, host: str = "http://127.0.0.1:11434"):
        self._sync = OllamaProvider(host=host)

    async def summarize(self, messages: List[Dict[str, Any]], settings: Optional[Dict[str, Any]] = None) -> str:
        # Prefer an async HTTP client where available for lower latency.
        httpx_mod = None
        try:
            import importlib

            httpx_mod = importlib.import_module("httpx")
        except Exception:
            httpx_mod = None

        if httpx_mod is not None:
            try:
                model = (settings or {}).get("modelName", None)
                payload = {
                    "model": model or "llama3.2:latest",
                    "system": (settings or {}).get("ollamaSystemMessage", ""),
                    "prompt": (settings or {}).get("prompt") or "\n".join(m.get("content", "") for m in messages),
                    "stream": False,
                }
                timeout = estimate_remote_timeout(payload.get("model"))
                async with httpx_mod.AsyncClient() as client:
                    r = await client.post(f"{self._sync.host}/api/generate", json=payload, timeout=timeout)
                    r.raise_for_status()
                    data = r.json()
                    return str(data.get("response", "")).strip()
            except Exception:
                # Fall back to the sync provider on any async/httpx error
                pass

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
