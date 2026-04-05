import os
import sys
from pathlib import Path


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]

APP_DIR = Path(__file__).resolve().parent


def _resolve_data_dir() -> Path:
    """Resolve a writable data directory for both source and packaged runs."""
    override = os.getenv("MAIL_SUMMARISER_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    if getattr(sys, "frozen", False):
        return Path.home() / ".mail-summariser"

    return APP_DIR / "data"


DATA_DIR = _resolve_data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "mail_summariser.sqlite3"

ALLOWED_ORIGINS = _split_csv(
    os.getenv(
        "ALLOWED_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:8766,http://localhost:8766",
    )
)
API_KEY = os.getenv("API_KEY", "").strip()
API_KEY_HEADER = os.getenv("API_KEY_HEADER", "X-API-Key").strip() or "X-API-Key"
ENABLE_DEV_TOOLS = os.getenv("MAIL_SUMMARISER_ENABLE_DEV_TOOLS", "false").lower() in ("1", "true", "yes", "on")

# Provider-specific API key env vars — take precedence over DB settings
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()

# Default application settings
DEFAULT_SETTINGS = {
    "dummyMode": os.getenv("DUMMY_MODE", "true").lower() in ("1", "true", "yes", "on"),
    "imapHost": os.getenv("IMAP_HOST", ""),
    "imapPort": int(os.getenv("IMAP_PORT", "993")),
    "imapUseSSL": os.getenv("IMAP_USE_SSL", "true").lower() in ("1", "true", "yes", "on"),
    "imapPassword": os.getenv("IMAP_PASSWORD", os.getenv("MAIL_PASSWORD", "")),
    "smtpHost": os.getenv("SMTP_HOST", ""),
    "smtpPort": int(os.getenv("SMTP_PORT", "465")),
    "smtpUseSSL": os.getenv("SMTP_USE_SSL", "true").lower() in ("1", "true", "yes", "on"),
    "smtpPassword": os.getenv("SMTP_PASSWORD", os.getenv("MAIL_PASSWORD", "")),
    "username": os.getenv("MAIL_USERNAME", ""),
    "recipientEmail": os.getenv("RECIPIENT_EMAIL", ""),
    "summarisedTag": os.getenv("SUMMARISED_TAG", "summarised"),
    "llmProvider": os.getenv("LLM_PROVIDER", "ollama"),
    "openaiApiKey": OPENAI_API_KEY,
    "anthropicApiKey": ANTHROPIC_API_KEY,
    "ollamaHost": os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"),
    "ollamaAutoStart": os.getenv("OLLAMA_AUTO_START", "true").lower() in ("1", "true", "yes", "on"),
    "ollamaStartOnStartup": os.getenv("OLLAMA_START_ON_STARTUP", "false").lower() in ("1", "true", "yes", "on"),
    "ollamaStopOnExit": os.getenv("OLLAMA_STOP_ON_EXIT", "false").lower() in ("1", "true", "yes", "on"),
    "modelName": os.getenv("MODEL_NAME", "llama3.2:latest"),
    "backendBaseURL": os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:8766"),
}

legacy_llm_api_key = os.getenv("LLM_API_KEY", "").strip()
if legacy_llm_api_key:
    DEFAULT_SETTINGS["llmApiKey"] = legacy_llm_api_key
