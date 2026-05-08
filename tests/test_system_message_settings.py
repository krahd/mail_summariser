import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend import db as backend_db
from backend.config import DEFAULT_SETTINGS, DEFAULT_SYSTEM_MESSAGES


def _base_settings() -> dict[str, object]:
    return dict(DEFAULT_SETTINGS)


@pytest.fixture(autouse=True)
def isolated_settings_db(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(backend_db, 'DB_PATH', tmp_path / 'mail_summariser-test.sqlite3')


def test_settings_endpoint_exposes_provider_specific_system_messages() -> None:
    with TestClient(app) as client:
        response = client.get('/settings')
        assert response.status_code == 200
        payload = response.json()
        assert payload['ollamaSystemMessage'] == DEFAULT_SYSTEM_MESSAGES['ollamaSystemMessage']
        assert payload['openaiSystemMessage'] == DEFAULT_SYSTEM_MESSAGES['openaiSystemMessage']
        assert payload['anthropicSystemMessage'] == DEFAULT_SYSTEM_MESSAGES['anthropicSystemMessage']


def test_system_message_defaults_endpoint_returns_expected_defaults() -> None:
    with TestClient(app) as client:
        response = client.get('/settings/system-message-defaults')
        assert response.status_code == 200
        assert response.json() == DEFAULT_SYSTEM_MESSAGES


def test_default_system_messages_keep_new_prompt_guidance() -> None:
    assert DEFAULT_SYSTEM_MESSAGES['openaiSystemMessage'] == (
        'Create compact, practical email digests. Prioritise deadlines, requests, blockers, '
        'and follow-up actions. Group related threads, avoid greetings and filler, do not '
        'invent facts, and make the next step obvious when one exists.'
    )
    assert DEFAULT_SYSTEM_MESSAGES['anthropicSystemMessage'] == (
        'Create concise, practical email summaries with clear action cues. Highlight '
        'deadlines, owners, approvals, risks, and reply-needed items. Keep wording neutral, '
        'specific, and free of invented details.'
    )
    assert DEFAULT_SYSTEM_MESSAGES['ollamaSystemMessage'] == (
        'Create compact, practical email digests that focus on priorities, deadlines, '
        'blockers, and follow-up actions. Group related messages, keep the output scannable, '
        'and prefer specific next steps over generic commentary.'
    )


def test_post_settings_persists_custom_provider_specific_system_messages() -> None:
    with TestClient(app) as client:
        payload = _base_settings()
        payload.update(
            {
                'llmProvider': 'openai',
                'modelName': 'gpt-4.1-mini',
                'openaiApiKey': 'super-secret-openai-key',
                'openaiSystemMessage': 'OpenAI system prompt for concise summaries.',
                'anthropicSystemMessage': 'Anthropic system prompt for terse digests.',
                'ollamaSystemMessage': 'Ollama system prompt for local summaries.',
            }
        )
        response = client.post('/settings', json=payload)
        assert response.status_code == 200

        settings_response = client.get('/settings')
        assert settings_response.status_code == 200
        settings_payload = settings_response.json()
        assert settings_payload['openaiSystemMessage'] == 'OpenAI system prompt for concise summaries.'
        assert settings_payload['anthropicSystemMessage'] == 'Anthropic system prompt for terse digests.'
        assert settings_payload['ollamaSystemMessage'] == 'Ollama system prompt for local summaries.'
        assert settings_payload['openaiApiKey'] == '__MASKED__'


def test_database_reset_restores_default_system_messages() -> None:
    with TestClient(app) as client:
        payload = _base_settings()
        payload.update(
            {
                'openaiSystemMessage': 'Temporary override',
                'anthropicSystemMessage': 'Temporary override',
                'ollamaSystemMessage': 'Temporary override',
            }
        )
        assert client.post('/settings', json=payload).status_code == 200

        reset_response = client.post('/admin/database/reset', json={'confirmation': 'RESET DATABASE'})
        assert reset_response.status_code == 200
        settings_payload = reset_response.json()['settings']
        assert settings_payload['openaiSystemMessage'] == DEFAULT_SYSTEM_MESSAGES['openaiSystemMessage']
        assert settings_payload['anthropicSystemMessage'] == DEFAULT_SYSTEM_MESSAGES['anthropicSystemMessage']
        assert settings_payload['ollamaSystemMessage'] == DEFAULT_SYSTEM_MESSAGES['ollamaSystemMessage']
