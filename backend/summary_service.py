

import modelito



ProviderError = modelito.LLMProviderError


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


def _post_json(url: str, payload: dict, headers: dict | None = None, timeout: float = 15.0) -> dict:
    """Simple POST helper used by tests (can be patched). Signature kept minimal (url, payload).

    Returns parsed JSON or raises ProviderError on network/parse error.
    """
    import json as _json
    from urllib.request import Request, urlopen
    from urllib.error import URLError

    hdrs = headers or {"Content-Type": "application/json"}
    body = _json.dumps(payload).encode("utf-8")
    req = Request(url=url, data=body, headers=hdrs, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            if not raw.strip():
                return {}
            return _json.loads(raw)
    except URLError as exc:
        raise ProviderError(f"Network error posting to {url}: {exc}") from exc
    except Exception as exc:
        raise ProviderError(f"Error parsing response from {url}: {exc}") from exc


def ensure_ollama_running(settings: dict) -> tuple[bool, str]:
    """Check whether Ollama is reachable at the configured host. Returns (running, message).

    This helper is kept for test compatibility and may be patched in tests.
    """
    host = str((settings or {}).get("ollamaHost", "http://127.0.0.1:11434")).rstrip("/")
    from urllib.request import urlopen
    from urllib.error import URLError

    try:
        urlopen(f"{host}/api/version", timeout=1.2)
        return True, "ok"
    except URLError as exc:
        return False, str(exc)
    except Exception as exc:
        return False, str(exc)


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









def summarize_messages(messages: list[dict], summary_length: int, settings: dict | None = None) -> tuple[str, dict[str, str]]:
    cfg = settings or {}
    provider_name = str(cfg.get("llmProvider", "ollama")).strip().lower()
    model_name = str(cfg.get("modelName", "llama3.2:latest")).strip() or "llama3.2:latest"
    prompt = _build_prompt(messages, summary_length)
    try:
        provider = modelito.get_provider(provider_name)
        text = provider.summarize(
            messages,
            {
                **cfg,
                "modelName": model_name,
                "prompt": prompt,
                "_post_json": _post_json,
            },
        )
        if _looks_like_placeholder_response(text):
            raise ProviderError("Provider returned placeholder content instead of a summary")
        text = _extract_valid_summary_text(text)
        return text, {
            "provider": provider_name,
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
                "provider": provider_name,
                "model": model_name,
                "status": "fallback",
                "fallback": "true",
                "error": str(exc),
            },
        )
