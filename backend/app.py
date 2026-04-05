import contextlib
import os
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config import ALLOWED_ORIGINS, API_KEY, API_KEY_HEADER, DEFAULT_SETTINGS, DEFAULT_SYSTEM_MESSAGES, ENABLE_DEV_TOOLS
from db import (
    get_job,
    get_setting,
    init_db,
    insert_job,
    list_logs,
    list_settings,
    list_undoable_log_ids,
    pop_undo,
    pop_undo_by_log_id,
    push_undo,
    reset_database,
    set_setting,
)
from logging_service import log_action
import dummy_state
from fake_mail_server import FakeMailServerManager
from mail_service import (
    MailServiceError,
    add_keyword_tag,
    get_dummy_outbox,
    is_dummy_mode,
    mark_messages_read,
    remove_keyword_tag,
    reset_dummy_mailbox,
    restore_messages_unread,
    search_messages,
    send_summary_email,
    test_mail_connection,
)
from model_provider_service import (
    ensure_ollama_running,
    get_ollama_runtime_status,
    get_model_download_status,
    list_downloadable_ollama_models,
    list_ollama_models,
    list_remote_models,
    run_ollama_startup_check,
    start_and_warm_ollama,
    start_ollama_model_download,
    stop_managed_ollama,
)
from schemas import (
    AppSettings,
    DatabaseResetRequest,
    DatabaseResetResponse,
    DummyModeUpdate,
    FakeMailStatusResponse,
    JobAction,
    MessageItem,
    ModelDownloadRequest,
    RuntimeActionResponse,
    RuntimeStatusResponse,
    SystemMessageDefaultsResponse,
    SummaryRequest,
    SummaryResponse,
)
from summary_service import summarize_messages

_backend_shutdown_requested = False
_shutdown_callback: Callable[[], None] | None = None
_fake_mail_manager = FakeMailServerManager()


def _reset_dummy_sandbox() -> None:
    dummy_state.reset_dummy_session_store()
    reset_dummy_mailbox()


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    global _backend_shutdown_requested
    _backend_shutdown_requested = False
    init_db()
    current = list_settings()
    for key, value in DEFAULT_SETTINGS.items():
        if key not in current:
            set_setting(key, value)
    _reset_dummy_sandbox()
    startup_settings = _merged_settings()
    run_ollama_startup_check(
        provider=str(startup_settings.get("llmProvider", "ollama")),
        ollama_host=str(startup_settings.get("ollamaHost", DEFAULT_SETTINGS["ollamaHost"])),
        model_name=str(startup_settings.get("modelName", DEFAULT_SETTINGS["modelName"])),
        start_on_startup=bool(startup_settings.get("ollamaStartOnStartup", False)),
    )
    try:
        yield
    finally:
        shutdown_settings = _merged_settings()
        _reset_dummy_sandbox()
        _fake_mail_manager.shutdown()
        stop_managed_ollama(bool(shutdown_settings.get("ollamaStopOnExit", False)))


app = FastAPI(
    title="Mail Summariser Backend",
    version="0.0.3",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PUBLIC_PATH_PREFIXES = (
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/web",
)

MAIL_CONTEXT_KEYS = ("dummyMode",)
SECRET_SETTING_KEYS = ("openaiApiKey", "anthropicApiKey", "imapPassword", "smtpPassword")


@app.middleware("http")
async def enforce_api_key(request: Request, call_next):
    # Keep local development friction low: auth activates only when API_KEY is set.
    if not API_KEY or request.method == "OPTIONS":
        return await call_next(request)

    path = request.url.path
    if path == "/" or path.startswith(PUBLIC_PATH_PREFIXES):
        return await call_next(request)

    provided_key = request.headers.get(API_KEY_HEADER, "")
    if provided_key != API_KEY:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Invalid or missing API key"},
        )

    return await call_next(request)



def _resolve_webapp_dir() -> Path:
    # When bundled with PyInstaller, static files are unpacked under _MEIPASS.
    meipass_dir = getattr(sys, "_MEIPASS", None)
    if meipass_dir:
        bundled = Path(meipass_dir) / "webapp"
        if bundled.exists():
            return bundled
    return Path(__file__).resolve().parent.parent / "webapp"


WEBAPP_DIR = _resolve_webapp_dir()
if WEBAPP_DIR.exists():
    app.mount("/web", StaticFiles(directory=WEBAPP_DIR, html=True), name="web")

# remove deprecated block:
# @app.on_event("startup")
# def startup() -> None:
#     init_db()
#     current = list_settings()
#     for key, value in DEFAULT_SETTINGS.items():
#         if key not in current:
#             set_setting(key, value)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_model=None)
def root():
    index_file = WEBAPP_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {
        "status": "ok",
        "message": "Backend is running. Visit /docs for API docs.",
    }


def _merged_settings() -> dict[str, object]:
    return DEFAULT_SETTINGS | list_settings()


def _masked_settings_payload() -> dict[str, object]:
    merged = _merged_settings()
    legacy_key = str(merged.get("llmApiKey", ""))
    if legacy_key:
        if not str(merged.get("openaiApiKey", "")):
            merged["openaiApiKey"] = legacy_key
        if not str(merged.get("anthropicApiKey", "")):
            merged["anthropicApiKey"] = legacy_key

    for key_name in SECRET_SETTING_KEYS:
        if merged.get(key_name, ""):
            merged[key_name] = "__MASKED__"

    return merged


def _active_dummy_mode() -> bool:
    return is_dummy_mode(_merged_settings())


def _new_log_id() -> str:
    return f"log-{uuid4()}"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _record_log(
    action: str,
    status: str,
    details: str,
    *,
    job_id: str | None = None,
    settings: dict[str, object] | None = None,
    persistent: bool = False,
) -> str:
    if not persistent and settings is not None and is_dummy_mode(settings):
        log_id = _new_log_id()
        dummy_state.insert_log(
            log_id=log_id,
            timestamp=_now_iso(),
            action=action,
            status=status,
            details=details,
            job_id=job_id,
        )
        return log_id
    return log_action(action, status, details, job_id=job_id)


def _insert_job_for_active_mode(
    *,
    job_id: str,
    created_at: str,
    criteria: dict[str, object],
    summary_length: int,
    summary_text: str,
    messages: list[dict[str, object]],
    settings: dict[str, object],
) -> None:
    if is_dummy_mode(settings):
        dummy_state.insert_job(job_id, created_at, criteria, summary_length, summary_text, messages)
        return
    insert_job(job_id, created_at, criteria, summary_length, summary_text, messages)


def _get_job_for_active_mode(job_id: str) -> dict | None:
    if _active_dummy_mode():
        return dummy_state.get_job(job_id)
    return get_job(job_id)


def _list_logs_for_active_mode() -> list[dict]:
    if _active_dummy_mode():
        return dummy_state.list_logs()
    return list_logs()


def _list_undoable_log_ids_for_active_mode() -> set[str]:
    if _active_dummy_mode():
        return dummy_state.list_undoable_log_ids()
    return list_undoable_log_ids()


def _push_undo_for_mode(payload: dict[str, object], created_at: str, settings: dict[str, object]) -> None:
    if is_dummy_mode(settings):
        dummy_state.push_undo(payload, created_at)
        return
    push_undo(payload, created_at)


def _pop_undo_for_active_mode() -> dict[str, object] | None:
    if _active_dummy_mode():
        return dummy_state.pop_undo()
    return pop_undo()


def _pop_undo_by_log_id_for_active_mode(log_id: str) -> dict[str, object] | None:
    if _active_dummy_mode():
        return dummy_state.pop_undo_by_log_id(log_id)
    return pop_undo_by_log_id(log_id)


def _fake_mail_status_payload() -> dict[str, object]:
    settings = _merged_settings()
    backend_base_url = str(settings.get("backendBaseURL", DEFAULT_SETTINGS["backendBaseURL"]))
    return _fake_mail_manager.status(ENABLE_DEV_TOOLS, backend_base_url)


def _runtime_status_payload() -> dict[str, object]:
    settings = _merged_settings()
    return {
        "backend": {
            "running": True,
            "canShutdown": not _backend_shutdown_requested,
        },
        "ollama": get_ollama_runtime_status(
            provider=str(settings.get("llmProvider", "ollama")),
            ollama_host=str(settings.get("ollamaHost", DEFAULT_SETTINGS["ollamaHost"])),
            model_name=str(settings.get("modelName", DEFAULT_SETTINGS["modelName"])),
        ),
    }


def _perform_backend_shutdown() -> None:
    callback = _shutdown_callback
    if callback is not None:
        callback()
        return
    os.kill(os.getpid(), signal.SIGTERM)


def _schedule_backend_shutdown(delay_seconds: float = 0.2) -> None:
    global _backend_shutdown_requested
    if _backend_shutdown_requested:
        return
    _backend_shutdown_requested = True

    def _delayed_shutdown() -> None:
        time.sleep(delay_seconds)
        _perform_backend_shutdown()

    threading.Thread(target=_delayed_shutdown, daemon=True).start()


def _job_mail_context(settings: dict[str, object]) -> dict[str, object]:
    return {key: settings.get(key) for key in MAIL_CONTEXT_KEYS}


def _resolve_masked_settings(data: dict[str, object]) -> dict[str, object]:
    resolved = data.copy()
    current = _merged_settings()
    for key_name in SECRET_SETTING_KEYS:
        if resolved.get(key_name) == "__MASKED__":
            resolved[key_name] = current.get(key_name, "")
    return resolved


def _job_effective_mail_settings(job: dict | None = None, payload: dict | None = None) -> dict[str, object]:
    settings = _merged_settings()
    mail_context: dict[str, object] = {}
    if job is not None:
        criteria = job.get("criteria_json", {})
        if isinstance(criteria, dict):
            candidate = criteria.get("mailContext", {})
            if isinstance(candidate, dict):
                mail_context = candidate
    if payload is not None:
        candidate = payload.get("mail_context", {})
        if isinstance(candidate, dict):
            mail_context = candidate
    for key in MAIL_CONTEXT_KEYS:
        if key in mail_context:
            settings[key] = mail_context[key]
    return settings


@app.post("/summaries", response_model=SummaryResponse)
def create_summary(request: SummaryRequest) -> SummaryResponse:
    settings = _merged_settings()
    try:
        messages = search_messages(request.criteria, settings)
    except MailServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    summary, summary_meta = summarize_messages(messages, request.summaryLength, settings=settings)
    job_id = f"job-{uuid4()}"
    created_at = datetime.now().isoformat(timespec="seconds")
    criteria_payload = request.criteria.model_dump()
    criteria_payload["mailContext"] = _job_mail_context(settings)

    _insert_job_for_active_mode(
        job_id=job_id,
        created_at=created_at,
        criteria=criteria_payload,
        summary_length=request.summaryLength,
        summary_text=summary,
        messages=messages,
        settings=settings,
    )
    _record_log(
        "create_summary",
        "ok",
        f"Created summary with {len(messages)} messages",
        job_id=job_id,
        settings=settings,
    )
    if summary_meta.get("status") == "fallback":
        detail = f"provider={summary_meta.get('provider')} model={summary_meta.get('model')} error={summary_meta.get('error', '')}"
        _record_log("summary_provider", "warning", detail, job_id=job_id, settings=settings)
    else:
        detail = f"provider={summary_meta.get('provider')} model={summary_meta.get('model')}"
        _record_log("summary_provider", "ok", detail, job_id=job_id, settings=settings)

    return SummaryResponse(
        jobId=job_id,
        messages=[
            MessageItem(id=m["id"], subject=m["subject"], sender=m["sender"], date=m["date"])
            for m in messages
        ],
        summary=summary,
    )


@app.post("/actions/mark-read")
def mark_read(action: JobAction) -> dict[str, str]:
    job = _get_job_for_active_mode(action.jobId)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    settings = _job_effective_mail_settings(job)
    message_ids = [m["id"] for m in job["messages_json"]]
    try:
        undo_data = mark_messages_read(message_ids, settings)
    except MailServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    action_log_id = _record_log(
        "mark_read",
        "ok",
        f"Marked {len(message_ids)} messages as read",
        job_id=action.jobId,
        settings=settings,
    )
    _push_undo_for_mode(
        {
            "type": "mark_read",
            "message_ids": message_ids,
            "restore_unread_ids": undo_data.get("restore_unread_ids", []),
            "job_id": action.jobId,
            "log_id": action_log_id,
            "mail_context": _job_mail_context(settings),
        },
        created_at=datetime.now().isoformat(timespec="seconds"),
        settings=settings,
    )
    return {"status": "ok"}


@app.post("/actions/tag-summarised")
def tag_summarised(action: JobAction) -> dict[str, str]:
    job = _get_job_for_active_mode(action.jobId)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    settings = _job_effective_mail_settings(job)
    message_ids = [m["id"] for m in job["messages_json"]]
    tag = str(settings.get("summarisedTag", get_setting("summarisedTag", "summarised")))
    try:
        undo_data = add_keyword_tag(message_ids, tag, settings)
    except MailServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    action_log_id = _record_log(
        "tag_summarised",
        "ok",
        f"Added tag '{tag}' to {len(message_ids)} messages",
        job_id=action.jobId,
        settings=settings,
    )
    _push_undo_for_mode(
        {
            "type": "tag_add",
            "message_ids": message_ids,
            "added_message_ids": undo_data.get("added_message_ids", []),
            "tag": tag,
            "job_id": action.jobId,
            "log_id": action_log_id,
            "mail_context": _job_mail_context(settings),
        },
        created_at=datetime.now().isoformat(timespec="seconds"),
        settings=settings,
    )
    return {"status": "ok"}


@app.post("/actions/email-summary")
def email_summary(action: JobAction) -> dict[str, str]:
    job = _get_job_for_active_mode(action.jobId)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    settings = _job_effective_mail_settings(job)
    recipient = get_setting("recipientEmail", "")
    if not recipient:
        raise HTTPException(status_code=400, detail="No recipientEmail configured")

    try:
        send_summary_email(
            recipient=recipient,
            subject=f"Mail summary for {action.jobId}",
            body=job["summary_text"],
            settings=settings,
        )
    except MailServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _record_log(
        "email_summary",
        "ok",
        f"Sent summary email to {recipient}",
        job_id=action.jobId,
        settings=settings,
    )
    return {"status": "ok"}


@app.get("/logs")
def get_logs() -> list[dict]:
    logs = _list_logs_for_active_mode()
    undoable_log_ids = _list_undoable_log_ids_for_active_mode()
    undo_actions = {"mark_read", "tag_summarised", "email_summary"}
    for log in logs:
        is_undoable = log["id"] in undoable_log_ids
        log["undoable"] = is_undoable
        if is_undoable:
            log["undo_status"] = "undoable"
        elif log["action"] in undo_actions:
            log["undo_status"] = "final"
        else:
            log["undo_status"] = "not_undoable"
    return logs


@app.get("/settings", response_model=AppSettings)
def get_settings() -> AppSettings:
    return AppSettings(**_masked_settings_payload())


@app.get("/settings/system-message-defaults", response_model=SystemMessageDefaultsResponse)
def get_system_message_defaults() -> SystemMessageDefaultsResponse:
    return SystemMessageDefaultsResponse(**DEFAULT_SYSTEM_MESSAGES)


@app.post("/admin/database/reset", response_model=DatabaseResetResponse)
def admin_reset_database(request: DatabaseResetRequest) -> DatabaseResetResponse:
    if request.confirmation != "RESET DATABASE":
        raise HTTPException(status_code=400, detail="Confirmation text must be RESET DATABASE")

    removed = reset_database(DEFAULT_SETTINGS)
    _reset_dummy_sandbox()
    return DatabaseResetResponse(
        status="ok",
        message="Local database reset to defaults.",
        removed=removed,
        settings=AppSettings(**_masked_settings_payload()),
    )


@app.get("/runtime/status", response_model=RuntimeStatusResponse)
def get_runtime_status() -> RuntimeStatusResponse:
    return RuntimeStatusResponse(**_runtime_status_payload())


@app.post("/runtime/ollama/start", response_model=RuntimeActionResponse)
def runtime_start_ollama() -> RuntimeActionResponse:
    settings = _merged_settings()
    status, message = start_and_warm_ollama(
        model_name=str(settings.get("modelName", DEFAULT_SETTINGS["modelName"])),
        ollama_host=str(settings.get("ollamaHost", DEFAULT_SETTINGS["ollamaHost"])),
    )
    if status == "error":
        log_action("runtime_start_ollama", "error", message)
        raise HTTPException(status_code=400, detail=message)

    log_action("runtime_start_ollama", status, message)
    return RuntimeActionResponse(
        status=status,
        message=message,
        runtime=RuntimeStatusResponse(**_runtime_status_payload()),
    )


@app.post("/runtime/shutdown")
def runtime_shutdown() -> dict[str, str]:
    if _backend_shutdown_requested:
        return {"status": "warning", "message": "Mail Summariser shutdown is already in progress"}

    _schedule_backend_shutdown()
    _record_log("runtime_shutdown", "ok", "Shutdown requested", persistent=True)
    return {"status": "ok", "message": "Mail Summariser is shutting down"}


@app.get("/dev/fake-mail/status", response_model=FakeMailStatusResponse)
def fake_mail_status() -> FakeMailStatusResponse:
    return FakeMailStatusResponse(**_fake_mail_status_payload())


@app.post("/dev/fake-mail/start", response_model=FakeMailStatusResponse)
def fake_mail_start() -> FakeMailStatusResponse:
    if not ENABLE_DEV_TOOLS:
        raise HTTPException(status_code=404, detail="Developer fake mail server is disabled")
    settings = _merged_settings()
    backend_base_url = str(settings.get("backendBaseURL", DEFAULT_SETTINGS["backendBaseURL"]))
    return FakeMailStatusResponse(**_fake_mail_manager.start(True, backend_base_url))


@app.post("/dev/fake-mail/stop", response_model=FakeMailStatusResponse)
def fake_mail_stop() -> FakeMailStatusResponse:
    if not ENABLE_DEV_TOOLS:
        raise HTTPException(status_code=404, detail="Developer fake mail server is disabled")
    settings = _merged_settings()
    backend_base_url = str(settings.get("backendBaseURL", DEFAULT_SETTINGS["backendBaseURL"]))
    return FakeMailStatusResponse(**_fake_mail_manager.stop(True, backend_base_url))


@app.get("/models/options")
def get_model_options(provider: str | None = None) -> dict[str, object]:
    merged = DEFAULT_SETTINGS | list_settings()
    selected_provider = (provider or merged.get("llmProvider", "ollama")).strip().lower()

    if selected_provider == "ollama":
        ollama_host = str(merged.get("ollamaHost", DEFAULT_SETTINGS["ollamaHost"]))
        model_name = str(merged.get("modelName", DEFAULT_SETTINGS["modelName"]))
        runtime_status = get_ollama_runtime_status(selected_provider, ollama_host, model_name)
        running = bool(runtime_status["running"])
        message = str(runtime_status["message"])
        models = list_ollama_models(ollama_host) if running else []
        return {
            "provider": "ollama",
            "models": models,
            "ollama": {
                "running": running,
                "host": ollama_host,
                "message": message,
            },
        }

    return {
        "provider": selected_provider,
        "models": list_remote_models(selected_provider),
        "ollama": None,
    }


@app.get("/models/catalog")
def get_model_catalog(query: str = "", limit: int = 60) -> dict[str, object]:
    models = list_downloadable_ollama_models(query=query, limit=limit)
    return {
        "provider": "ollama",
        "models": models,
        "count": len(models),
    }


@app.post("/models/download")
def download_model(request: ModelDownloadRequest) -> dict[str, str]:
    settings = DEFAULT_SETTINGS | list_settings()
    ollama_host = str(settings.get("ollamaHost", DEFAULT_SETTINGS["ollamaHost"]))
    auto_start = bool(settings.get("ollamaAutoStart", True))

    running, message = ensure_ollama_running(ollama_host, auto_start)
    if not running:
        log_action("download_model", "error", message)
        raise HTTPException(status_code=400, detail=message)

    ok, pull_message = start_ollama_model_download(request.name, ollama_host)
    if not ok:
        log_action("download_model", "error", pull_message)
        raise HTTPException(status_code=400, detail=pull_message)

    log_action("download_model", "ok", pull_message)
    return {"status": "ok", "message": pull_message}


@app.get("/models/download/status")
def download_status(name: str) -> dict[str, str]:
    settings = DEFAULT_SETTINGS | list_settings()
    ollama_host = str(settings.get("ollamaHost", DEFAULT_SETTINGS["ollamaHost"]))
    return get_model_download_status(name, ollama_host)


@app.post("/settings")
def save_settings(settings: AppSettings) -> dict[str, str]:
    previous_settings = _merged_settings()
    dummy_mode_changed = bool(previous_settings.get("dummyMode", True)) != bool(settings.dummyMode)
    data = settings.model_dump()
    # __MASKED__ means "keep existing stored key".
    for key_name in SECRET_SETTING_KEYS:
        if data.get(key_name) == "__MASKED__":
            data.pop(key_name)
    for key, value in data.items():
        set_setting(key, value)

    if settings.llmProvider.strip().lower() == "ollama":
        runtime_status = get_ollama_runtime_status(settings.llmProvider, settings.ollamaHost, settings.modelName)
        status_label = "ok" if runtime_status["running"] else "warning"
        _record_log("ollama_status", status_label, str(runtime_status["message"]), settings=data)

    if dummy_mode_changed:
        _reset_dummy_sandbox()

    _record_log("save_settings", "ok", "Settings updated", settings=settings.model_dump())
    return {"status": "ok"}


@app.post("/settings/dummy-mode")
def save_dummy_mode(update: DummyModeUpdate) -> dict[str, object]:
    set_setting("dummyMode", update.dummyMode)
    _reset_dummy_sandbox()
    label = "enabled" if update.dummyMode else "disabled"
    _record_log("dummy_mode", "ok", f"Dummy mode {label}", settings={"dummyMode": update.dummyMode})
    return {"status": "ok", "dummyMode": update.dummyMode}


@app.post("/settings/test-connection")
def settings_test_connection(settings: AppSettings) -> dict[str, object]:
    try:
        payload = _resolve_masked_settings(settings.model_dump())
        result = test_mail_connection(payload)
    except MailServiceError as exc:
        _record_log("test_connection", "error", str(exc), settings=payload)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    mode = "dummy" if is_dummy_mode(payload) else "imap"
    _record_log("test_connection", "ok", f"Connection test succeeded in {mode} mode", settings=payload)
    return result


@app.post("/actions/undo")
def undo_last_action() -> dict[str, str]:
    last = _pop_undo_for_active_mode()
    if last is None:
        _record_log("undo", "noop", "Nothing to undo", settings=_merged_settings())
        return {"status": "noop"}

    action_type = last.get("type")
    settings = _job_effective_mail_settings(payload=last)
    if action_type == "tag_add":
        try:
            remove_keyword_tag(last.get("added_message_ids", []), last["tag"], settings)
        except MailServiceError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _record_log(
            "undo", "ok", f"Removed tag '{last['tag']}' from prior job", job_id=last.get("job_id"), settings=settings)
        return {"status": "ok"}

    if action_type == "mark_read":
        try:
            restore_messages_unread(last.get("restore_unread_ids", []), settings)
        except MailServiceError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _record_log(
            "undo",
            "ok",
            f"Restored unread state for {len(last.get('restore_unread_ids', []))} messages",
            job_id=last.get("job_id"),
            settings=settings,
        )
        return {"status": "ok"}

    _record_log(
        "undo",
        "noop",
        f"No undo handler for {action_type}",
        job_id=last.get("job_id"),
        settings=settings,
    )
    return {"status": "noop"}


@app.post("/actions/undo/logs/{log_id}")
def undo_action_by_log(log_id: str) -> dict[str, str]:
    payload = _pop_undo_by_log_id_for_active_mode(log_id)
    if payload is None:
        raise HTTPException(status_code=400, detail="Selected log item is not undoable")

    action_type = payload.get("type")
    settings = _job_effective_mail_settings(payload=payload)
    if action_type == "tag_add":
        try:
            remove_keyword_tag(payload.get("added_message_ids", []), payload["tag"], settings)
        except MailServiceError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _record_log(
            "undo",
            "ok",
            f"Removed tag '{payload['tag']}' from selected log item",
            job_id=payload.get("job_id"),
            settings=settings,
        )
        return {"status": "ok"}

    if action_type == "mark_read":
        try:
            restore_messages_unread(payload.get("restore_unread_ids", []), settings)
        except MailServiceError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _record_log(
            "undo",
            "ok",
            f"Restored unread state for {len(payload.get('restore_unread_ids', []))} messages",
            job_id=payload.get("job_id"),
            settings=settings,
        )
        return {"status": "ok"}

    _record_log(
        "undo",
        "noop",
        f"No undo handler for {action_type}",
        job_id=payload.get("job_id"),
        settings=settings,
    )
    return {"status": "noop"}
