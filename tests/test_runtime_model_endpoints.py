from __future__ import annotations

import importlib
import sys
import tempfile
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from backend import app as backend_app
from backend import db as backend_db
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


def test_runtime_routes_use_persisted_ollama_settings() -> None:
    saved_host = 'http://127.0.0.1:9999'
    saved_model = 'custom-model:latest'
    host_calls: list[str] = []
    original_backend_db_path = backend_db.DB_PATH
    top_level_db = sys.modules.get('db')
    original_top_level_db_path = getattr(top_level_db, 'DB_PATH', None)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_db_path = Path(temp_dir) / 'mail_summariser.sqlite3'
        backend_db.DB_PATH = temp_db_path
        if top_level_db is not None:
            top_level_db.DB_PATH = temp_db_path

        def capture_list_models(host: str) -> list[str]:
            host_calls.append(host)
            return [saved_model]

        def capture_serve_model(host: str, model_name: str) -> tuple[bool, str]:
            host_calls.append(host)
            assert model_name == saved_model
            return True, 'served'

        settings_payload = {
            key: value for key, value in backend_app.DEFAULT_SETTINGS.items()
            if key != 'llmApiKey'
        }
        settings_payload.update({
            'imapPassword': '',
            'smtpPassword': '',
            'username': '',
            'recipientEmail': '',
            'openaiApiKey': '',
            'anthropicApiKey': '',
            'ollamaHost': saved_host,
            'modelName': saved_model,
            'ollamaStartOnStartup': False,
        })

        try:
            with (
                mock.patch.object(model_provider_service, 'is_ollama_installed',
                                  return_value=True),
                mock.patch.object(model_provider_service, 'is_ollama_running',
                                  return_value=True),
                mock.patch.object(model_provider_service, 'list_ollama_models',
                                  side_effect=capture_list_models),
                mock.patch.object(model_provider_service, 'serve_ollama_model',
                                  side_effect=capture_serve_model),
                mock.patch.object(top_level_provider, 'is_ollama_installed',
                                  return_value=True),
                mock.patch.object(top_level_provider, 'is_ollama_running',
                                  return_value=True),
                mock.patch.object(top_level_provider, 'list_ollama_models',
                                  side_effect=capture_list_models),
                mock.patch.object(top_level_provider, 'serve_ollama_model',
                                  side_effect=capture_serve_model),
            ):
                with TestClient(backend_app.app) as client:
                    save = client.post('/settings', json=settings_payload)
                    runtime = client.get('/runtime/status')
                    options = client.get('/models/options', params={'provider': 'ollama'})
                    serve = client.post('/models/serve', json={'name': saved_model})
        finally:
            backend_db.DB_PATH = original_backend_db_path
            if top_level_db is not None:
                top_level_db.DB_PATH = original_top_level_db_path

    assert save.status_code == 200
    assert runtime.status_code == 200
    assert options.status_code == 200
    assert serve.status_code == 200
    assert runtime.json()['ollama']['host'] == saved_host
    assert runtime.json()['ollama']['modelName'] == saved_model
    assert options.json()['ollama']['host'] == saved_host
    assert saved_host in host_calls


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


def test_list_online_ollama_models_parses_string_catalog_entries() -> None:
    with mock.patch.object(
        model_provider_service,
        'list_remote_model_catalog',
        return_value=['llama3.2:latest 4.7GB 2 days ago', 'mistral:latest'],
    ):
        models = model_provider_service.list_online_ollama_models('http://127.0.0.1:11434', limit=10)

    assert models == ['llama3.2:latest', 'mistral:latest']


def test_list_online_ollama_models_falls_back_when_remote_catalog_is_empty() -> None:
    with mock.patch.object(
        model_provider_service,
        'list_remote_model_catalog',
        return_value=[],
    ), mock.patch.object(model_provider_service, 'urlopen', side_effect=OSError('offline')):
        models = model_provider_service.list_online_ollama_models('http://127.0.0.1:11434', limit=4)

    assert models == [
        'llama3.2:latest',
        'llama3.1:8b',
        'mistral:latest',
        'qwen2.5:latest',
    ]


def test_list_online_ollama_models_uses_library_html_fallback() -> None:
    html = (
        '<a href="/library/llama3.2">Llama</a>'
        '<a href="/library/mistral">Mistral</a>'
        '<a href="/library/deepseek-r1:8b">DeepSeek</a>'
    )

    mock_response = mock.MagicMock()
    mock_response.read.return_value = html.encode('utf-8')
    mock_urlopen = mock.MagicMock()
    mock_urlopen.return_value.__enter__.return_value = mock_response

    with mock.patch.object(
        model_provider_service,
        'list_remote_model_catalog',
        return_value=[],
    ), mock.patch.object(model_provider_service, 'urlopen', mock_urlopen):
        models = model_provider_service.list_online_ollama_models('http://127.0.0.1:11434', limit=10)

    assert models == ['llama3.2:latest', 'mistral:latest', 'deepseek-r1:8b']


def test_models_catalog_returns_error_when_empty() -> None:
    with (
        mock.patch.object(model_provider_service, 'list_online_ollama_models', return_value=[]),
        mock.patch.object(top_level_provider, 'list_online_ollama_models', return_value=[]),
    ):
        with TestClient(backend_app.app) as client:
            response = client.get('/models/catalog', params={'limit': 20})

    assert response.status_code == 200
    payload = response.json()
    assert payload['provider'] == 'ollama'
    assert payload['count'] == 0
    assert payload['models'] == []
    assert 'error' in payload


def test_serve_ollama_model_returns_error_when_pull_in_progress() -> None:
    """serve_ollama_model must report a clear message when the model is still downloading."""
    with mock.patch.object(
        model_provider_service,
        'get_pull_status',
        return_value={'name': 'llama3.2:latest', 'status': 'downloading', 'message': 'Downloading'},
    ):
        ok, message = model_provider_service.serve_ollama_model(
            'http://127.0.0.1:11434', 'llama3.2:latest'
        )

    assert ok is False
    assert 'downloading' in message.lower() or 'pull' in message.lower()


def test_serve_endpoint_reports_error_when_model_is_downloading() -> None:
    """POST /models/serve must propagate the still-downloading error through the HTTP layer."""
    downloading_msg = 'Model llama3.2:latest is still downloading. Wait for pull to finish.'
    with (
        mock.patch.object(model_provider_service, 'serve_ollama_model',
                          return_value=(False, downloading_msg)),
        mock.patch.object(top_level_provider, 'serve_ollama_model',
                          return_value=(False, downloading_msg)),
    ):
        with TestClient(backend_app.app) as client:
            response = client.post('/models/serve', json={'name': 'llama3.2:latest'})

    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'error'
    assert 'downloading' in payload['message'].lower()


def test_pull_ollama_model_does_not_double_start_active_download() -> None:
    """pull_ollama_model must not start a second thread when one is already alive."""
    alive_thread = mock.MagicMock()
    alive_thread.is_alive.return_value = True

    with mock.patch.dict(
        model_provider_service._download_threads,  # type: ignore[attr-defined]
        {'llama3.2:latest': alive_thread},
    ), mock.patch.object(
        model_provider_service, 'is_ollama_installed', return_value=True
    ):
        ok, message = model_provider_service.pull_ollama_model('llama3.2:latest')

    assert ok is True
    assert 'already downloading' in message.lower()
