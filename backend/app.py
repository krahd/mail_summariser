import contextlib
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config import ALLOWED_ORIGINS, API_KEY, API_KEY_HEADER, DEFAULT_SETTINGS
from db import get_job, get_setting, init_db, insert_job, list_logs, list_settings, pop_undo, push_undo, set_setting
from logging_service import log_action
from mail_service import add_keyword_tag, demo_search, mark_messages_read, remove_keyword_tag, send_summary_email
from model_provider_service import (
    ensure_ollama_running,
    get_model_download_status,
    list_downloadable_ollama_models,
    list_ollama_models,
    list_remote_models,
    start_ollama_model_download,
)
from schemas import AppSettings, JobAction, MessageItem, ModelDownloadRequest, SummaryRequest, SummaryResponse
from summary_service import summarize_messages

@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    current = list_settings()
    for key, value in DEFAULT_SETTINGS.items():
        if key not in current:
            set_setting(key, value)
    yield


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


@app.post("/summaries", response_model=SummaryResponse)
def create_summary(request: SummaryRequest) -> SummaryResponse:
    messages = demo_search(request.criteria)
    settings = DEFAULT_SETTINGS | list_settings()
    summary, summary_meta = summarize_messages(messages, request.summaryLength, settings=settings)
    job_id = f"job-{uuid4()}"
    created_at = datetime.now().isoformat(timespec="seconds")

    insert_job(
        job_id=job_id,
        created_at=created_at,
        criteria=request.criteria.model_dump(),
        summary_length=request.summaryLength,
        summary_text=summary,
        messages=messages,
    )
    log_action("create_summary", "ok",
               f"Created summary with {len(messages)} messages", job_id=job_id)
    if summary_meta.get("status") == "fallback":
        detail = f"provider={summary_meta.get('provider')} model={summary_meta.get('model')} error={summary_meta.get('error', '')}"
        log_action("summary_provider", "warning", detail, job_id=job_id)
    else:
        detail = f"provider={summary_meta.get('provider')} model={summary_meta.get('model')}"
        log_action("summary_provider", "ok", detail, job_id=job_id)

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
    job = get_job(action.jobId)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    message_ids = [m["id"] for m in job["messages_json"]]
    mark_messages_read(message_ids)
    push_undo(
        {"type": "mark_read", "message_ids": message_ids, "job_id": action.jobId},
        created_at=datetime.now().isoformat(timespec="seconds"),
    )
    log_action("mark_read", "ok",
               f"Marked {len(message_ids)} messages as read", job_id=action.jobId)
    return {"status": "ok"}


@app.post("/actions/tag-summarised")
def tag_summarised(action: JobAction) -> dict[str, str]:
    job = get_job(action.jobId)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    message_ids = [m["id"] for m in job["messages_json"]]
    tag = get_setting("summarisedTag", "summarised")
    add_keyword_tag(message_ids, tag)
    push_undo(
        {"type": "tag_add", "message_ids": message_ids, "tag": tag, "job_id": action.jobId},
        created_at=datetime.now().isoformat(timespec="seconds"),
    )
    log_action("tag_summarised", "ok",
               f"Added tag '{tag}' to {len(message_ids)} messages", job_id=action.jobId)
    return {"status": "ok"}


@app.post("/actions/email-summary")
def email_summary(action: JobAction) -> dict[str, str]:
    job = get_job(action.jobId)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    recipient = get_setting("recipientEmail", "")
    if not recipient:
        raise HTTPException(status_code=400, detail="No recipientEmail configured")

    send_summary_email(
        recipient=recipient,
        subject=f"Mail summary for {action.jobId}",
        body=job["summary_text"],
    )
    push_undo(
        {"type": "email_sent", "recipient": recipient, "job_id": action.jobId},
        created_at=datetime.now().isoformat(timespec="seconds"),
    )
    log_action("email_summary", "ok", f"Sent summary email to {recipient}", job_id=action.jobId)
    return {"status": "ok"}


@app.get("/logs")
def get_logs() -> list[dict]:
    return list_logs()


@app.get("/settings", response_model=AppSettings)
def get_settings() -> AppSettings:
    merged = DEFAULT_SETTINGS | list_settings()
    legacy_key = str(merged.get("llmApiKey", ""))
    if legacy_key:
        if not str(merged.get("openaiApiKey", "")):
            merged["openaiApiKey"] = legacy_key
        if not str(merged.get("anthropicApiKey", "")):
            merged["anthropicApiKey"] = legacy_key

    # Never return real provider keys over the wire.
    if merged.get("openaiApiKey", ""):
        merged["openaiApiKey"] = "__MASKED__"
    if merged.get("anthropicApiKey", ""):
        merged["anthropicApiKey"] = "__MASKED__"

    return AppSettings(**merged)


@app.get("/models/options")
def get_model_options(provider: str | None = None) -> dict[str, object]:
    merged = DEFAULT_SETTINGS | list_settings()
    selected_provider = (provider or merged.get("llmProvider", "ollama")).strip().lower()

    if selected_provider == "ollama":
        ollama_host = str(merged.get("ollamaHost", DEFAULT_SETTINGS["ollamaHost"]))
        auto_start = bool(merged.get("ollamaAutoStart", True))
        running, message = ensure_ollama_running(ollama_host, auto_start)
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
    data = settings.model_dump()
    # __MASKED__ means "keep existing stored key".
    for key_name in ("openaiApiKey", "anthropicApiKey"):
        if data.get(key_name) == "__MASKED__":
            data.pop(key_name)
    for key, value in data.items():
        set_setting(key, value)

    if settings.llmProvider.strip().lower() == "ollama":
        running, message = ensure_ollama_running(settings.ollamaHost, settings.ollamaAutoStart)
        status_label = "ok" if running else "warning"
        log_action("ollama_status", status_label, message)

    log_action("save_settings", "ok", "Settings updated")
    return {"status": "ok"}


@app.post("/actions/undo")
def undo_last_action() -> dict[str, str]:
    last = pop_undo()
    if last is None:
        log_action("undo", "noop", "Nothing to undo")
        return {"status": "noop"}

    action_type = last.get("type")
    if action_type == "tag_add":
        remove_keyword_tag(last["message_ids"], last["tag"])
        log_action(
            "undo", "ok", f"Removed tag '{last['tag']}' from prior job", job_id=last.get("job_id"))
        return {"status": "ok"}

    if action_type == "mark_read":
        log_action(
            "undo",
            "partial",
            "mark_read undo placeholder: implement restoring prior unread/read flags in real mail backend",
            job_id=last.get("job_id"),
        )
        return {"status": "partial"}

    if action_type == "email_sent":
        log_action(
            "undo",
            "partial",
            "Email cannot be unsent; action recorded only",
            job_id=last.get("job_id"),
        )
        return {"status": "partial"}

    log_action("undo", "noop", f"No undo handler for {action_type}", job_id=last.get("job_id"))
    return {"status": "noop"}
