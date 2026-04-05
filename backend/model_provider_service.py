import json
import os
import signal
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlparse
from urllib.error import URLError
from urllib.request import urlopen

# In-memory set of model names whose download is in-progress this session
_active_downloads: set[str] = set()
INSTALL_OLLAMA_URL = "https://ollama.com/download"

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


@dataclass
class _OllamaRuntimeState:
    process: subprocess.Popen | None = None
    host: str = ""
    started_by_app: bool = False
    last_message: str = "Ollama status not checked yet"
    last_message_host: str = ""
    last_message_model: str = ""
    last_message_warning: bool = False


_runtime_state = _OllamaRuntimeState()
_runtime_lock = threading.Lock()


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


def _set_runtime_message(ollama_host: str, model_name: str, message: str, warning: bool = False) -> None:
    host = _normalize_host(ollama_host)
    model = (model_name or "").strip()
    with _runtime_lock:
        _runtime_state.last_message = message
        _runtime_state.last_message_host = host
        _runtime_state.last_message_model = model
        _runtime_state.last_message_warning = warning


def _get_runtime_message(ollama_host: str, model_name: str) -> tuple[str | None, bool]:
    host = _normalize_host(ollama_host)
    model = (model_name or "").strip()
    with _runtime_lock:
        if _runtime_state.last_message_host != host:
            return None, False
        if _runtime_state.last_message_model not in ("", model):
            return None, False
        return _runtime_state.last_message, _runtime_state.last_message_warning


def _refresh_tracked_process_state() -> None:
    with _runtime_lock:
        process = _runtime_state.process
        if process is not None and process.poll() is not None:
            _runtime_state.process = None
            _runtime_state.host = ""
            _runtime_state.started_by_app = False


def _mark_managed_process(process: subprocess.Popen, ollama_host: str) -> None:
    host = _normalize_host(ollama_host)
    with _runtime_lock:
        _runtime_state.process = process
        _runtime_state.host = host
        _runtime_state.started_by_app = True


def _clear_managed_process() -> None:
    with _runtime_lock:
        _runtime_state.process = None
        _runtime_state.host = ""
        _runtime_state.started_by_app = False


def _signal_process(process: subprocess.Popen, sig: signal.Signals) -> None:
    try:
        os.killpg(os.getpgid(process.pid), sig)
        return
    except (ProcessLookupError, PermissionError, OSError):
        pass

    try:
        process.send_signal(sig)
    except OSError:
        pass


def is_ollama_installed() -> bool:
    return shutil.which("ollama") is not None


def was_ollama_started_by_app(ollama_host: str) -> bool:
    _refresh_tracked_process_state()
    host = _normalize_host(ollama_host)
    with _runtime_lock:
        return _runtime_state.started_by_app and _runtime_state.host == host and _runtime_state.process is not None


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
        message = f"Ollama is running at {host}"
        _set_runtime_message(host, "", message)
        return True, message

    if not auto_start:
        message = f"Ollama is not running at {host} and auto-start is disabled"
        _set_runtime_message(host, "", message, warning=True)
        return False, message

    started, message = start_ollama_service(host)
    if not started:
        _set_runtime_message(host, "", message, warning=True)
        return False, message

    _set_runtime_message(host, "", message)
    return True, message


def start_ollama_service(ollama_host: str) -> tuple[bool, str]:
    host = _normalize_host(ollama_host)
    if is_ollama_running(host):
        return True, f"Ollama is already running at {host}"

    if not is_ollama_installed():
        return False, "Ollama CLI not found. Install Ollama to use local models"

    env = os.environ.copy()
    env["OLLAMA_HOST"] = _ollama_host_for_env(host)

    try:
        process = subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=env,
        )
    except OSError as exc:
        return False, f"Failed to start Ollama: {exc}"

    for _ in range(24):
        if is_ollama_running(host):
            _mark_managed_process(process, host)
            return True, f"Ollama started at {host}"
        if process.poll() is not None:
            break
        time.sleep(0.5)

    if process.poll() is None:
        _signal_process(process, signal.SIGTERM)
    _clear_managed_process()
    return False, f"Tried to start Ollama at {host} but it did not become ready in time"


def warm_ollama_model(model_name: str, ollama_host: str) -> tuple[bool, str]:
    host = _normalize_host(ollama_host)
    name = (model_name or "").strip() or "llama3.2:latest"

    if not is_ollama_running(host):
        return False, f"Ollama is not running at {host}"

    try:
        local_models = list_ollama_models(host)
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return False, f"Ollama is running, but installed models could not be listed: {exc}"

    if name not in local_models:
        return False, f"Ollama is running, but model '{name}' is not installed. Download it from Settings."

    try:
        _post_json(
            f"{host}/api/generate",
            {
                "model": name,
                "prompt": "Reply with READY.",
                "stream": False,
            },
            timeout=60.0,
        )
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return False, f"Ollama is running, but failed to warm model '{name}': {exc}"

    return True, f"Ollama is ready with model '{name}' at {host}"


def start_and_warm_ollama(model_name: str, ollama_host: str) -> tuple[str, str]:
    host = _normalize_host(ollama_host)
    name = (model_name or "").strip() or "llama3.2:latest"

    running, start_message = ensure_ollama_running(host, auto_start=True)
    if not running:
        _set_runtime_message(host, name, start_message, warning=True)
        return "error", start_message

    warmed, warm_message = warm_ollama_model(name, host)
    _set_runtime_message(host, name, warm_message, warning=not warmed)
    return ("ok" if warmed else "warning"), warm_message


def run_ollama_startup_check(provider: str, ollama_host: str, model_name: str, start_on_startup: bool) -> None:
    normalized_provider = (provider or "").strip().lower()
    host = _normalize_host(ollama_host)
    name = (model_name or "").strip() or "llama3.2:latest"

    if normalized_provider != "ollama":
        _set_runtime_message(host, name, "Ollama startup checks are inactive because the selected provider is not Ollama.")
        return

    if not is_ollama_installed():
        _set_runtime_message(host, name, "Ollama CLI not found. Install Ollama to use local models.", warning=True)
        return

    if not start_on_startup:
        if is_ollama_running(host):
            _set_runtime_message(host, name, f"Ollama is running at {host}")
        else:
            _set_runtime_message(host, name, f"Ollama is installed but not running at {host}. Start it to use model '{name}'.", warning=True)
        return

    _status, message = start_and_warm_ollama(name, host)
    if _status == "error":
        _set_runtime_message(host, name, message, warning=True)


def get_ollama_runtime_status(provider: str, ollama_host: str, model_name: str) -> dict[str, object]:
    normalized_provider = (provider or "").strip().lower()
    host = _normalize_host(ollama_host)
    name = (model_name or "").strip() or "llama3.2:latest"
    installed = is_ollama_installed()
    running = installed and is_ollama_running(host)
    started_by_app = running and was_ollama_started_by_app(host)
    cached_message, _cached_warning = _get_runtime_message(host, name)

    if normalized_provider != "ollama":
        startup_action = "none"
        message = "Ollama startup prompts are inactive because the selected provider is not Ollama."
    elif not installed:
        startup_action = "install"
        message = "Ollama CLI not found. Install Ollama to use local models."
    elif not running:
        startup_action = "start"
        message = f"Ollama is installed but not running at {host}. Start it to use model '{name}'."
    else:
        startup_action = "none"
        if cached_message:
            message = cached_message
        elif started_by_app:
            message = f"Ollama is running at {host} (started by mail_summariser)."
        else:
            message = f"Ollama is running at {host}."

    return {
        "installed": installed,
        "running": running,
        "startedByApp": started_by_app,
        "host": host,
        "modelName": name,
        "startupAction": startup_action,
        "message": message,
        "installUrl": INSTALL_OLLAMA_URL,
    }


def stop_managed_ollama(stop_on_exit: bool) -> tuple[bool, str]:
    _refresh_tracked_process_state()
    if not stop_on_exit:
        return False, "Configured to keep Ollama running on exit"

    with _runtime_lock:
        process = _runtime_state.process
        host = _runtime_state.host
        started_by_app = _runtime_state.started_by_app

    if process is None or not started_by_app:
        return False, "No Ollama process started by mail_summariser is running"

    _signal_process(process, signal.SIGTERM)
    for _ in range(20):
        if process.poll() is not None:
            break
        time.sleep(0.25)

    if process.poll() is None:
        _signal_process(process, signal.SIGKILL)

    _clear_managed_process()
    _set_runtime_message(host, "", f"Stopped app-managed Ollama at {host}")
    return True, f"Stopped app-managed Ollama at {host}"


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
