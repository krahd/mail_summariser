from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from urllib.error import URLError
from urllib.request import Request, urlopen


class ProviderClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderRequest:
    model: str
    prompt: str
    system_message: str
    api_key: str = ''
    host: str = 'http://127.0.0.1:11434'
    auto_start: bool = True


class BaseProviderClient:
    provider_name: str = 'unknown'

    def summarize(self, request: ProviderRequest) -> str:
        raise NotImplementedError


class OpenAIProviderClient(BaseProviderClient):
    provider_name = 'openai'

    def summarize(self, request: ProviderRequest) -> str:
        if not request.api_key.strip():
            raise ProviderClientError('OpenAI API key is missing')
        try:
            openai_module = importlib.import_module('openai')
        except ModuleNotFoundError as exc:
            raise ProviderClientError('openai package is not installed') from exc

        client = openai_module.OpenAI(api_key=request.api_key.strip())
        try:
            response = client.responses.create(
                model=request.model,
                input=[
                    {'role': 'system', 'content': request.system_message},
                    {'role': 'user', 'content': request.prompt},
                ],
                temperature=0.2,
            )
            text = getattr(response, 'output_text', '')
            if text:
                return str(text).strip()
            raise ProviderClientError('OpenAI response did not include output_text')
        except Exception as exc:  # pragma: no cover - depends on library internals
            raise ProviderClientError(str(exc)) from exc


class AnthropicProviderClient(BaseProviderClient):
    provider_name = 'anthropic'

    def summarize(self, request: ProviderRequest) -> str:
        if not request.api_key.strip():
            raise ProviderClientError('Anthropic API key is missing')
        try:
            anthropic_module = importlib.import_module('anthropic')
        except ModuleNotFoundError as exc:
            raise ProviderClientError('anthropic package is not installed') from exc

        client = anthropic_module.Anthropic(api_key=request.api_key.strip())
        try:
            response = client.messages.create(
                model=request.model,
                max_tokens=900,
                temperature=0.2,
                system=request.system_message,
                messages=[{'role': 'user', 'content': request.prompt}],
            )
            blocks = getattr(response, 'content', [])
            texts = [getattr(block, 'text', '') for block in blocks if getattr(block, 'type', '') == 'text']
            text = '\n'.join(part for part in texts if part).strip()
            if not text:
                raise ProviderClientError('Anthropic response contained no text blocks')
            return text
        except Exception as exc:  # pragma: no cover
            raise ProviderClientError(str(exc)) from exc


class OllamaProviderClient(BaseProviderClient):
    provider_name = 'ollama'

    def summarize(self, request: ProviderRequest) -> str:
        payload = {
            'model': request.model,
            'system': request.system_message,
            'prompt': request.prompt,
            'stream': False,
        }
        req = Request(
            url=f"{request.host.rstrip('/')}/api/generate",
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        try:
            with urlopen(req, timeout=45.0) as response:
                parsed = json.loads(response.read().decode('utf-8'))
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise ProviderClientError(str(exc)) from exc
        text = str(parsed.get('response', '')).strip()
        if not text:
            raise ProviderClientError(f'Empty Ollama response: {parsed}')
        return text


def get_provider_client(provider: str) -> BaseProviderClient:
    normalized = provider.strip().lower()
    if normalized == 'openai':
        return OpenAIProviderClient()
    if normalized == 'anthropic':
        return AnthropicProviderClient()
    return OllamaProviderClient()
