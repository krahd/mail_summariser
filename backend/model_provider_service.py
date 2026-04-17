from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from typing import List


# Minimal runtime state and managed-process tracking used by tests
_managed_process = None
_managed_process_host: str | None = None


def _mark_managed_process(process, host: str) -> None:
    global _managed_process, _managed_process_host
    _managed_process = process
    _managed_process_host = host


def _clear_managed_process() -> None:
    global _managed_process, _managed_process_host
    _managed_process = None
    _managed_process_host = None


@dataclass
class _RuntimeState:
    last_message: str = ""
    last_message_host: str = ""
    last_message_model: str = ""
    last_message_warning: bool = False


_runtime_state = _RuntimeState()


def is_ollama_installed(host: str) -> bool:
    # In tests this is patched; default to True for local development
    return True


def is_ollama_running(host: str) -> bool:
    # Default implementation checks if a managed process appears to be alive
    global _managed_process
    if _managed_process is None:
        return False
    poll = getattr(_managed_process, 'poll', None)
    try:
        return poll() is None
    except Exception:
        return False


def list_ollama_models(host: str) -> List[str]:
    # Default: no models installed. Tests patch this to control behavior.
    return []


def _post_json(url: str, payload: dict) -> dict:
    # Simple stub; tests patch this if needed
    return {}


def ensure_ollama_running(ollama_host: str, auto_start: bool) -> tuple[bool, str]:
    """Ensure Ollama is running. Attempts to start when auto_start is True.

    Returns (success: bool, message: str).
    """
    # Check installed
    if not is_ollama_installed(ollama_host):
        _runtime_state.last_message = 'Install Ollama'
        _runtime_state.last_message_host = ollama_host
        _runtime_state.last_message_warning = True
        return False, 'Install Ollama'

    # Already running?
    if is_ollama_running(ollama_host):
        msg = f'Ollama already running at {ollama_host}'
        _runtime_state.last_message = msg
        _runtime_state.last_message_host = ollama_host
        _runtime_state.last_message_warning = False
        return True, msg

    if not auto_start:
        _runtime_state.last_message = 'Ollama not running'
        _runtime_state.last_message_host = ollama_host
        _runtime_state.last_message_warning = True
        return False, 'Ollama not running'

    # Try to start a managed process - tests may patch subprocess.Popen
    try:
        proc = subprocess.Popen(['ollama', 'serve'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        _mark_managed_process(proc, ollama_host)
    except Exception as exc:
        msg = f'Failed to start Ollama: {exc}'
        _runtime_state.last_message = msg
        _runtime_state.last_message_host = ollama_host
        _runtime_state.last_message_warning = True
        return False, msg

    # Wait briefly for it to report running
    for _ in range(10):
        if is_ollama_running(ollama_host):
            break
        time.sleep(0.05)

    if not is_ollama_running(ollama_host):
        msg = 'Failed to start Ollama'
        _runtime_state.last_message = msg
        _runtime_state.last_message_host = ollama_host
        _runtime_state.last_message_warning = True
        return False, msg

    # Warm model if available
    models = list_ollama_models(ollama_host)
    if models:
        try:
            _post_json(f"{ollama_host}/models/{models[0]}/generate", {"prompt": "warm up"})
            msg = f'ready with model {models[0]}'
            _runtime_state.last_message = msg
            _runtime_state.last_message_host = ollama_host
            _runtime_state.last_message_model = models[0]
            _runtime_state.last_message_warning = False
            return True, msg
        except Exception:
            msg = 'running (model warm-up failed)'
            _runtime_state.last_message = msg
            _runtime_state.last_message_host = ollama_host
            _runtime_state.last_message_warning = False
            return True, msg
    # No models installed on the Ollama runtime
    msg = 'running (models not installed)'
    _runtime_state.last_message = msg
    _runtime_state.last_message_host = ollama_host
    _runtime_state.last_message_warning = True
    return True, msg


def stop_managed_ollama(only_owned: bool) -> tuple[bool, str]:
    global _managed_process
    if _managed_process is None:
        return False, 'No Ollama process started by mail_summariser'
    try:
        # Prefer a graceful stop if available
        send_signal = getattr(_managed_process, 'send_signal', None)
        if callable(send_signal):
            send_signal(None)
        else:
            terminate = getattr(_managed_process, 'terminate', None)
            if callable(terminate):
                terminate()
    except Exception:
        pass
    _clear_managed_process()
    return True, 'Stopped app-managed Ollama'
