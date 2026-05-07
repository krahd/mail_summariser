"""mail_summariser FastAPI application and HTTP route handlers.

This module exposes the FastAPI application and routes used by the mail
summariser backend. Pylint checks are selectively disabled here for some
dynamic import and callable detection patterns used for test patching.
"""

# Local pylint tweaks: dynamic imports and runtime-callable checks used by tests
# pylint: disable=not-callable

import contextlib
import logging
from datetime import datetime
from typing import Callable, Optional, TYPE_CHECKING, Any
from uuid import uuid4

from fastapi import FastAPI  # pylint: disable=import-error
from fastapi.middleware.cors import CORSMiddleware  # pylint: disable=import-error

from backend import dummy_state
from backend.config import (
    ALLOWED_ORIGINS,
    ALLOWED_ORIGIN_REGEX,
    DEFAULT_SETTINGS,
    ENABLE_DEV_TOOLS as _CONFIG_ENABLE_DEV_TOOLS,
)
from backend.db import (
    init_db,
    list_settings,
    set_setting,
)
from backend.logging_service import log_action
from backend.mail_service import (
    is_dummy_mode,
    reset_dummy_mailbox,
)
from backend.schemas import (
    SummaryRequest,
)
from backend import model_provider_service
from backend.routers_actions import router as actions_router
from backend.routers_devtools import router as devtools_router
from backend.routers_runtime_models import router as runtime_models_router
from backend.routers_settings import router as settings_router
from backend.routers_summaries import router as summaries_router

if TYPE_CHECKING:
    # Provide imports for static type checkers. These modules are often
    # test-patched at runtime which confuses static analysis; the
    # TYPE_CHECKING block makes their attributes available to tools.
    from backend import db as _db  # pylint: disable=reimported
    from backend import dummy_state as _dummy_state  # pylint: disable=reimported


logger = logging.getLogger(__name__)
__all__ = ['app', 'SummaryRequest']


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    # If tests imported a top-level 'db' module and set its DB_PATH, honor it here so
    # the app uses the same database file as the tests.
    import sys as _sys  # pylint: disable=import-outside-toplevel
    if 'db' in _sys.modules:
        # copy DB_PATH from top-level db module into backend.db
        try:
            # Import inside lifespan to respect test-time top-level patching
            from backend import db as _backend_db  # pylint: disable=import-outside-toplevel
            _backend_db.DB_PATH = _sys.modules['db'].DB_PATH
        except (ImportError, AttributeError):
            pass
    init_db()
    # If a top-level model_provider_service module was imported by tests and patched,
    # prefer that module so the app observes the test patches.
    if 'model_provider_service' in _sys.modules:
        try:
            # Replace the reference used by this module with the test-patched one
            globals()['model_provider_service'] = _sys.modules['model_provider_service']
        except (ImportError, AttributeError):
            pass
    # If tests imported a top-level dummy_state module, prefer that instance
    if 'dummy_state' in _sys.modules:
        try:
            globals()['dummy_state'] = _sys.modules['dummy_state']
        except (ImportError, AttributeError):
            pass
    # Ensure database contains the known defaults at startup (add missing defaults only)
    try:
        from backend import db as _db  # pylint: disable=import-outside-toplevel
        logger.info("seeded_db_path=%s", _db.DB_PATH)
    except (ImportError, AttributeError):
        pass
    current = list_settings()
    logger.debug("seeded_settings=%s", current)
    for key, value in DEFAULT_SETTINGS.items():
        if key not in current:
            set_setting(key, value)
    dummy_state.reset_dummy_session_store()
    reset_dummy_mailbox()
    # Auto-start Ollama at startup when configured (tests may patch provider)
    try:
        settings = _merged_settings()
        host = str(settings.get('ollamaHost') or DEFAULT_SETTINGS.get(
            'ollamaHost', 'http://127.0.0.1:11434'))
        if bool(settings.get('ollamaStartOnStartup', False)):
            try:
                # Best-effort; allow provider to handle subprocess mocking in tests
                model_provider_service.ensure_ollama_running(host, auto_start=True)
            except (AttributeError, TypeError, OSError):
                # Ignore common issues when test-patching the provider or starting subprocesses
                pass
    except (AttributeError, TypeError):
        pass
    yield


app = FastAPI(title='mail_summariser backend', version='0.0.5', lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=ALLOWED_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)
app.include_router(settings_router)
app.include_router(summaries_router)
app.include_router(actions_router)
app.include_router(devtools_router)
app.include_router(runtime_models_router)

SECRET_SETTING_KEYS = ('openaiApiKey', 'anthropicApiKey', 'imapPassword', 'smtpPassword')


# Expose a mutable flag at module level so tests can toggle dev tools.
ENABLE_DEV_TOOLS = _CONFIG_ENABLE_DEV_TOOLS


# Backend runtime/shutdown state used by tests
_backend_shutdown_requested: bool = False
_shutdown_callback: Optional[Callable[[], None]] = None  # pylint: disable=invalid-name


# Fake mail manager (dev tools) -------------------------------------------------
class _FakeMailManager:
    def __init__(self) -> None:
        self._environment = None

    def shutdown(self) -> None:
        if self._environment is None:
            return
        try:
            # FakeMailEnvironment provides stop()/start() or context manager methods
            if hasattr(self._environment, 'stop') and callable(self._environment.stop):
                self._environment.stop()
        finally:
            self._environment = None

    def start(self):
        if self._environment is not None:
            return self._environment
        from backend.fake_mail_server import FakeMailEnvironment  # pylint: disable=import-outside-toplevel

        env = FakeMailEnvironment()
        # Prefer explicit start() when available
        if hasattr(env, 'start') and callable(env.start):
            env.start()
        self._environment = env
        return env


_fake_mail_manager = _FakeMailManager()


def _reset_dummy_sandbox() -> None:
    # Clear in-memory dummy stores and reset fake mailbox state
    try:
        dummy_state.reset_dummy_session_store()
    except (AttributeError, TypeError):
        pass
    try:
        reset_dummy_mailbox()
    except (AttributeError, TypeError):
        pass


# Some runtime patterns here use test-time injected callbacks and dynamic imports
# which confuse static checks; disable the not-callable check locally.
# pylint: disable=not-callable, import-outside-toplevel
def _schedule_backend_shutdown(delay_seconds: float = 0.1) -> None:
    """Schedule a backend shutdown callback after a short delay."""
    global _backend_shutdown_requested  # pylint: disable=global-statement
    _backend_shutdown_requested = True
    if _shutdown_callback is None:
        return
    import threading

    def _run() -> None:
        try:
            if callable(_shutdown_callback):
                # _shutdown_callback is typed as Optional[Callable], guard with callable()
                _shutdown_callback()  # pylint: disable=not-callable
        except Exception:  # pylint: disable=broad-except
            # Swallow errors from callbacks; shutdown should be best-effort
            pass

    t = threading.Timer(delay_seconds, _run)
    t.daemon = True
    t.start()



def _merged_settings() -> dict[str, Any]:
    return DEFAULT_SETTINGS | list_settings()


def _masked_settings_payload() -> dict[str, Any]:
    merged = _merged_settings()
    legacy_key = str(merged.get('llmApiKey', ''))
    if legacy_key:
        if not str(merged.get('openaiApiKey', '')):
            merged['openaiApiKey'] = legacy_key
        if not str(merged.get('anthropicApiKey', '')):
            merged['anthropicApiKey'] = legacy_key
    for key_name in SECRET_SETTING_KEYS:
        if merged.get(key_name, ''):
            merged[key_name] = '__MASKED__'
    return merged


def _new_log_id() -> str:
    return f'log-{uuid4()}'


def _get_db() -> Any:
    """Return the backend.db module (supports test-time patching).

    Uses a dynamic import at runtime but provides a static name for
    type-checkers via the TYPE_CHECKING imports above.
    """
    import importlib
    module = importlib.import_module("backend")
    return getattr(module, "db")


def _record_log(action: str, status: str, details: str, *, job_id: str | None = None, settings: dict[str, Any] | None = None) -> str:
    if settings is not None and is_dummy_mode(settings):
        log_id = _new_log_id()
        dummy_state.insert_log(log_id=log_id, timestamp=datetime.now().isoformat(
            timespec='seconds'), action=action, status=status, details=details, job_id=job_id)
        return log_id
    return log_action(action, status, details, job_id=job_id)


def _push_undo(payload: dict) -> None:
    created_at = datetime.now().isoformat(timespec='seconds')
    if is_dummy_mode(_merged_settings()):
        dummy_state.push_undo(payload, created_at)
    else:
        from backend import db as _db

        _db.push_undo(payload, created_at)


@app.get('/health')
def health() -> dict[str, str]:
    return {'status': 'ok'}
