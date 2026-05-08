from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import List
from urllib.parse import urlparse
from urllib.request import urlopen

from modelito import (
    clear_model_lifecycle_state,
    delete_model,
    detect_install_method,
    download_model,
    ensure_model_ready,
    ensure_ollama_running_verbose,
    get_model_lifecycle_state,
    install_ollama as modelito_install_ollama,
    list_local_models,
    list_remote_model_catalog,
    ollama_installed,
    server_is_up,
    stop_ollama,
)


# Minimal runtime state and managed-process tracking used by tests
_managed_process = None
_managed_process_host: str | None = None
_download_threads: dict[str, threading.Thread] = {}
_download_messages: dict[str, str] = {}
_download_results: dict[str, tuple[bool, str]] = {}


def _mark_managed_process(process, host: str) -> None:  # pylint: disable=global-statement
    global _managed_process, _managed_process_host  # pylint: disable=global-statement
    _managed_process = process
    _managed_process_host = host


def _clear_managed_process() -> None:  # pylint: disable=global-statement
    global _managed_process, _managed_process_host  # pylint: disable=global-statement
    _managed_process = None
    _managed_process_host = None


@dataclass
class _RuntimeState:
    last_message: str = ""
    last_message_host: str = ""
    last_message_model: str = ""
    last_message_warning: bool = False


_runtime_state = _RuntimeState()

_DEFAULT_REMOTE_MODEL_CATALOG: tuple[str, ...] = (
    'llama3.2:latest',
    'llama3.1:8b',
    'mistral:latest',
    'qwen2.5:latest',
    'phi3:latest',
    'gemma2:latest',
    'deepseek-r1:latest',
    'nomic-embed-text:latest',
)


def _list_ollama_library_models(query_text: str, limit: int) -> list[str]:
    try:
        with urlopen('https://ollama.com/library', timeout=8) as response:
            html = response.read().decode('utf-8', errors='ignore')
    except OSError:
        return []

    names: list[str] = []
    seen: set[str] = set()
    for raw_name in re.findall(r'href=["\']?/library/([A-Za-z0-9._:-]+)["\']', html):
        name = raw_name.strip()
        if not name:
            continue
        if ':' not in name:
            name = f'{name}:latest'
        if query_text and query_text not in name.lower():
            continue
        if name in seen:
            continue
        names.append(name)
        seen.add(name)
        if len(names) >= limit:
            break
    return names


def _normalize_model_name(raw: str) -> str:
    """Return a clean model identifier from UI/CLI style model strings."""
    value = str(raw or '').strip()
    if not value:
        return ''
    # Some providers/CLIs include digest/size/date columns after the name.
    return value.split()[0].strip()


def _normalized_ollama_endpoint(host: str) -> tuple[str, str, int]:
    parsed = urlparse(host if '://' in host else f'http://{host}')
    scheme = parsed.scheme or 'http'
    hostname = parsed.hostname or '127.0.0.1'
    port = parsed.port or 11434
    base_url = f'{scheme}://{hostname}'
    return f'{base_url}:{port}', base_url, port


def is_ollama_installed(host: str) -> bool:
    del host
    try:
        return bool(ollama_installed())
    except (OSError, TypeError, ValueError):
        return False


def is_ollama_running(host: str) -> bool:
    _full_host, base_url, port = _normalized_ollama_endpoint(host)
    try:
        return bool(server_is_up(base_url, port))
    except (OSError, TypeError, ValueError):
        return False


def list_ollama_models(host: str) -> List[str]:
    del host
    try:
        models = list_local_models()
    except (OSError, TypeError, ValueError):
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for entry in models:
        name = _normalize_model_name(entry)
        if name and name not in seen:
            normalized.append(name)
            seen.add(name)
    return normalized


def list_online_ollama_models(host: str, query: str = '', limit: int = 20) -> List[str]:
    del host
    normalized_query = query.strip().lower()
    catalog = list_remote_model_catalog(query=query.strip() or None)
    max_items = max(1, int(limit))
    names: list[str] = []
    seen: set[str] = set()
    for entry in catalog:
        name = ''
        if isinstance(entry, dict):
            name = str(entry.get('name', '')).strip()
        elif isinstance(entry, str):
            name = entry.strip()
        else:
            name = str(getattr(entry, 'name', '')).strip()
        name = _normalize_model_name(name)
        if not name or name in seen:
            continue
        names.append(name)
        seen.add(name)
        if len(names) >= max_items:
            break
    if names:
        return names

    library_names = _list_ollama_library_models(normalized_query, max_items)
    if library_names:
        return library_names

    # Keep Discover Models usable when the upstream remote catalog endpoint
    # returns an empty list despite a healthy local runtime.
    fallback: list[str] = []
    for model_name in _DEFAULT_REMOTE_MODEL_CATALOG:
        if normalized_query and normalized_query not in model_name.lower():
            continue
        fallback.append(model_name)
        if len(fallback) >= max_items:
            break
    return fallback


def install_ollama() -> tuple[bool, str]:
    if is_ollama_installed(''):
        return True, 'Ollama is already installed'
    try:
        method = detect_install_method()
        installed = bool(modelito_install_ollama(allow_install=True, method=method, timeout=600.0))
    except (OSError, TypeError, ValueError) as exc:
        return False, f'Failed to run installer: {exc}'
    if not installed:
        return False, 'Ollama install failed'
    return True, 'Ollama installed successfully'


def ensure_ollama_running(ollama_host: str, auto_start: bool) -> tuple[bool, str]:
    """Ensure Ollama is running. Attempts to start when auto_start is True.

    Returns (success: bool, message: str).
    """
    # Initialize defaults
    success = False
    msg = ''
    warning = True

    full_host, base_url, port = _normalized_ollama_endpoint(ollama_host)

    # Check installed
    if not is_ollama_installed(ollama_host):
        msg = 'Install Ollama'
        success = False
        warning = True
    elif is_ollama_running(full_host):
        msg = f'Ollama already running at {full_host}'
        success = True
        warning = False
    elif not auto_start:
        msg = 'Ollama not running'
        success = False
        warning = True
    else:
        started, start_message = ensure_ollama_running_verbose(
            host=base_url,
            port=port,
            auto_start=True,
            timeout=15.0,
        )
        if started:
            _mark_managed_process(object(), full_host)

        # Keep runtime checks deterministic by validating through the same
        # status helper used in route payloads.
        if started and not is_ollama_running(full_host):
            started = False

        if not started:
            msg = start_message or 'Failed to start Ollama'
            success = False
            warning = True
        else:
            models = list_ollama_models(full_host)
            if not models:
                success = True
                msg = 'running (models not installed)'
                warning = True
            else:
                warmed = ensure_model_ready(
                    models[0],
                    host=base_url,
                    port=port,
                    auto_start=True,
                    allow_download=False,
                    timeout=120.0,
                )
                _runtime_state.last_message_model = models[0]
                if warmed:
                    success = True
                    msg = f'ready with model {models[0]}'
                    warning = False
                else:
                    success = True
                    msg = 'running (model warm-up failed)'
                    warning = False

    # Update runtime state once before returning
    _runtime_state.last_message = msg
    _runtime_state.last_message_host = full_host
    _runtime_state.last_message_warning = bool(warning)
    return success, msg


def stop_managed_ollama(only_owned: bool) -> tuple[bool, str]:  # pylint: disable=global-statement
    if _managed_process_host:
        full_host, _base_url, _port = _normalized_ollama_endpoint(_managed_process_host)
    else:
        full_host = 'http://127.0.0.1:11434'

    if only_owned and _managed_process is None:
        return False, 'No Ollama process started by mail_summariser'

    if _managed_process is not None:
        try:
            if hasattr(_managed_process, 'send_signal') and callable(_managed_process.send_signal):
                _managed_process.send_signal(None)
            elif hasattr(_managed_process, 'terminate') and callable(_managed_process.terminate):
                _managed_process.terminate()
        except OSError:
            pass

    if only_owned:
        _clear_managed_process()
        return True, 'Stopped app-managed Ollama'

    try:
        stopped = bool(stop_ollama(force=True))
    except (OSError, TypeError, ValueError):
        stopped = False

    _clear_managed_process()
    if stopped:
        return True, f'Stopped Ollama at {full_host}'
    return False, 'Failed to stop Ollama'


def serve_ollama_model(ollama_host: str, model_name: str) -> tuple[bool, str]:
    normalized_model = _normalize_model_name(model_name)
    if not normalized_model:
        return False, 'Model name is required'

    host, base_url, port = _normalized_ollama_endpoint(ollama_host)

    pull_state = get_pull_status(normalized_model)
    if pull_state.get('status') == 'downloading':
        return False, f'Model {normalized_model} is still downloading. Wait for pull to finish.'

    started, message = ensure_ollama_running(host, auto_start=True)
    if not started:
        return False, message

    ready = ensure_model_ready(
        normalized_model,
        host=base_url,
        port=port,
        auto_start=True,
        allow_download=False,
        timeout=120.0,
    )
    if not ready:
        local_models = list_ollama_models(host)
        if normalized_model not in local_models:
            return False, f'Model {normalized_model} is not available locally yet. Download it first.'
        return False, f'Failed to serve model {normalized_model}'
    _runtime_state.last_message_model = normalized_model
    _runtime_state.last_message = f'Model {normalized_model} is warmed and ready'
    _runtime_state.last_message_host = host
    _runtime_state.last_message_warning = False
    return True, _runtime_state.last_message


def pull_ollama_model(name: str) -> tuple[bool, str]:
    model_name = name.strip()
    if not model_name:
        return False, 'Model name is required'
    if not is_ollama_installed(''):
        return False, 'Ollama is not installed'
    thread = _download_threads.get(model_name)
    if thread is not None and thread.is_alive():
        return True, f'Model {model_name} is already downloading'

    def _download_worker(target: str) -> None:
        ok = bool(download_model(target, timeout=1800.0))
        state = get_model_lifecycle_state(target)
        if ok:
            _download_results[target] = (True, 'Download completed')
            _download_messages[target] = 'Download completed'
            return
        message = 'Download failed'
        if state is not None:
            message = state.error or state.message or message
        _download_results[target] = (False, message)
        _download_messages[target] = message

    try:
        clear_model_lifecycle_state(model_name)
    except (OSError, TypeError, ValueError):
        pass

    worker = threading.Thread(target=_download_worker, args=(model_name,), daemon=True)
    _download_threads[model_name] = worker
    worker.start()
    _download_messages[model_name] = 'Download started'
    return True, f'Started downloading {model_name}'


def get_pull_status(name: str) -> dict:
    model_name = name.strip()
    if not model_name:
        return {'name': '', 'status': 'error', 'message': 'Model name is required'}

    state = get_model_lifecycle_state(model_name)
    thread = _download_threads.get(model_name)

    if thread is not None and thread.is_alive():
        if state is not None:
            if state.phase == 'error':
                return {'name': model_name, 'status': 'error', 'message': state.error or state.message or 'Download failed'}
            if state.phase == 'downloaded':
                return {'name': model_name, 'status': 'completed', 'message': state.message or 'Download completed'}
            return {'name': model_name, 'status': 'downloading', 'message': state.message or _download_messages.get(model_name, 'Downloading')}
        return {'name': model_name, 'status': 'downloading', 'message': _download_messages.get(model_name, 'Downloading')}

    if model_name in _download_results:
        ok, message = _download_results[model_name]
        return {'name': model_name, 'status': 'completed' if ok else 'error', 'message': message}

    if state is not None:
        if state.phase == 'downloaded':
            return {'name': model_name, 'status': 'completed', 'message': state.message or 'Download completed'}
        if state.phase == 'error':
            return {'name': model_name, 'status': 'error', 'message': state.error or state.message or 'Download failed'}

    local_models = list_ollama_models('http://127.0.0.1:11434')
    if model_name in local_models:
        return {'name': model_name, 'status': 'completed'}
    return {'name': model_name, 'status': 'not_found'}


def delete_ollama_model(name: str) -> tuple[bool, str]:
    model_name = name.strip()
    if not model_name:
        return False, 'Model name is required'
    if not is_ollama_installed(''):
        return False, 'Ollama is not installed'

    try:
        deleted = bool(delete_model(model_name))
    except (OSError, TypeError, ValueError) as exc:
        return False, f'Failed to delete model: {exc}'
    if not deleted:
        return False, 'Delete failed'
    return True, f'Deleted model {model_name}'
