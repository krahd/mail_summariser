from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from typing import List


# Minimal runtime state and managed-process tracking used by tests
_managed_process = None
_managed_process_host: str | None = None


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


def is_ollama_installed(host: str) -> bool:
    # In tests this is patched; default to True for local development
    return True


def is_ollama_running(host: str) -> bool:
    # Default implementation checks if a managed process appears to be alive
    if _managed_process is None:
        return False
    if not hasattr(_managed_process, 'poll'):
        return False
    try:
        return _managed_process.poll() is None
    except (OSError, TypeError):
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
    # Initialize defaults
    success = False
    msg = ''
    warning = True

    # Check installed
    if not is_ollama_installed(ollama_host):
        msg = 'Install Ollama'
        success = False
        warning = True
    elif is_ollama_running(ollama_host):
        msg = f'Ollama already running at {ollama_host}'
        success = True
        warning = False
    elif not auto_start:
        msg = 'Ollama not running'
        success = False
        warning = True
    else:
        # Attempt to start and warm Ollama in a helper to reduce nested branching
        def _start_and_warm(host: str) -> tuple[bool, str, bool]:
            try:
                proc = subprocess.Popen(['ollama', 'serve'],
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                _mark_managed_process(proc, host)
            except (OSError, subprocess.SubprocessError) as exc:
                return False, f'Failed to start Ollama: {exc}', True

            for _ in range(10):
                if is_ollama_running(host):
                    break
                time.sleep(0.05)

            if not is_ollama_running(host):
                return False, 'Failed to start Ollama', True

            models = list_ollama_models(host)
            if not models:
                return True, 'running (models not installed)', True

            try:
                _post_json(f"{host}/models/{models[0]}/generate", {"prompt": "warm up"})
                _runtime_state.last_message_model = models[0]
                return True, f'ready with model {models[0]}', False
            except Exception:  # pylint: disable=broad-except
                return True, 'running (model warm-up failed)', False

        success, msg, warning = _start_and_warm(ollama_host)

    # Update runtime state once before returning
    _runtime_state.last_message = msg
    _runtime_state.last_message_host = ollama_host
    _runtime_state.last_message_warning = bool(warning)
    return success, msg


def stop_managed_ollama(only_owned: bool) -> tuple[bool, str]:  # pylint: disable=global-statement
    if _managed_process is None:
        return False, 'No Ollama process started by mail_summariser'
    try:
        # Prefer a graceful stop if available
        if hasattr(_managed_process, 'send_signal') and callable(_managed_process.send_signal):
            _managed_process.send_signal(None)
        elif hasattr(_managed_process, 'terminate') and callable(_managed_process.terminate):
            _managed_process.terminate()
    except OSError:
        # Best-effort: ignore OS-level errors during shutdown
        pass
    _clear_managed_process()
    return True, 'Stopped app-managed Ollama'
