from __future__ import annotations
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from backend.db import get_job, insert_job
from backend.mail_service import MailServiceError, is_dummy_mode, search_messages
from backend.router_context import get_app_module
from backend.schemas import MessageDetail, MessageItem, SummaryRequest, SummaryResponse
from backend.summary_service import EMPTY_SUMMARY_TEXT, summarize_messages


router = APIRouter()


def _safe_summary_length(value: int) -> int:
    return max(1, min(int(value), 24))


@router.post('/summaries', response_model=SummaryResponse)
def create_summary(request: SummaryRequest) -> SummaryResponse:
    app_module = get_app_module()

    settings = app_module._merged_settings()
    summary_length = _safe_summary_length(request.summaryLength)
    try:
        messages = search_messages(request.criteria, settings)
    except MailServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if messages:
        summary, meta = summarize_messages(messages, summary_length, settings=settings)
    else:
        summary = EMPTY_SUMMARY_TEXT
        meta = {'provider': 'none', 'model': 'none', 'status': 'empty', 'fallback': 'false'}
    job_id = f'job-{uuid4()}'
    created_at = datetime.now().isoformat(timespec='seconds')
    criteria_payload = request.criteria.model_dump()
    criteria_payload['mailContext'] = {'dummyMode': settings.get('dummyMode')}
    if is_dummy_mode(settings):
        app_module.dummy_state.insert_job(job_id, created_at, criteria_payload,
                                          summary_length, summary, messages)
    else:
        insert_job(job_id, created_at, criteria_payload, summary_length, summary, messages)
    app_module._record_log(
        'create_summary',
        'ok',
        f'Created summary with {len(messages)} messages',
        job_id=job_id,
        settings=settings,
    )
    app_module._record_log(
        'summary_provider',
        meta.get('status', 'ok'),
        f"provider={meta.get('provider')} model={meta.get('model')}",
        job_id=job_id,
        settings=settings,
    )
    return SummaryResponse(
        jobId=job_id,
        messages=[MessageItem(id=m['id'], subject=m['subject'],
                              sender=m['sender'], date=m['date']) for m in messages],
        summary=summary,
    )


@router.get('/jobs/{job_id}/messages/{message_id}', response_model=MessageDetail)
def get_job_message(job_id: str, message_id: str) -> MessageDetail:
    app_module = get_app_module()

    job = app_module.dummy_state.get_job(job_id) if is_dummy_mode(
        app_module._merged_settings()) else get_job(job_id)
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
