import contextlib
from datetime import datetime
from uuid import uuid4

from fastapi import FastAPI, HTTPException

from db import get_job, get_setting, init_db, insert_job, list_logs, list_settings, pop_undo, push_undo, set_setting
from logging_service import log_action
from mail_service import add_keyword_tag, demo_search, mark_messages_read, remove_keyword_tag, send_summary_email
from schemas import AppSettings, JobAction, MessageItem, SummaryRequest, SummaryResponse
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
    version="0.1.0",
    lifespan=lifespan,
)

DEFAULT_SETTINGS = AppSettings().model_dump()

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


@app.post("/summaries", response_model=SummaryResponse)
def create_summary(request: SummaryRequest) -> SummaryResponse:
    messages = demo_search(request.criteria)
    summary = summarize_messages(messages, request.summaryLength)
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
    return AppSettings(**merged)


@app.post("/settings")
def save_settings(settings: AppSettings) -> dict[str, str]:
    for key, value in settings.model_dump().items():
        set_setting(key, value)
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
