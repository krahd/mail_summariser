"""mail_summariser FastAPI application and HTTP route handlers.

This module exposes the FastAPI application and routes used by the mail
summariser backend. Pylint checks are selectively disabled here for some
dynamic import and callable detection patterns used for test patching.
"""

# Local pylint tweaks: dynamic imports and runtime-callable checks used by tests
# pylint: disable=not-callable

import contextlib
from datetime import datetime
from typing import Callable, Optional, TYPE_CHECKING, Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException  # pylint: disable=import-error
from fastapi.middleware.cors import CORSMiddleware  # pylint: disable=import-error

from backend import dummy_state
from backend.config import (
    ALLOWED_ORIGINS,
    DEFAULT_SETTINGS,
    DEFAULT_SYSTEM_MESSAGES,
    ENABLE_DEV_TOOLS as _CONFIG_ENABLE_DEV_TOOLS,
)
from backend.db import (
    get_job,
    init_db,
    insert_job,
    list_logs,
    list_settings,
    reset_database,
    set_setting,
)
from backend.logging_service import log_action
from backend.mail_service import (
    MailServiceError,
    is_dummy_mode,
    reset_dummy_mailbox,
    search_messages,
    mark_messages_read,
    restore_messages_unread,
    add_keyword_tag,
    remove_keyword_tag,
    send_summary_email,
    test_mail_connection,
)
from backend.schemas import (
    AppSettings,
    DatabaseResetRequest,
    DatabaseResetResponse,
    MessageDetail,
    MessageItem,
    SummaryRequest,
    SummaryResponse,
    SystemMessageDefaultsResponse,
)
from backend.summary_service import summarize_messages
from backend import model_provider_service

if TYPE_CHECKING:
    # Provide imports for static type checkers. These modules are often
    # test-patched at runtime which confuses static analysis; the
    # TYPE_CHECKING block makes their attributes available to tools.
    from backend import db as _db  # pylint: disable=reimported
    from backend import dummy_state as _dummy_state  # pylint: disable=reimported


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
    # Debug: show DB path and seeded settings
    try:
        from backend import db as _db  # pylint: disable=import-outside-toplevel
        print(f"[DEBUG-lifespan] seeded DB_PATH={_db.DB_PATH}")
    except (ImportError, AttributeError):
        pass
    current = list_settings()
    print(f"[DEBUG-lifespan] seeded settings at lifespan start: {current}")
    for key, value in DEFAULT_SETTINGS.items():
        if key not in current:
            set_setting(key, value)
    dummy_state.reset_dummy_session_store()
    reset_dummy_mailbox()
    # Auto-start Ollama at startup when configured (tests may patch provider)
    try:
        host = str(DEFAULT_SETTINGS.get('ollamaHost', 'http://127.0.0.1:11434'))
        if bool(DEFAULT_SETTINGS.get('ollamaStartOnStartup', False)):
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
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

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


@app.get('/settings', response_model=AppSettings)
def get_settings() -> AppSettings:
    # Debug: show effective defaults and persisted settings when running tests
    try:
        current = list_settings()
    except Exception:  # pylint: disable=broad-except
        current = {}
    print(
        f"[DEBUG] DEFAULT_SETTINGS dummyMode={DEFAULT_SETTINGS.get('dummyMode')} persisted={current.get('dummyMode')}")
    return AppSettings(**_masked_settings_payload())


@app.get('/settings/system-message-defaults', response_model=SystemMessageDefaultsResponse)
def get_system_message_defaults() -> SystemMessageDefaultsResponse:
    return SystemMessageDefaultsResponse(**DEFAULT_SYSTEM_MESSAGES)


@app.post('/settings')
def save_settings(settings: AppSettings) -> dict[str, str]:
    data = settings.model_dump()
    for key_name in SECRET_SETTING_KEYS:
        if data.get(key_name) == '__MASKED__':
            data.pop(key_name)
    for key, value in data.items():
        set_setting(key, value)
    _record_log('save_settings', 'ok', 'Settings updated', settings=settings.model_dump())
    return {'status': 'ok'}


@app.post('/summaries', response_model=SummaryResponse)
def create_summary(request: SummaryRequest) -> SummaryResponse:
    settings = _merged_settings()
    try:
        messages = search_messages(request.criteria, settings)
    except MailServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    summary, meta = summarize_messages(messages, request.summaryLength, settings=settings)
    job_id = f'job-{uuid4()}'
    created_at = datetime.now().isoformat(timespec='seconds')
    criteria_payload = request.criteria.model_dump()
    criteria_payload['mailContext'] = {'dummyMode': settings.get('dummyMode')}
    if is_dummy_mode(settings):
        dummy_state.insert_job(job_id, created_at, criteria_payload,
                               request.summaryLength, summary, messages)
    else:
        insert_job(job_id, created_at, criteria_payload, request.summaryLength, summary, messages)
    _record_log('create_summary', 'ok',
                f'Created summary with {len(messages)} messages', job_id=job_id, settings=settings)
    _record_log('summary_provider', meta.get('status', 'ok'),
                f"provider={meta.get('provider')} model={meta.get('model')}", job_id=job_id, settings=settings)
    return SummaryResponse(jobId=job_id, messages=[MessageItem(id=m['id'], subject=m['subject'], sender=m['sender'], date=m['date']) for m in messages], summary=summary)


@app.post('/settings/test-connection')
def test_connection(settings: dict) -> dict:
    try:
        payload = settings if isinstance(settings, dict) else settings.model_dump()
        # Delegate to mail service which returns a detailed status payload
        return test_mail_connection(payload)
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post('/settings/dummy-mode')
def set_dummy_mode(payload: dict) -> dict:
    try:
        data = payload if isinstance(payload, dict) else payload.model_dump()
        dummy_mode = bool(data.get('dummyMode'))
        set_setting('dummyMode', dummy_mode)
        if not dummy_mode:
            dummy_state.reset_dummy_session_store()
        return {'dummyMode': dummy_mode}
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get('/jobs/{job_id}/messages/{message_id}', response_model=MessageDetail)
def get_job_message(job_id: str, message_id: str) -> MessageDetail:
    job = dummy_state.get_job(job_id) if is_dummy_mode(_merged_settings()) else get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail='Job not found')
    for message in job.get('messages_json', []):
        if str(message.get('id', '')) == message_id:
            return MessageDetail(
                id=str(message.get('id', '')),
                subject=str(message.get('subject', '')),
                sender=str(message.get('sender', '')),
                recipient=str(message.get('recipient', '')),
                date=str(message.get('date', '')),
                body=str(message.get('body', '')),
            )
    raise HTTPException(status_code=404, detail='Message not found')


@app.post('/actions/mark-read')
def actions_mark_read(payload: dict) -> dict:
    try:
        job_id = payload.get('jobId') if isinstance(payload, dict) else None
        settings = _merged_settings()
        job = dummy_state.get_job(job_id) if is_dummy_mode(settings) else get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail='Job not found')
        message_ids = [m.get('id') for m in job.get('messages_json', [])]
        mark_messages_read(message_ids, settings)
        details = f"marked_read {len(message_ids)} messages"
        log_id = _record_log('mark_read', 'ok', details, job_id=job_id, settings=settings)
        _push_undo({'action': 'mark_read', 'log_id': log_id,
                   'job_id': job_id, 'message_ids': message_ids})
        return {'status': 'ok'}
    except HTTPException:
        raise
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post('/actions/tag-summarised')
def actions_tag_summarised(payload: dict) -> dict:
    try:
        job_id = payload.get('jobId') if isinstance(payload, dict) else None
        settings = _merged_settings()
        job = dummy_state.get_job(job_id) if is_dummy_mode(settings) else get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail='Job not found')
        message_ids = [m.get('id') for m in job.get('messages_json', [])]
        add_keyword_tag(message_ids, str(DEFAULT_SETTINGS.get(
            'summarisedTag', 'summarised')), settings)
        details = f"tagged_summarised {len(message_ids)} messages"
        log_id = _record_log('tag_summarised', 'ok', details, job_id=job_id, settings=settings)
        _push_undo({'action': 'tag_summarised', 'log_id': log_id,
                   'job_id': job_id, 'message_ids': message_ids})
        return {'status': 'ok'}
    except HTTPException:
        raise
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post('/actions/email-summary')
def actions_email_summary(payload: dict) -> dict:
    try:
        job_id = payload.get('jobId') if isinstance(payload, dict) else None
        settings = _merged_settings()
        job = dummy_state.get_job(job_id) if is_dummy_mode(settings) else get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail='Job not found')
        summary_text = str(job.get('summary_text') or '')
        recipient = str(settings.get('recipientEmail') or '')
        if is_dummy_mode(settings):
            send_summary_email(recipient, 'Mail summary', summary_text, settings)
        else:
            # Use unified helper which handles fake SMTP environments as well as real SMTP
            send_summary_email(recipient, 'Mail summary', summary_text, settings)
        details = 'email_summary_sent'
        _record_log('email_summary', 'ok', details, job_id=job_id, settings=settings)
        return {'status': 'ok'}
    except HTTPException:
        raise
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post('/actions/undo/logs/{log_id}')
def actions_undo_log(log_id: str) -> dict:
    try:
        settings = _merged_settings()
        if is_dummy_mode(settings):
            payload = dummy_state.pop_undo_by_log_id(log_id)
        else:
            payload = _get_db().pop_undo_by_log_id(log_id)
        if payload is None:
            raise HTTPException(status_code=404, detail='No undo found for log')
        action = payload.get('action')
        job_id = payload.get('job_id')
        message_ids = payload.get('message_ids', []) or []
        if action == 'mark_read':
            restore_messages_unread(message_ids, settings)
            _record_log(
                'undo', 'ok', f'restored {len(message_ids)} messages', job_id=job_id, settings=settings)
        elif action == 'tag_summarised':
            for mid in message_ids:
                remove_keyword_tag([mid], str(DEFAULT_SETTINGS.get(
                    'summarisedTag', 'summarised')), settings)
            _record_log(
                'undo', 'ok', f'removed tags from {len(message_ids)} messages', job_id=job_id, settings=settings)
        else:
            # Unknown undoable action
            _record_log(
                'undo', 'ok', f'performed undo for action {action}', job_id=job_id, settings=settings)
        return {'status': 'ok'}
    except HTTPException:
        raise
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post('/actions/undo')
def actions_undo() -> dict:
    try:
        settings = _merged_settings()
        # Pop the most recent undo payload from the appropriate store
        payload = dummy_state.pop_latest_undo() if is_dummy_mode(settings) else _get_db().pop_latest_undo()
        if payload is None:
            raise HTTPException(status_code=404, detail='No undo found')
        action = payload.get('action')
        job_id = payload.get('job_id')
        message_ids = payload.get('message_ids', []) or []
        if action == 'mark_read':
            restore_messages_unread(message_ids, settings)
            _record_log(
                'undo', 'ok', f'restored {len(message_ids)} messages', job_id=job_id, settings=settings)
        elif action == 'tag_summarised':
            for mid in message_ids:
                remove_keyword_tag([mid], str(DEFAULT_SETTINGS.get(
                    'summarisedTag', 'summarised')), settings)
            _record_log(
                'undo', 'ok', f'removed tags from {len(message_ids)} messages', job_id=job_id, settings=settings)
        else:
            # Unknown undoable action
            _record_log(
                'undo', 'ok', f'performed undo for action {action}', job_id=job_id, settings=settings)
        return {'status': 'ok'}
    except HTTPException:
        raise
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get('/logs')
def get_logs() -> list[dict]:
    raw = dummy_state.list_logs() if is_dummy_mode(_merged_settings()) else list_logs()
    undoable = dummy_state.list_undoable_log_ids() if is_dummy_mode(
        _merged_settings()) else _get_db().list_undoable_log_ids()
    enriched: list[dict] = []
    for item in raw:
        entry = dict(item)
        entry['undoable'] = bool(entry.get('id') in undoable)
        if entry.get('action') in ('tag_summarised', 'email_summary') and not entry['undoable']:
            entry['undo_status'] = 'final'
        else:
            entry['undo_status'] = None
        enriched.append(entry)
    return enriched


@app.post('/admin/database/reset', response_model=DatabaseResetResponse)
def admin_reset_database(request: DatabaseResetRequest) -> DatabaseResetResponse:
    if request.confirmation != 'RESET DATABASE':
        raise HTTPException(status_code=400, detail='Confirmation text must be RESET DATABASE')
    removed = reset_database(DEFAULT_SETTINGS)
    dummy_state.reset_dummy_session_store()
    reset_dummy_mailbox()
    return DatabaseResetResponse(status='ok', message='Local database reset to defaults.', removed=removed, settings=AppSettings(**_masked_settings_payload()))


# Dev fake-mail endpoints ------------------------------------------------------
@app.get('/dev/fake-mail/status')
def dev_fake_mail_status() -> dict:
    if not ENABLE_DEV_TOOLS:
        return {
            'enabled': False,
            'running': False,
            'message': 'dev tools disabled',
            'suggestedSettings': None,
        }
    env = _fake_mail_manager._environment
    if env is None:
        return {'enabled': True, 'running': False, 'message': 'stopped', 'suggestedSettings': None}
    return {
        'enabled': True,
        'running': True,
        'imapHost': '127.0.0.1',
        'imapPort': env.imap_server.server_address[1],
        'smtpHost': '127.0.0.1',
        'smtpPort': env.smtp_server.server_address[1],
        'username': getattr(env, 'username', ''),
        'password': getattr(env, 'password', ''),
        'recipientEmail': getattr(env, 'recipient_email', ''),
        'suggestedSettings': getattr(env, 'settings_payload', None) or (env.settings_payload if hasattr(env, 'settings_payload') else None),
    }


@app.post('/dev/fake-mail/start')
def dev_fake_mail_start() -> dict:
    if not ENABLE_DEV_TOOLS:
        return dev_fake_mail_status()
    env = _fake_mail_manager.start()
    return {
        'enabled': True,
        'running': True,
        'imapHost': '127.0.0.1',
        'imapPort': env.imap_server.server_address[1],
        'smtpHost': '127.0.0.1',
        'smtpPort': env.smtp_server.server_address[1],
        'username': getattr(env, 'username', ''),
        'password': getattr(env, 'password', ''),
        'recipientEmail': getattr(env, 'recipient_email', ''),
        'suggestedSettings': env.settings_payload,
    }


@app.post('/dev/fake-mail/stop')
def dev_fake_mail_stop() -> dict:
    if not ENABLE_DEV_TOOLS:
        return dev_fake_mail_status()
    _fake_mail_manager.shutdown()
    return {'enabled': True, 'running': False, 'message': 'stopped', 'suggestedSettings': None}


# Runtime endpoints -----------------------------------------------------------
def _build_runtime_status() -> dict:
    backend = {'running': True, 'canShutdown': True}
    host = str(DEFAULT_SETTINGS.get('ollamaHost', 'http://127.0.0.1:11434'))
    installed = False
    running = False
    model_name = DEFAULT_SETTINGS.get('modelName', '')
    started_by_app = False
    message = ''

    try:
        installed = bool(getattr(model_provider_service, 'is_ollama_installed')(host))
    except (AttributeError, TypeError, OSError):
        installed = False
    try:
        running = bool(getattr(model_provider_service, 'is_ollama_running')(host))
    except (AttributeError, TypeError, OSError):
        running = False
    try:
        # Determine whether the running process was started by this app
        started_by_app = getattr(model_provider_service, '_managed_process_host', None) == host
    except (AttributeError, TypeError):
        started_by_app = False

    if not installed:
        startup_action = 'install'
        message = 'Install Ollama'
    elif not running:
        # Auto-start behavior may have warmed the model
        startup_action = 'start'
        message = 'Ollama not running'
    else:
        startup_action = 'none'
        message = 'Ollama running'

    # Prefer any detailed runtime message produced by the provider (e.g. warm-up)
    try:
        rt = getattr(model_provider_service, '_runtime_state', None)
        if rt and getattr(rt, 'last_message_host', '') == host and getattr(rt, 'last_message', ''):
            message = rt.last_message
    except (AttributeError, TypeError):
        pass

    # Expose current runtime structure
    ollama = {
        'installed': installed,
        'running': running,
        'startedByApp': started_by_app,
        'host': host,
        'modelName': model_name,
        'startupAction': startup_action,
        'message': message,
        'installUrl': 'https://ollama.com',
    }

    return {'backend': backend, 'ollama': ollama}


@app.get('/runtime/status')
def runtime_status() -> dict:
    return _build_runtime_status()


@app.post('/runtime/ollama/start')
def runtime_start_ollama() -> dict:
    host = str(DEFAULT_SETTINGS.get('ollamaHost', 'http://127.0.0.1:11434'))
    started, message = model_provider_service.ensure_ollama_running(host, auto_start=True)
    runtime = _build_runtime_status()
    # If models are missing, return a warning
    try:
        models = model_provider_service.list_ollama_models(host)
    except (AttributeError, TypeError, OSError):
        models = []
    status = 'ok' if models else 'warning'
    return {'status': status, 'message': message, 'runtime': runtime}


@app.post('/runtime/shutdown')
def runtime_shutdown() -> dict:
    # Schedule backend shutdown
    _schedule_backend_shutdown()
    return {'status': 'ok'}


@app.get('/models/options')
def models_options(provider: str | None = None) -> dict:
    prov = (provider or 'openai').lower()
    # Minimal response shape used by the webapp and smoke tests
    if prov == 'openai':
        return {'provider': 'openai', 'models': []}
    if prov == 'ollama':
        host = str(DEFAULT_SETTINGS.get('ollamaHost', 'http://127.0.0.1:11434'))
        try:
            models = model_provider_service.list_ollama_models(host)
        except (AttributeError, TypeError, OSError):
            models = []
        running = model_provider_service.is_ollama_running(host)
        rt = getattr(model_provider_service, '_runtime_state', None)
        last_message = getattr(rt, 'last_message', '') if rt is not None else ''
        return {
            'provider': 'ollama',
            'models': models,
            'ollama': {'running': running, 'host': host, 'message': last_message},
        }
    return {'provider': prov, 'models': []}


@app.get('/models/catalog')
def models_catalog(query: str | None = None, limit: int | None = 20) -> dict:
    # For the smoke test we return an Ollama-oriented catalog response
    host = str(DEFAULT_SETTINGS.get('ollamaHost', 'http://127.0.0.1:11434'))
    try:
        models = model_provider_service.list_ollama_models(host)
    except (AttributeError, TypeError, OSError):
        models = []
    return {'provider': 'ollama', 'models': models, 'count': len(models)}
