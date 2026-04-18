"""Simple connector utilities to manage conversation history and system messages.

This module provides a small, framework-agnostic connector that maintains per-
conversation histories (or a shared history) and prepares prompts for providers.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pathlib import Path
from .exceptions import LLMProviderError



from .tokenizer import count_tokens


def _estimate_tokens(text: str) -> int:
    """Estimate token count for a text using the tokenizer wrapper."""
    try:
        return int(count_tokens(text or ""))
    except Exception:
        # defensive fallback
        if not text:
            return 0
        return max(1, len(text) // 4)


class OllamaConnector:
    def __init__(self, provider: Any, shared_history: bool = False, system_message_file: Optional[str] = None, max_history_messages: int = 20, max_history_tokens: Optional[int] = None):
        self.provider = provider
        self.shared_history = shared_history
        self.max_history_messages = int(max_history_messages or 20)
        self.max_history_tokens = int(
            max_history_tokens) if max_history_tokens is not None else None
        self._histories: Dict[str, List[Dict[str, str]]] = {}
        self._system_message = None
        if system_message_file:
            p = Path(system_message_file)
            if p.exists():
                try:
                    self._system_message = p.read_text(encoding="utf-8").strip()
                except Exception:
                    self._system_message = None

    def _conv_key(self, conv_id: Optional[str]) -> str:
        return "__shared__" if self.shared_history else (conv_id or "default")

    def clear_history(self, conv_id: Optional[str] = None) -> None:
        key = self._conv_key(conv_id)
        self._histories.pop(key, None)

    def set_system_message(self, text: Optional[str]) -> None:
        self._system_message = text

    def _ensure_system(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        if not self._system_message:
            return messages
        if not messages:
            return [{"role": "system", "content": self._system_message}]
        first = messages[0]
        if first.get("role") == "system":
            return messages
        return [{"role": "system", "content": self._system_message}] + messages

    def _message_tokens(self, message: Dict[str, str]) -> int:
        # Count tokens in message content and a tiny overhead for role/metadata
        return _estimate_tokens(message.get("content", "")) + 1

    def _total_tokens(self, messages: List[Dict[str, str]]) -> int:
        return sum(self._message_tokens(m) for m in messages)

    def add_to_history(self, conv_id: Optional[str], role: str, content: str) -> None:
        key = self._conv_key(conv_id)
        hist = self._histories.setdefault(key, [])
        hist.append({"role": role, "content": content})
        # trim by count
        if len(hist) > self.max_history_messages:
            del hist[: len(hist) - self.max_history_messages]
        # trim by tokens if configured
        if self.max_history_tokens is not None:
            # preserve system message at index 0 if present
            while True:
                total = self._total_tokens(hist)
                if total <= self.max_history_tokens:
                    break
                # remove the oldest non-system message
                if hist and hist[0].get("role") == "system":
                    # drop the next message instead if possible
                    if len(hist) > 1:
                        del hist[1]
                    else:
                        # nothing to trim
                        break
                else:
                    del hist[0]

    def get_history(self, conv_id: Optional[str]) -> List[Dict[str, str]]:
        return list(self._histories.get(self._conv_key(conv_id), []))

    def trim_history_by_tokens(self, messages: List[Dict[str, str]], max_tokens: int) -> List[Dict[str, str]]:
        """Return a trimmed copy of messages where total tokens <= max_tokens.

        Preserves a leading system message when present.
        """
        if max_tokens is None or max_tokens <= 0:
            return messages
        msgs = list(messages)
        # if first is system, keep it and trim the rest
        system = None
        if msgs and msgs[0].get("role") == "system":
            system = msgs.pop(0)
        # trim from the left (oldest) until within budget
        while self._total_tokens(([system] if system else []) + msgs) > max_tokens and msgs:
            del msgs[0]
        if system:
            return [system] + msgs
        return msgs

    def build_prompt(self, conv_id: Optional[str], new_messages: Optional[List[Dict[str, str]]] = None, include_history: bool = True, max_prompt_tokens: Optional[int] = None) -> List[Dict[str, str]]:
        hist = self.get_history(conv_id) if include_history else []
        if new_messages:
            hist = hist + new_messages
        # apply message count trimming first
        if len(hist) > self.max_history_messages:
            hist = hist[-self.max_history_messages:]
        # apply token trimming for the prompt if requested
        if max_prompt_tokens is not None:
            hist = self.trim_history_by_tokens(hist, max_prompt_tokens)
        hist = self._ensure_system(hist)
        return hist

    def send_sync(self, conv_id: Optional[str], new_messages: List[Dict[str, str]], settings: Optional[Dict] = None) -> str:
        messages = self.build_prompt(conv_id, new_messages=new_messages, include_history=True, max_prompt_tokens=(
            settings or {}).get("max_prompt_tokens"))
        try:
            resp = self.provider.summarize(messages, settings=settings)
        except Exception as exc:
            raise LLMProviderError(f"Provider call failed: {exc}") from exc
        # append user messages and assistant response to history
        for m in (new_messages or []):
            role = m.get("role", "user")
            self.add_to_history(conv_id, role, m.get("content", ""))
        self.add_to_history(conv_id, "assistant", resp)
        return resp
