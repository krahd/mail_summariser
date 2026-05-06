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
        mock.patch.object(model_provider_service, 'list_online_ollama_models',
                          return_value=['llama3.2:latest', 'mistral:latest']),
        mock.patch.object(top_level_provider, 'is_ollama_installed', return_value=True),
        mock.patch.object(top_level_provider, 'is_ollama_running', return_value=False),
        mock.patch.object(top_level_provider, 'list_ollama_models',
                          return_value=['llama3.2:latest']),
        mock.patch.object(top_level_provider, 'list_online_ollama_models',
                          return_value=['llama3.2:latest', 'mistral:latest']),
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
    assert 'mistral:latest' in catalog_payload['models']
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


def test_runtime_ollama_admin_routes() -> None:
    with (
        mock.patch.object(model_provider_service, 'install_ollama',
                          return_value=(True, 'installed')),
        mock.patch.object(model_provider_service, 'stop_managed_ollama',
                          return_value=(True, 'stopped')),
        mock.patch.object(model_provider_service, 'serve_ollama_model',
                          return_value=(True, 'served')),
        mock.patch.object(model_provider_service, 'pull_ollama_model',
                          return_value=(True, 'pulling')),
        mock.patch.object(model_provider_service, 'get_pull_status', return_value={
                          'name': 'llama3.2:latest', 'status': 'completed'}),
        mock.patch.object(model_provider_service, 'delete_ollama_model',
                          return_value=(True, 'deleted')),
        mock.patch.object(model_provider_service, 'is_ollama_installed', return_value=True),
        mock.patch.object(model_provider_service, 'is_ollama_running', return_value=True),
        mock.patch.object(model_provider_service, 'list_ollama_models',
                          return_value=['llama3.2:latest']),
        mock.patch.object(top_level_provider, 'install_ollama', return_value=(True, 'installed')),
        mock.patch.object(top_level_provider, 'stop_managed_ollama',
                          return_value=(True, 'stopped')),
        mock.patch.object(top_level_provider, 'serve_ollama_model', return_value=(True, 'served')),
        mock.patch.object(top_level_provider, 'pull_ollama_model', return_value=(True, 'pulling')),
        mock.patch.object(top_level_provider, 'get_pull_status', return_value={
                          'name': 'llama3.2:latest', 'status': 'completed'}),
        mock.patch.object(top_level_provider, 'delete_ollama_model',
                          return_value=(True, 'deleted')),
        mock.patch.object(top_level_provider, 'is_ollama_installed', return_value=True),
        mock.patch.object(top_level_provider, 'is_ollama_running', return_value=True),
        mock.patch.object(top_level_provider, 'list_ollama_models',
                          return_value=['llama3.2:latest']),
    ):
        with TestClient(backend_app.app) as client:
            install = client.post('/runtime/ollama/install', json={})
            stop = client.post('/runtime/ollama/stop', json={})
            serve = client.post('/models/serve', json={'name': 'llama3.2:latest'})
            pull = client.post('/models/download', json={'name': 'llama3.2:latest'})
            pull_status = client.get('/models/download/status', params={'name': 'llama3.2:latest'})
            delete = client.delete('/models/local', params={'name': 'llama3.2:latest'})

    assert install.status_code == 200
    assert stop.status_code == 200
    assert serve.status_code == 200
    assert pull.status_code == 200
    assert pull_status.status_code == 200
    assert delete.status_code == 200
    assert install.json()['status'] == 'ok'
    assert stop.json()['status'] in {'ok', 'warning'}
    assert serve.json()['status'] == 'ok'
    assert pull.json()['status'] == 'ok'
    assert pull_status.json()['status'] == 'completed'
    assert delete.json()['status'] == 'ok'
