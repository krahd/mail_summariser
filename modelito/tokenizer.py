"""Tokenizer wrapper for optional high-accuracy token counting.

This module provides a small API around `tiktoken` when available and a
lightweight fallback estimator when not. Import `count_tokens(text)` to use.
"""

from __future__ import annotations




def count_tokens(text: str) -> int:
    """Return an estimated token count for `text`.

    If `tiktoken` is installed, use it for accurate counts; otherwise fall
    back to a conservative character-based heuristic.
    """
    if not text:
        return 0
    try:
        import importlib

        tiktoken = importlib.import_module("tiktoken")
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        # heuristic: 4 characters per token on average (conservative)
        return max(1, len(text) // 4)
