from __future__ import annotations

import sys
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from backend.config import DEFAULT_SETTINGS
from backend.router_context import get_app_module


router = APIRouter()


class _ModelNamePayload(BaseModel):
    name: str


def _provider_module() -> Any:
    # Prefer test-patched top-level module when present.
    if 'model_provider_service' in sys.modules:
        return sys.modules['model_provider_service']
    from backend import model_provider_service

    return model_provider_service


def _build_runtime_status() -> dict:
    provider = _provider_module()
    backend = {'running': True, 'canShutdown': True}
    host = str(DEFAULT_SETTINGS.get('ollamaHost', 'http://127.0.0.1:11434'))
    installed = False
    running = False
    model_name = DEFAULT_SETTINGS.get('modelName', '')
    started_by_app = False
    message = ''

    try:
        installed = bool(getattr(provider, 'is_ollama_installed')(host))
    except (AttributeError, TypeError, OSError):
        installed = False
    try:
        running = bool(getattr(provider, 'is_ollama_running')(host))
    except (AttributeError, TypeError, OSError):
        running = False
    try:
        started_by_app = getattr(provider, '_managed_process_host', None) == host
    except (AttributeError, TypeError):
        started_by_app = False

    if not installed:
        startup_action = 'install'
        message = 'Install Ollama'
    elif not running:
        startup_action = 'start'
        message = 'Ollama not running'
    else:
        startup_action = 'none'
        message = 'Ollama running'

    try:
        rt = getattr(provider, '_runtime_state', None)
        if rt and getattr(rt, 'last_message_host', '') == host and getattr(rt, 'last_message', ''):
            message = rt.last_message
    except (AttributeError, TypeError):
        pass

    ollama = {
        'installed': installed,
        'running': running,
        'startedByApp': started_by_app,
        'host': host,
        'modelName': model_name,
        'startupAction': startup_action,
        'message': message,
        'installUrl': 'https://ollama.com',
    }

    return {'backend': backend, 'ollama': ollama}


@router.get('/runtime/status')
def runtime_status() -> dict:
    return _build_runtime_status()


@router.post('/runtime/ollama/start')
def runtime_start_ollama() -> dict:
    provider = _provider_module()
    host = str(DEFAULT_SETTINGS.get('ollamaHost', 'http://127.0.0.1:11434'))
    _started, message = provider.ensure_ollama_running(host, auto_start=True)
    runtime = _build_runtime_status()
    try:
        models = provider.list_ollama_models(host)
    except (AttributeError, TypeError, OSError):
        models = []
    status = 'ok' if models else 'warning'
    return {'status': status, 'message': message, 'runtime': runtime}


@router.post('/runtime/ollama/install')
def runtime_install_ollama() -> dict:
    provider = _provider_module()
    installed, message = provider.install_ollama()
    runtime = _build_runtime_status()
    return {'status': 'ok' if installed else 'error', 'message': message, 'runtime': runtime}


@router.post('/runtime/ollama/stop')
def runtime_stop_ollama() -> dict:
    provider = _provider_module()
    stopped, message = provider.stop_managed_ollama(only_owned=False)
    runtime = _build_runtime_status()
    return {'status': 'ok' if stopped else 'warning', 'message': message, 'runtime': runtime}


@router.post('/runtime/shutdown')
def runtime_shutdown() -> dict:
    app_module = get_app_module()
    app_module._schedule_backend_shutdown()
    return {'status': 'ok'}


@router.get('/models/options')
def models_options(provider: str | None = None) -> dict:
    prov = (provider or 'openai').lower()
    if prov == 'openai':
        return {'provider': 'openai', 'models': []}
    if prov == 'ollama':
        service = _provider_module()
        host = str(DEFAULT_SETTINGS.get('ollamaHost', 'http://127.0.0.1:11434'))
        try:
            models = service.list_ollama_models(host)
        except (AttributeError, TypeError, OSError):
            models = []
        running = service.is_ollama_running(host)
        rt = getattr(service, '_runtime_state', None)
        last_message = getattr(rt, 'last_message', '') if rt is not None else ''
        return {
            'provider': 'ollama',
            'models': models,
            'ollama': {'running': running, 'host': host, 'message': last_message},
        }
    return {'provider': prov, 'models': []}


@router.get('/models/catalog')
def models_catalog(query: str | None = None, limit: int | None = 20) -> dict:
    provider = _provider_module()
    host = str(DEFAULT_SETTINGS.get('ollamaHost', 'http://127.0.0.1:11434'))
    try:
        models = provider.list_online_ollama_models(host, query=query or '', limit=int(limit or 20))
    except (AttributeError, TypeError, OSError):
        models = []
    return {'provider': 'ollama', 'models': models, 'count': len(models)}


@router.post('/models/serve')
def models_serve(payload: _ModelNamePayload) -> dict:
    provider = _provider_module()
    host = str(DEFAULT_SETTINGS.get('ollamaHost', 'http://127.0.0.1:11434'))
    ok, message = provider.serve_ollama_model(host, payload.name)
    return {'status': 'ok' if ok else 'error', 'message': message}


@router.post('/models/download')
def models_download(payload: _ModelNamePayload) -> dict:
    provider = _provider_module()
    ok, message = provider.pull_ollama_model(payload.name)
    return {'status': 'ok' if ok else 'error', 'message': message}


@router.get('/models/download/status')
def models_download_status(name: str) -> dict:
    provider = _provider_module()
    return provider.get_pull_status(name)


@router.delete('/models/local')
def models_delete(name: str) -> dict:
    provider = _provider_module()
    ok, message = provider.delete_ollama_model(name)
    return {'status': 'ok' if ok else 'error', 'message': message}
