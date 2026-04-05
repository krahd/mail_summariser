import json
import os
from urllib.error import URLError
from urllib.request import Request, urlopen

from config import DEFAULT_SYSTEM_MESSAGES
from model_provider_service import ensure_ollama_running


class ProviderError(Exception):
    pass


RESPONSE_SENTINEL = "MAIL_SUMMARISER_VALID_V1"


def _looks_like_placeholder_response(text: str) -> bool:
    normalized = (text or "").strip().lower()
    if not normalized:
        return True
    placeholder_markers = (
        "please provide the emails",
        "please share the emails",
        "i'm ready to summarize",
        "i am ready to summarize",
        "go ahead and provide the emails",
    )
    return any(marker in normalized for marker in placeholder_markers)


def _extract_valid_summary_text(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        raise ProviderError("Provider returned empty content")

    lines = [line.strip() for line in raw.splitlines()]
    if not lines or lines[0] != RESPONSE_SENTINEL:
        raise ProviderError("Provider response missing validation sentinel")

    summary = "\n".join(raw.splitlines()[1:]).strip()
    if not summary:
        raise ProviderError("Provider returned sentinel but no summary content")
    return summary


def _demo_summarize_messages(messages: list[dict], summary_length: int) -> str:
    level = _effective_detail_level(summary_length)
    intro = _detail_label(level)

    lines = [intro, "", f"Messages summarized: {len(messages)}", ""]

    for idx, message in enumerate(messages, start=1):
        body = message.get("body", "").strip().replace("\n", " ")
        excerpt_length = min(520, 60 + level * 20)
        excerpt = body[:excerpt_length]
        lines.append(f"{idx}. {message['sender']} — {message['subject']}")
        lines.append(f"   {excerpt}")
        if level >= 5:
            lines.append("   Action: review and decide whether a reply is needed.")
        if level >= 11 and message.get("date"):
            lines.append(f"   Timing: message date {message.get('date')}.")
        if level >= 15:
            lines.append("   Priority: consider whether this belongs in today’s response queue.")
        lines.append("")

    if level >= 7:
        lines.append("Overall themes:")
        lines.append("- Follow-ups and planning")
        lines.append("- Items that may need a response")
    if level >= 12:
        lines.extend(
            [
                "",
                "Suggested next steps:",
                "- Reply to any time-sensitive senders first.",
                "- Group non-urgent items into one later batch.",
            ]
        )
    if level >= 18:
        lines.extend(
            [
                "",
                "Risk watch:",
                "- Flag anything that could become overdue if ignored.",
                "- Check for missing context before replying to complex threads.",
            ]
        )

    return "\n".join(lines).strip()


def _build_prompt(messages: list[dict], summary_length: int) -> str:
    level = _effective_detail_level(summary_length)
    target_lines = max(3, min(48, 4 + level * 2))
    chunks = [
        "Summarize the email list into concise actionable points.",
        f"Requested detail level: {summary_length}. Keep around {target_lines} bullet lines.",
        "Focus on priority items, deadlines, and likely responses needed.",
        f"First line must be exactly: {RESPONSE_SENTINEL}",
        "On following lines, provide only the summary.",
        "",
        "Emails:",
    ]
    for idx, message in enumerate(messages, start=1):
        body = message.get("body", "").strip().replace("\n", " ")
        excerpt = body[:800]
        chunks.append(
            f"{idx}. Subject: {message.get('subject', '')} | From: {message.get('sender', '')} | Date: {message.get('date', '')}\n"
            f"   Body: {excerpt}"
        )
    return "\n".join(chunks)


def _effective_detail_level(summary_length: int) -> int:
    return max(1, min(int(summary_length), 24))


def _detail_label(level: int) -> str:
    if level <= 2:
        return "Very terse digest"
    if level <= 4:
        return "Compact digest"
    if level <= 6:
        return "Balanced digest"
    if level <= 9:
        return "Detailed digest"
    if level <= 12:
        return "Comprehensive digest"
    if level <= 16:
        return "Expanded digest"
    if level <= 20:
        return "In-depth digest"
    return "Extended digest"


def _post_json(url: str, payload: dict, headers: dict[str, str], timeout: float = 25.0) -> dict:
    req = Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise ProviderError(str(exc)) from exc


def _summarize_with_openai(model_name: str, api_key: str, prompt: str, system_message: str) -> str:
    if not api_key.strip():
        raise ProviderError("OpenAI API key is missing")

    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "system",
                "content": system_message,
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    response = _post_json(
        "https://api.openai.com/v1/chat/completions",
        payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key.strip()}",
        },
    )
    try:
        return response["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError(f"Unexpected OpenAI response: {response}") from exc


def _summarize_with_anthropic(model_name: str, api_key: str, prompt: str, system_message: str) -> str:
    if not api_key.strip():
        raise ProviderError("Anthropic API key is missing")

    payload = {
        "model": model_name,
        "max_tokens": 900,
        "system": system_message,
        "messages": [{"role": "user", "content": prompt}],
    }
    response = _post_json(
        "https://api.anthropic.com/v1/messages",
        payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key.strip(),
            "anthropic-version": "2023-06-01",
        },
    )
    try:
        blocks = response.get("content", [])
        text_blocks = [block.get("text", "") for block in blocks if block.get("type") == "text"]
        return "\n".join(text_blocks).strip()
    except (AttributeError, TypeError) as exc:
        raise ProviderError(f"Unexpected Anthropic response: {response}") from exc


def _summarize_with_ollama(model_name: str, ollama_host: str, auto_start: bool, prompt: str, system_message: str) -> str:
    running, message = ensure_ollama_running(ollama_host, auto_start)
    if not running:
        raise ProviderError(message)

    response = _post_json(
        f"{ollama_host.rstrip('/')}/api/generate",
        {
            "model": model_name,
            "system": system_message,
            "prompt": prompt,
            "stream": False,
        },
        headers={"Content-Type": "application/json"},
        timeout=45.0,
    )
    text = str(response.get("response", "")).strip()
    if not text:
        raise ProviderError(f"Empty Ollama response: {response}")
    return text


def summarize_messages(messages: list[dict], summary_length: int, settings: dict | None = None) -> tuple[str, dict[str, str]]:
    cfg = settings or {}
    provider = str(cfg.get("llmProvider", "ollama")).strip().lower()
    model_name = str(cfg.get("modelName", "llama3.2:latest")).strip() or "llama3.2:latest"
    ollama_host = str(cfg.get("ollamaHost", "http://127.0.0.1:11434"))
    auto_start = bool(cfg.get("ollamaAutoStart", True))
    openai_system_message = str(
        cfg.get("openaiSystemMessage", DEFAULT_SYSTEM_MESSAGES["openaiSystemMessage"])
    ).strip() or DEFAULT_SYSTEM_MESSAGES["openaiSystemMessage"]
    anthropic_system_message = str(
        cfg.get("anthropicSystemMessage", DEFAULT_SYSTEM_MESSAGES["anthropicSystemMessage"])
    ).strip() or DEFAULT_SYSTEM_MESSAGES["anthropicSystemMessage"]
    ollama_system_message = str(
        cfg.get("ollamaSystemMessage", DEFAULT_SYSTEM_MESSAGES["ollamaSystemMessage"])
    ).strip() or DEFAULT_SYSTEM_MESSAGES["ollamaSystemMessage"]

    # API key resolution: provider-specific key, then env var, then legacy shared key.
    legacy_key = str(cfg.get("llmApiKey", ""))
    openai_key = str(cfg.get("openaiApiKey", ""))
    anthropic_key = str(cfg.get("anthropicApiKey", ""))

    if legacy_key == "__MASKED__":
        legacy_key = ""
    if openai_key == "__MASKED__":
        openai_key = ""
    if anthropic_key == "__MASKED__":
        anthropic_key = ""

    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "").strip() or openai_key or legacy_key
    elif provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip() or anthropic_key or legacy_key
    else:
        api_key = ""

    prompt = _build_prompt(messages, summary_length)

    try:
        if provider == "openai":
            text = _summarize_with_openai(model_name, api_key, prompt, openai_system_message)
        elif provider == "anthropic":
            text = _summarize_with_anthropic(model_name, api_key, prompt, anthropic_system_message)
        else:
            text = _summarize_with_ollama(model_name, ollama_host, auto_start, prompt, ollama_system_message)

        # Some models occasionally return a generic "please provide emails" placeholder.
        if _looks_like_placeholder_response(text):
            raise ProviderError("Provider returned placeholder content instead of a summary")

        text = _extract_valid_summary_text(text)

        return text, {
            "provider": provider,
            "model": model_name,
            "status": "ok",
            "fallback": "false",
        }
    except ProviderError as exc:
        fallback = _demo_summarize_messages(messages, summary_length)
        return (
            "Fallback summary (provider unavailable).\n"
            f"Reason: {exc}\n\n{fallback}",
            {
                "provider": provider,
                "model": model_name,
                "status": "fallback",
                "fallback": "true",
                "error": str(exc),
            },
        )
