"""
modelito/translation.py

Optional translation helpers. Uses an externally-configured translation endpoint
when `TRANSLATE_API_URL` is set in the environment. This keeps the library
lightweight and avoids hard dependencies.
"""

import json
from typing import Optional
from urllib.request import Request, urlopen

from .utils import get_env_setting, setup_logger

_logger = setup_logger("modelito.translation")


def translate_text(text: str, target_language: str, api_key: Optional[str] = None, timeout: int = 10) -> str:
    """Translate `text` into `target_language` using the configured translation service.

    The translation service URL must be provided via the `TRANSLATE_API_URL` environment
    variable (e.g. a LibreTranslate instance). If not configured, this function raises
    NotImplementedError so callers can provide an alternative implementation.
    """
    url = get_env_setting("TRANSLATE_API_URL")
    if not url:
        raise NotImplementedError("No translation provider configured. Set TRANSLATE_API_URL to enable translation.")

    payload = {"q": text, "source": "auto", "target": target_language, "format": "text"}
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        if not raw.strip():
            return ""
        data = json.loads(raw)
        # Support common response shapes
        if isinstance(data, dict):
            if "translatedText" in data:
                return data["translatedText"]
            if "data" in data and isinstance(data["data"], dict):
                translations = data["data"].get("translations", [])
                if translations:
                    return translations[0].get("translatedText", "")
        # fallback: return raw
        return raw
