"""modelito.timeout

Utilities to estimate remote model timeouts based on a small catalog.

This is a lightweight approximation of BatLLM's timeout catalog logic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def _catalog_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "ollama_remote_timeout_catalog.json"


def load_catalog() -> Dict[str, Any]:
    p = _catalog_path()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    # fallback minimal catalog
    return {
        "size_bands": [
            {"max_input_tokens": 2048, "timeout_seconds": 15},
            {"max_input_tokens": 8192, "timeout_seconds": 60},
            {"max_input_tokens": 32768, "timeout_seconds": 300},
        ],
        "family_overrides": {},
        "keyword_adjustments": {},
    }


def estimate_remote_timeout(model_name: str | None, input_tokens: int = 2048, concurrency: int = 1) -> int:
    """Estimate a conservative timeout (seconds) for a remote model request.

    - model_name: name of the model (used to detect family or keywords)
    - input_tokens: approximate number of input tokens
    - concurrency: number of parallel requests expected
    """
    if not model_name:
        return 60
    model = model_name.lower()
    catalog = load_catalog()
    size_bands = catalog.get("size_bands", []) or []

    base_timeout = None
    for band in size_bands:
        if input_tokens <= int(band.get("max_input_tokens", 0)):
            base_timeout = int(band.get("timeout_seconds", 60))
            break
    if base_timeout is None:
        # use largest band
        if size_bands:
            base_timeout = int(size_bands[-1].get("timeout_seconds", 300))
        else:
            base_timeout = 60

    multiplier = 1.0
    fam_over = catalog.get("family_overrides", {}) or {}
    for fam, mult in fam_over.items():
        if fam in model:
            try:
                multiplier = float(mult)
            except Exception:
                pass
            break

    kw_adj = catalog.get("keyword_adjustments", {}) or {}
    for kw, mult in kw_adj.items():
        if kw in model:
            try:
                # prefer the largest multiplier found
                multiplier = max(multiplier, float(mult))
            except Exception:
                pass

    timeout = int(max(5, base_timeout * multiplier * max(1, int(concurrency))))
    return timeout
