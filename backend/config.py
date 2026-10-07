import os
import sys
import tempfile

# Process-level lock: this cannot be disabled by an HTTP settings request.
DEMO_MODE = os.getenv("MAIL_SUMMARISER_DEMO", "").lower() in ("1", "true", "yes", "on")
_DEMO_DATA = tempfile.TemporaryDirectory(prefix="mail-summariser-demo-") if DEMO_MODE else None
from pathlib import Path


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(',') if item.strip()]


APP_DIR = Path(__file__).resolve().parent


def _resolve_data_dir() -> Path:
    if _DEMO_DATA is not None:
        return Path(_DEMO_DATA.name)
    override = os.getenv('MAIL_SUMMARISER_DATA_DIR', '').strip()
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, 'frozen', False):
        return Path.home() / '.mail_summariser'
    return APP_DIR / 'data'


DATA_DIR = _resolve_data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / 'mail_summariser.sqlite3'

ALLOWED_ORIGINS = _split_csv(
    os.getenv(
        'ALLOWED_ORIGINS',
        'http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:8766,http://localhost:8766',
    )
)
ALLOWED_ORIGIN_REGEX = os.getenv(
    'ALLOWED_ORIGIN_REGEX',
    r'^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$',
).strip()
ENABLE_DEV_TOOLS = os.getenv('MAIL_SUMMARISER_ENABLE_DEV_TOOLS',
                             'false').lower() in ('1', 'true', 'yes', 'on')

def _env(name: str, default: str = '') -> str:
    return default if DEMO_MODE else os.getenv(name, default)


DEFAULT_OPENAI_SYSTEM_MESSAGE = _env(
    'OPENAI_SYSTEM_MESSAGE',
    'Create compact, practical email digests. Prioritise deadlines, requests, blockers, and follow-up actions. Group related threads, avoid greetings and filler, do not invent facts, and make the next step obvious when one exists.',
).strip()
DEFAULT_ANTHROPIC_SYSTEM_MESSAGE = _env(
    'ANTHROPIC_SYSTEM_MESSAGE',
    'Create concise, practical email summaries with clear action cues. Highlight deadlines, owners, approvals, risks, and reply-needed items. Keep wording neutral, specific, and free of invented details.',
).strip()
DEFAULT_OLLAMA_SYSTEM_MESSAGE = _env(
    'OLLAMA_SYSTEM_MESSAGE',
    'Create compact, practical email digests that focus on priorities, deadlines, blockers, and follow-up actions. Group related messages, keep the output scannable, and prefer specific next steps over generic commentary.',
).strip()

DEFAULT_SYSTEM_MESSAGES = {
    'ollamaSystemMessage': DEFAULT_OLLAMA_SYSTEM_MESSAGE,
    'openaiSystemMessage': DEFAULT_OPENAI_SYSTEM_MESSAGE,
    'anthropicSystemMessage': DEFAULT_ANTHROPIC_SYSTEM_MESSAGE,
}

DEFAULT_SETTINGS = {
    'dummyMode': _env('DUMMY_MODE', 'true').lower() in ('1', 'true', 'yes', 'on'),
    'imapHost': _env('IMAP_HOST', ''),
    'imapPort': int(_env('IMAP_PORT', '993')),
    'imapUseSSL': _env('IMAP_USE_SSL', 'true').lower() in ('1', 'true', 'yes', 'on'),
    'imapPassword': _env('IMAP_PASSWORD', _env('MAIL_PASSWORD', '')),
    'smtpHost': _env('SMTP_HOST', ''),
    'smtpPort': int(_env('SMTP_PORT', '465')),
    'smtpUseSSL': _env('SMTP_USE_SSL', 'true').lower() in ('1', 'true', 'yes', 'on'),
    'smtpPassword': _env('SMTP_PASSWORD', _env('MAIL_PASSWORD', '')),
    'username': _env('MAIL_USERNAME', ''),
    'recipientEmail': _env('RECIPIENT_EMAIL', ''),
    'summarisedTag': _env('SUMMARISED_TAG', 'summarised'),
    'archiveMailbox': _env('ARCHIVE_MAILBOX', 'Archive'),
    'safeMode': _env('SAFE_MODE', 'true').lower() in ('1', 'true', 'yes', 'on'),
    'llmProvider': _env('LLM_PROVIDER', 'ollama'),
    'openaiApiKey': _env('OPENAI_API_KEY', '').strip(),
    'anthropicApiKey': _env('ANTHROPIC_API_KEY', '').strip(),
    'ollamaHost': _env('OLLAMA_HOST', 'http://127.0.0.1:11434'),
    'ollamaAutoStart': _env('OLLAMA_AUTO_START', 'true').lower() in ('1', 'true', 'yes', 'on'),
    'ollamaStartOnStartup': _env('OLLAMA_START_ON_STARTUP', 'false').lower() in ('1', 'true', 'yes', 'on'),
    'ollamaStopOnExit': _env('OLLAMA_STOP_ON_EXIT', 'false').lower() in ('1', 'true', 'yes', 'on'),
    'ollamaSystemMessage': DEFAULT_OLLAMA_SYSTEM_MESSAGE,
    'openaiSystemMessage': DEFAULT_OPENAI_SYSTEM_MESSAGE,
    'anthropicSystemMessage': DEFAULT_ANTHROPIC_SYSTEM_MESSAGE,
    'modelName': _env('MODEL_NAME', 'llama3.2:latest'),
    'backendBaseURL': _env('BACKEND_BASE_URL', 'http://127.0.0.1:8766'),
}

legacy_llm_api_key = _env('LLM_API_KEY', '').strip()
if legacy_llm_api_key:
    DEFAULT_SETTINGS['llmApiKey'] = legacy_llm_api_key


# Demo never inherits mailbox/provider credentials, addresses, or runtime settings.
if DEMO_MODE:
    DEFAULT_SETTINGS = {
        'dummyMode': True, 'safeMode': True, 'llmProvider': 'ollama',
        'imapHost': '', 'imapPort': 993, 'imapUseSSL': True, 'imapPassword': '',
        'smtpHost': '', 'smtpPort': 465, 'smtpUseSSL': True, 'smtpPassword': '',
        'username': '', 'recipientEmail': '', 'openaiApiKey': '', 'anthropicApiKey': '',
        'mailAccounts': [], 'summarisedTag': 'summarised', 'archiveMailbox': 'Archive',
        'ollamaHost': '', 'ollamaAutoStart': False, 'ollamaStartOnStartup': False,
        'ollamaStopOnExit': False, 'modelName': '', 'backendBaseURL': '',
        **DEFAULT_SYSTEM_MESSAGES,
    }
    ENABLE_DEV_TOOLS = False
