from types import SimpleNamespace
from typing import Any

import pytest

from backend import summary_service
from backend.llm_provider_clients import ProviderClientError, ProviderRequest, get_provider_client


MESSAGES = [
    {
        'id': 'm1',
        'subject': 'Quarterly project update',
        'sender': 'alice@example.com',
        'recipient': 'you@example.com',
        'date': '2026-04-01T15:00:00Z',
        'body': 'Budget approved. Review the launch checklist by Friday.',
    }
]


def test_empty_message_list_skips_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    class StubClient:
        def summarize(self, request: ProviderRequest) -> str:
            raise AssertionError('provider should not be called for empty message lists')

    monkeypatch.setattr(summary_service, 'get_provider_client', lambda provider: StubClient())

    text, meta = summary_service.summarize_messages([], 5, settings={'llmProvider': 'openai'})
    assert text.startswith('No messages matched')
    assert meta == {
        'provider': 'none',
        'model': 'none',
        'status': 'empty',
        'fallback': 'false',
    }


def test_unknown_provider_falls_back_to_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, ProviderRequest] = {}

    class StubClient:
        def summarize(self, request: ProviderRequest) -> str:
            captured['request'] = request
            return f"{summary_service.RESPONSE_SENTINEL}\nDone"

    monkeypatch.setattr(summary_service, 'get_provider_client', lambda provider: StubClient())
    monkeypatch.setattr(summary_service, 'ensure_ollama_running',
                        lambda host, auto_start: (True, 'ok'))

    text, meta = summary_service.summarize_messages(
        MESSAGES, 5, settings={'llmProvider': 'mystery-provider'})
    assert text == 'Done'
    assert meta['provider'] == 'ollama'
    assert captured['request'].host == 'http://127.0.0.1:11434'


def test_placeholder_provider_response_triggers_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    class StubClient:
        def summarize(self, request: ProviderRequest) -> str:
            return "I'm ready to summarize. Please provide the emails."

    monkeypatch.setattr(summary_service, 'get_provider_client', lambda provider: StubClient())
    monkeypatch.setattr(summary_service, 'ensure_ollama_running',
                        lambda host, auto_start: (True, 'ok'))

    text, meta = summary_service.summarize_messages(MESSAGES, 5, settings={'llmProvider': 'ollama'})
    assert text.startswith('Fallback summary (provider unavailable).')
    assert meta['status'] == 'fallback'
    assert 'placeholder content' in meta['error']


def test_masked_provider_keys_do_not_count_as_real_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)

    class StubClient:
        def summarize(self, request: ProviderRequest) -> str:
            raise ProviderClientError(f'api_key={request.api_key!r}')

    monkeypatch.setattr(summary_service, 'get_provider_client', lambda provider: StubClient())

    text, meta = summary_service.summarize_messages(
        MESSAGES,
        5,
        settings={'llmProvider': 'openai', 'openaiApiKey': '__MASKED__', 'llmApiKey': '__MASKED__'},
    )
    assert meta['status'] == 'fallback'
    assert "api_key=''" in meta['error']
    assert text.startswith('Fallback summary')


def test_provider_errors_redact_environment_api_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_key = 'sk-test-secret-value-12345'
    monkeypatch.setenv('OPENAI_API_KEY', fake_key)
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)

    class StubClient:
        def summarize(self, request: ProviderRequest) -> str:
            raise ProviderClientError(f'provider rejected api_key={request.api_key}')

    monkeypatch.setattr(summary_service, 'get_provider_client', lambda provider: StubClient())

    text, meta = summary_service.summarize_messages(
        MESSAGES,
        5,
        settings={'llmProvider': 'openai', 'openaiApiKey': '__MASKED__'},
    )
    assert meta['status'] == 'fallback'
    assert fake_key not in meta['error']
    assert fake_key not in text
    assert '[redacted]' in meta['error']


def test_openai_client_uses_library_response_api(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib

    captured: dict[str, Any] = {}

    class ResponsesAPI:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(output_text=f"{summary_service.RESPONSE_SENTINEL}\nLibrary path works")

    class OpenAIStub:
        def __init__(self, api_key: str):
            captured['api_key'] = api_key
            self.responses = ResponsesAPI()

    real_import_module = importlib.import_module

    def fake_import_module(name: str):
        if name == 'openai':
            return SimpleNamespace(OpenAI=OpenAIStub)
        return real_import_module(name)

    monkeypatch.setattr(importlib, 'import_module', fake_import_module)

    client = get_provider_client('openai')
    text = client.summarize(ProviderRequest(model='gpt-4.1-mini',
                            api_key='secret', system_message='system', prompt='prompt'))
    assert text.endswith('Library path works')
    assert captured['api_key'] == 'secret'
    assert captured['model'] == 'gpt-4.1-mini'
    assert captured['input'][0]['role'] == 'system'
    assert captured['input'][1]['role'] == 'user'


def test_anthropic_client_joins_text_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib

    class MessagesAPI:
        def create(self, **kwargs):
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type='text', text=f'{summary_service.RESPONSE_SENTINEL}\nPart one'),
                    SimpleNamespace(type='text', text='Part two'),
                ]
            )

    class AnthropicStub:
        def __init__(self, api_key: str):
            self.messages = MessagesAPI()

    real_import_module = importlib.import_module

    def fake_import_module(name: str):
        if name == 'anthropic':
            return SimpleNamespace(Anthropic=AnthropicStub)
        return real_import_module(name)

    monkeypatch.setattr(importlib, 'import_module', fake_import_module)

    client = get_provider_client('anthropic')
    text = client.summarize(ProviderRequest(model='claude-3-7-sonnet',
                            api_key='secret', system_message='system', prompt='prompt'))
    assert text.startswith(summary_service.RESPONSE_SENTINEL)
    assert 'Part two' in text
