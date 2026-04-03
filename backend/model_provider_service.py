import json
import os
import shutil
import subprocess
import time
from urllib.parse import urlparse
from urllib.error import URLError
from urllib.request import urlopen

# In-memory set of model names whose download is in-progress this session
_active_downloads: set[str] = set()

REMOTE_MODELS = {
    "openai": [
        "gpt-4.1-mini",
        "gpt-4.1",
        "gpt-4o-mini",
        "o3-mini",
    ],
    "anthropic": [
        "claude-3-5-haiku-latest",
        "claude-3-5-sonnet-latest",
        "claude-3-7-sonnet-latest",
    ],
}

DEFAULT_OLLAMA_CATALOG = [
    "llama3.2:latest",
    "phi3:mini",
    "qwen2.5:7b",
    "mistral:latest",
    "gemma3:4b",
    "deepseek-r1:7b",
]


def _normalize_host(ollama_host: str) -> str:
    host = (ollama_host or "").strip().rstrip("/")
    return host or "http://127.0.0.1:11434"


def _get_json(url: str, timeout: float = 2.0) -> dict:
    with urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(url: str, payload: dict, timeout: float = 15.0) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = {
        "Content-Type": "application/json",
    }
    from urllib.request import Request  # local import to keep module import section compact

    req = Request(url=url, data=body, headers=request, method="POST")
    with urlopen(req, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
        if not raw.strip():
            return {}
        return json.loads(raw)


def _ollama_host_for_env(ollama_host: str) -> str:
    parsed = urlparse(_normalize_host(ollama_host))
    if parsed.scheme and parsed.netloc:
        return parsed.netloc
    return _normalize_host(ollama_host).replace("http://", "").replace("https://", "")


def is_ollama_running(ollama_host: str) -> bool:
    host = _normalize_host(ollama_host)
    try:
        _get_json(f"{host}/api/version", timeout=1.2)
        return True
    except (URLError, TimeoutError, json.JSONDecodeError, OSError):
        return False


def ensure_ollama_running(ollama_host: str, auto_start: bool) -> tuple[bool, str]:
    host = _normalize_host(ollama_host)
    if is_ollama_running(host):
        return True, "Ollama is running"

    if not auto_start:
        return False, "Ollama is not running and auto-start is disabled"

    if shutil.which("ollama") is None:
        return False, "Ollama CLI not found. Install Ollama to use local models"

    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        return False, f"Failed to start Ollama: {exc}"

    for _ in range(24):
        if is_ollama_running(host):
            return True, "Ollama started automatically"
        time.sleep(0.5)

    return False, "Tried to start Ollama but it did not become ready in time"


def list_ollama_models(ollama_host: str) -> list[str]:
    host = _normalize_host(ollama_host)
    payload = _get_json(f"{host}/api/tags", timeout=2.5)
    models = payload.get("models", [])
    names = [item.get("name", "").strip() for item in models]
    return [name for name in names if name]


def list_remote_models(provider: str) -> list[str]:
    return REMOTE_MODELS.get((provider or "").strip().lower(), [])


def list_downloadable_ollama_models(query: str = "", limit: int = 60) -> list[str]:
    normalized_query = (query or "").strip().lower()
    capped_limit = max(1, min(int(limit), 200))

    try:
        payload = _get_json("https://ollama.com/api/tags", timeout=4.5)
        names = [item.get("name", "").strip() for item in payload.get("models", [])]
        models = [name for name in names if name]
    except (URLError, TimeoutError, json.JSONDecodeError, OSError):
        models = DEFAULT_OLLAMA_CATALOG.copy()

    if normalized_query:
        models = [name for name in models if normalized_query in name.lower()]

    return models[:capped_limit]


def start_ollama_model_download(model_name: str, ollama_host: str) -> tuple[bool, str]:
    name = (model_name or "").strip()
    if not name:
        return False, "Model name is required"

    host = _normalize_host(ollama_host)
    if not is_ollama_running(host):
        return False, "Ollama is not running"

    if shutil.which("ollama"):
        env = os.environ.copy()
        env["OLLAMA_HOST"] = _ollama_host_for_env(host)
        try:
            subprocess.Popen(
                ["ollama", "pull", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                env=env,
            )
            _active_downloads.add(name)
            return True, f"Started download for {name}"
        except OSError as exc:
            return False, f"Failed to start model download: {exc}"

    try:
        _post_json(f"{host}/api/pull", {"name": name, "stream": False}, timeout=20.0)
        _active_downloads.add(name)
        return True, f"Download requested for {name}"
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return False, f"Failed to request model download: {exc}"


def get_model_download_status(model_name: str, ollama_host: str) -> dict[str, str]:
    """Check if a model download has completed, is in-progress, or is unknown."""
    name = (model_name or "").strip()
    if not name:
        return {"name": "", "status": "error", "message": "Model name is required"}

    host = _normalize_host(ollama_host)
    try:
        local_models = list_ollama_models(host)
        if name in local_models:
            _active_downloads.discard(name)
            return {"name": name, "status": "completed"}
    except (URLError, TimeoutError, json.JSONDecodeError, OSError):
        pass

    if name in _active_downloads:
        return {"name": name, "status": "downloading"}

    return {"name": name, "status": "not_found"}
