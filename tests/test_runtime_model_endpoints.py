from __future__ import annotations

import importlib
from unittest import mock

from fastapi.testclient import TestClient

from backend import app as backend_app
from backend import model_provider_service


try:
    top_level_provider = importlib.import_module('model_provider_service')
except ModuleNotFoundError:  # pragma: no cover
    top_level_provider = model_provider_service


def test_runtime_and_model_endpoints_smoke() -> None:
    with (
        mock.patch.object(model_provider_service, 'is_ollama_installed', return_value=True),
        mock.patch.object(model_provider_service, 'is_ollama_running', return_value=False),
        mock.patch.object(model_provider_service, 'list_ollama_models',
                          return_value=['llama3.2:latest']),
        mock.patch.object(top_level_provider, 'is_ollama_installed', return_value=True),
        mock.patch.object(top_level_provider, 'is_ollama_running', return_value=False),
        mock.patch.object(top_level_provider, 'list_ollama_models',
                          return_value=['llama3.2:latest']),
    ):
        with TestClient(backend_app.app) as client:
            runtime = client.get('/runtime/status')
            options = client.get('/models/options', params={'provider': 'ollama'})
            catalog = client.get('/models/catalog', params={'limit': 5})

    assert runtime.status_code == 200
    assert options.status_code == 200
    assert catalog.status_code == 200

    runtime_payload = runtime.json()
    options_payload = options.json()
    catalog_payload = catalog.json()

    assert runtime_payload['ollama']['host']
    assert options_payload['provider'] == 'ollama'
    assert isinstance(options_payload['models'], list)
    assert catalog_payload['provider'] == 'ollama'
    assert catalog_payload['count'] == len(catalog_payload['models'])


def test_runtime_start_ollama_endpoint_returns_runtime_payload() -> None:
    with (
        mock.patch.object(model_provider_service, 'ensure_ollama_running',
                          return_value=(True, 'ok')),
        mock.patch.object(model_provider_service, 'list_ollama_models',
                          return_value=['llama3.2:latest']),
        mock.patch.object(model_provider_service, 'is_ollama_installed', return_value=True),
        mock.patch.object(model_provider_service, 'is_ollama_running', return_value=True),
        mock.patch.object(top_level_provider, 'ensure_ollama_running', return_value=(True, 'ok')),
        mock.patch.object(top_level_provider, 'list_ollama_models',
                          return_value=['llama3.2:latest']),
        mock.patch.object(top_level_provider, 'is_ollama_installed', return_value=True),
        mock.patch.object(top_level_provider, 'is_ollama_running', return_value=True),
    ):
        with TestClient(backend_app.app) as client:
            response = client.post('/runtime/ollama/start', json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'ok'
    assert payload['runtime']['ollama']['running'] is True
