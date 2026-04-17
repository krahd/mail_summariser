import os

from backend.config import DEFAULT_SYSTEM_MESSAGES
from backend.llm_provider_clients import ProviderClientError, ProviderRequest, get_provider_client
from backend.model_provider_service import ensure_ollama_running


class ProviderError(Exception):
    pass


RESPONSE_SENTINEL = 'MAIL_SUMMARISER_VALID_V1'
SUPPORTED_PROVIDERS = {'ollama', 'openai', 'anthropic'}


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
    if level <= 2:
        return 'Very terse digest'
    if level <= 4:
        return 'Compact digest'
    if level <= 6:
        return 'Balanced digest'
    if level <= 9:
        return 'Detailed digest'
    if level <= 12:
        return 'Comprehensive digest'
    if level <= 16:
        return 'Expanded digest'
    if level <= 20:
        return 'In-depth digest'
    return 'Extended digest'


def _demo_summarize_messages(messages: list[dict], summary_length: int) -> str:
    level = _effective_detail_level(summary_length)
    intro = _detail_label(level)
    lines = [intro, '', f'Messages summarized: {len(messages)}', '']
    for idx, message in enumerate(messages, start=1):
        body = message.get('body', '').strip().replace('\n', ' ')
        excerpt_length = min(520, 60 + level * 20)
        excerpt = body[:excerpt_length]
        lines.append(f"{idx}. {message['sender']} — {message['subject']}")
        lines.append(f'   {excerpt}')
        if level >= 5:
            lines.append('   Action: review and decide whether a reply is needed.')
        if level >= 11 and message.get('date'):
            lines.append(f"   Timing: message date {message.get('date')}.")
        if level >= 15:
            lines.append('   Priority: consider whether this belongs in today’s response queue.')
        lines.append('')
    if level >= 7:
        lines.extend(['Overall themes:', '- Follow-ups and planning', '- Items that may need a response'])
    if level >= 12:
        lines.extend(['', 'Suggested next steps:', '- Reply to any time-sensitive senders first.', '- Group non-urgent items into one later batch.'])
    if level >= 18:
        lines.extend(['', 'Risk watch:', '- Flag anything that could become overdue if ignored.', '- Check for missing context before replying to complex threads.'])
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
        excerpt = body[:800]
        chunks.append(
            f"{idx}. Subject: {message.get('subject', '')} | From: {message.get('sender', '')} | Date: {message.get('date', '')}\n   Body: {excerpt}"
        )
    return '\n'.join(chunks)


def _normalize_provider(provider: str) -> str:
    normalized = str(provider or 'ollama').strip().lower()
    return normalized if normalized in SUPPORTED_PROVIDERS else 'ollama'


def _resolve_provider_api_key(provider: str, cfg: dict) -> str:
    legacy_key = str(cfg.get('llmApiKey', ''))
    openai_key = str(cfg.get('openaiApiKey', ''))
    anthropic_key = str(cfg.get('anthropicApiKey', ''))
    if legacy_key == '__MASKED__':
        legacy_key = ''
    if openai_key == '__MASKED__':
        openai_key = ''
    if anthropic_key == '__MASKED__':
        anthropic_key = ''
    if provider == 'openai':
        return os.getenv('OPENAI_API_KEY', '').strip() or openai_key or legacy_key
    if provider == 'anthropic':
        return os.getenv('ANTHROPIC_API_KEY', '').strip() or anthropic_key or legacy_key
    return ''


def _resolve_system_message(provider: str, cfg: dict) -> str:
    mapping = {
        'openai': 'openaiSystemMessage',
        'anthropic': 'anthropicSystemMessage',
        'ollama': 'ollamaSystemMessage',
    }
    key = mapping[provider]
    fallback = DEFAULT_SYSTEM_MESSAGES[key]
    return str(cfg.get(key, fallback)).strip() or fallback


def _summarize_with_provider(provider: str, model_name: str, prompt: str, system_message: str, cfg: dict) -> str:
    if provider == 'ollama':
        ollama_host = str(cfg.get('ollamaHost', 'http://127.0.0.1:11434'))
        auto_start = bool(cfg.get('ollamaAutoStart', True))
        running, message = ensure_ollama_running(ollama_host, auto_start)
        if not running:
            raise ProviderError(message)
        request = ProviderRequest(model=model_name, prompt=prompt, system_message=system_message, host=ollama_host, auto_start=auto_start)
    else:
        request = ProviderRequest(
            model=model_name,
            prompt=prompt,
            system_message=system_message,
            api_key=_resolve_provider_api_key(provider, cfg),
        )
    try:
        return get_provider_client(provider).summarize(request)
    except ProviderClientError as exc:
        raise ProviderError(str(exc)) from exc


def summarize_messages(messages: list[dict], summary_length: int, settings: dict | None = None) -> tuple[str, dict[str, str]]:
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
        fallback = _demo_summarize_messages(messages, summary_length)
        return (
            'Fallback summary (provider unavailable).\n'
            f'Reason: {exc}\n\n{fallback}',
            {'provider': provider, 'model': model_name, 'status': 'fallback', 'fallback': 'true', 'error': str(exc)},
        )
