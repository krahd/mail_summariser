import os
import re

from backend.config import DEFAULT_SYSTEM_MESSAGES
from backend.llm_provider_clients import ProviderClientError, ProviderRequest, get_provider_client
from backend.model_provider_service import ensure_ollama_running


class ProviderError(Exception):
    pass


RESPONSE_SENTINEL = 'MAIL_SUMMARISER_VALID_V1'
SUPPORTED_PROVIDERS = {'ollama', 'openai', 'anthropic'}
EMPTY_SUMMARY_TEXT = (
    'No messages matched this search. Clear filters or adjust criteria, '
    'then generate another digest.'
)
MASKED_SECRET_VALUES = {'__MASKED__', ''}
SECRET_PATTERNS = (
    re.compile(r'sk-ant-[A-Za-z0-9_-]{8,}'),
    re.compile(r'sk-[A-Za-z0-9_-]{8,}'),
)


def _looks_like_placeholder_response(text: str) -> bool:
    normalized = (text or '').strip().lower()
    if not normalized:
        return True
    placeholder_markers = (
        'please provide the emails',
        'please share the emails',
        "i'm ready to summarize",
        'i am ready to summarize',
        'go ahead and provide the emails',
    )
    return any(marker in normalized for marker in placeholder_markers)


def _extract_valid_summary_text(text: str) -> str:
    raw = (text or '').strip()
    if not raw:
        raise ProviderError('Provider returned empty content')
    lines = [line.strip() for line in raw.splitlines()]
    if not lines or lines[0] != RESPONSE_SENTINEL:
        raise ProviderError('Provider response missing validation sentinel')
    summary = '\n'.join(raw.splitlines()[1:]).strip()
    if not summary:
        raise ProviderError('Provider returned sentinel but no summary content')
    return summary


def _effective_detail_level(summary_length: int) -> int:
    return max(1, min(int(summary_length), 24))


def _detail_label(level: int) -> str:
    labels = [
        (2, 'Very terse digest'),
        (4, 'Compact digest'),
        (6, 'Balanced digest'),
        (9, 'Detailed digest'),
        (12, 'Comprehensive digest'),
        (16, 'Expanded digest'),
        (20, 'In-depth digest'),
    ]
    for max_level, text in labels:
        if level <= max_level:
            return text
    return 'Extended digest'


def _demo_summarize_messages(messages: list[dict], summary_length: int) -> str:
    level = _effective_detail_level(summary_length)
    lines = [_detail_label(level), '', f'Messages summarized: {len(messages)}', '']
    for idx, message in enumerate(messages, start=1):
        body = message.get('body', '').strip().replace('\n', ' ')
        excerpt = body[: min(520, 60 + level * 20)]
        lines.append(f"{idx}. {message['sender']} — {message['subject']}")
        lines.append(f'   {excerpt}')
        if level >= 5:
            lines.append('   Action: review and decide whether a reply is needed.')
        lines.append('')
    return '\n'.join(lines).strip()


def _build_prompt(messages: list[dict], summary_length: int) -> str:
    level = _effective_detail_level(summary_length)
    target_lines = max(3, min(48, 4 + level * 2))
    chunks = [
        'Summarize the email list into concise actionable points.',
        f'Requested detail level: {summary_length}. Keep around {target_lines} bullet lines.',
        'Focus on priority items, deadlines, and likely responses needed.',
        f'First line must be exactly: {RESPONSE_SENTINEL}',
        'On following lines, provide only the summary.',
        '',
        'Emails:',
    ]
    for idx, message in enumerate(messages, start=1):
        body = message.get('body', '').strip().replace('\n', ' ')
        chunks.append(
            f"{idx}. Subject: {message.get('subject', '')} | From: {message.get('sender', '')} | Date: {message.get('date', '')}\n   Body: {body[:800]}"
        )
    return '\n'.join(chunks)


def _normalize_provider(provider: str) -> str:
    normalized = str(provider or 'ollama').strip().lower()
    return normalized if normalized in SUPPORTED_PROVIDERS else 'ollama'


def _resolve_provider_api_key(provider: str, cfg: dict) -> str:
    legacy_key = str(cfg.get('llmApiKey', ''))
    openai_key = str(cfg.get('openaiApiKey', ''))
    anthropic_key = str(cfg.get('anthropicApiKey', ''))
    if provider == 'openai':
        return (
            os.getenv('OPENAI_API_KEY', '').strip()
            or ('' if openai_key in MASKED_SECRET_VALUES else openai_key)
            or ('' if legacy_key in MASKED_SECRET_VALUES else legacy_key)
        )
    if provider == 'anthropic':
        return (
            os.getenv('ANTHROPIC_API_KEY', '').strip()
            or ('' if anthropic_key in MASKED_SECRET_VALUES else anthropic_key)
            or ('' if legacy_key in MASKED_SECRET_VALUES else legacy_key)
        )
    return ''


def _known_secret_values(cfg: dict) -> set[str]:
    values = {
        str(cfg.get('llmApiKey', '')),
        str(cfg.get('openaiApiKey', '')),
        str(cfg.get('anthropicApiKey', '')),
        os.getenv('OPENAI_API_KEY', '').strip(),
        os.getenv('ANTHROPIC_API_KEY', '').strip(),
    }
    return {value for value in values if value not in MASKED_SECRET_VALUES and len(value) >= 6}


def _redact_provider_error(message: str, cfg: dict) -> str:
    redacted = str(message)
    for secret in sorted(_known_secret_values(cfg), key=len, reverse=True):
        redacted = redacted.replace(secret, '[redacted]')
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub('[redacted]', redacted)
    return redacted


def _resolve_system_message(provider: str, cfg: dict) -> str:
    key = {'openai': 'openaiSystemMessage', 'anthropic': 'anthropicSystemMessage',
           'ollama': 'ollamaSystemMessage'}[provider]
    fallback = DEFAULT_SYSTEM_MESSAGES[key]
    return str(cfg.get(key, fallback)).strip() or fallback


def _summarize_with_provider(provider: str, model_name: str, prompt: str, system_message: str, cfg: dict) -> str:
    if provider == 'ollama':
        ollama_host = str(cfg.get('ollamaHost', 'http://127.0.0.1:11434'))
        auto_start = bool(cfg.get('ollamaAutoStart', True))
        running, message = ensure_ollama_running(ollama_host, auto_start)
        if not running:
            raise ProviderError(message)
        request = ProviderRequest(model=model_name, prompt=prompt,
                                  system_message=system_message, host=ollama_host, auto_start=auto_start)
    else:
        request = ProviderRequest(model=model_name, prompt=prompt,
                                  system_message=system_message, api_key=_resolve_provider_api_key(provider, cfg))
    try:
        return get_provider_client(provider).summarize(request)
    except ProviderClientError as exc:
        raise ProviderError(str(exc)) from exc


def summarize_messages(messages: list[dict], summary_length: int, settings: dict | None = None) -> tuple[str, dict[str, str]]:
    if not messages:
        return EMPTY_SUMMARY_TEXT, {
            'provider': 'none',
            'model': 'none',
            'status': 'empty',
            'fallback': 'false',
        }
    cfg = settings or {}
    provider = _normalize_provider(str(cfg.get('llmProvider', 'ollama')))
    model_name = str(cfg.get('modelName', 'llama3.2:latest')).strip() or 'llama3.2:latest'
    system_message = _resolve_system_message(provider, cfg)
    prompt = _build_prompt(messages, summary_length)
    try:
        text = _summarize_with_provider(provider, model_name, prompt, system_message, cfg)
        if _looks_like_placeholder_response(text):
            raise ProviderError('Provider returned placeholder content instead of a summary')
        text = _extract_valid_summary_text(text)
        return text, {'provider': provider, 'model': model_name, 'status': 'ok', 'fallback': 'false'}
    except ProviderError as exc:
        reason = _redact_provider_error(str(exc), cfg)
        fallback = _demo_summarize_messages(messages, summary_length)
        return (
            'Fallback summary (provider unavailable).\n' f'Reason: {reason}\n\n{fallback}',
            {'provider': provider, 'model': model_name,
                'status': 'fallback', 'fallback': 'true', 'error': reason},
        )
