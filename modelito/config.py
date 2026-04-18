"""Small config helpers for modelito.

Provides minimal helpers to read JSON/YAML config files and basic host parsing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple


def load_config(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    text = p.read_text(encoding="utf-8")
    # try JSON first
    try:
        return json.loads(text)
    except Exception:
        pass
    # try YAML if available
    try:
        import yaml
        return yaml.safe_load(text) or {}
    except Exception:
        return {}


def parse_host_port(host_url: str) -> Tuple[str, int]:
    # Accept forms like http://host:port or host:port or http://host
    if host_url.startswith("http://") or host_url.startswith("https://"):
        from urllib.parse import urlparse
        u = urlparse(host_url)
        host = u.hostname or "localhost"
        port = int(u.port or 11434)
        return host, port
    if ":" in host_url:
        host, port_s = host_url.split(":", 1)
        try:
            return host, int(port_s)
        except Exception:
            return host, 11434
    return host_url, 11434
