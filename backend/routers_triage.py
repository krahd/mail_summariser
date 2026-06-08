from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from backend.db import insert_job
from backend.mail_service import is_dummy_mode
from backend.router_context import get_app_module
from backend.saved_scope_service import get_saved_scope
from backend.schemas import (
    MessageItem,
    SummaryResponse,
    TriageBucketSummaryRequest,
    TriageDashboardResponse,
)
from backend.summary_service import EMPTY_SUMMARY_TEXT, summarize_messages
from backend.triage_service import (
    build_triage_bucket_summary_data,
    build_triage_dashboard,
    project_message_for_summary,
)


router = APIRouter(prefix='/mail/triage')


def _safe_summary_length(value: int) -> int:
    return max(1, min(int(value), 24))


@router.get('/dashboard', response_model=TriageDashboardResponse)
def get_triage_dashboard(scopeId: str | None = None, limitPerBucket: int = 5,
                         staleDays: int = 14) -> TriageDashboardResponse:
    try:
        dashboard = build_triage_dashboard(scopeId, limitPerBucket, staleDays, include_body_text=False)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return TriageDashboardResponse(**dashboard)


@router.post('/buckets/{bucket_id}/summary', response_model=SummaryResponse)
def create_triage_bucket_summary(bucket_id: str, request: TriageBucketSummaryRequest) -> SummaryResponse:
    app_module = get_app_module()
    settings = app_module._merged_settings()

    try:
        dashboard, bucket = build_triage_bucket_summary_data(
            request.scopeId,
            bucket_id,
            request.limitPerBucket,
            request.staleDays,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    scope = get_saved_scope(dashboard['scopeId'])
    if scope is None:
        raise HTTPException(status_code=404, detail=f"Saved scope {dashboard['scopeId']!r} not found")

    summary_length = _safe_summary_length(request.summaryLength)
    job_messages = [project_message_for_summary(message) for message in bucket.get('messages', [])]
    summary, meta = summarize_messages(job_messages, summary_length, settings=settings)
    if not job_messages and summary == EMPTY_SUMMARY_TEXT:
        meta = {'provider': 'none', 'model': 'none', 'status': 'empty', 'fallback': 'false'}

    job_id = f'job-{uuid4()}'
    created_at = datetime.now().isoformat(timespec='seconds')
    criteria_payload = {
        'scopeId': dashboard['scopeId'],
        'scopeName': scope.get('name', ''),
        'scopeQuery': scope.get('query', {}),
        'triageBucketId': bucket_id,
        'triageBucketLabel': bucket.get('label', bucket_id),
        'triageBucketDescription': bucket.get('description', ''),
        'triageLimitPerBucket': max(1, min(int(request.limitPerBucket), 100)),
        'triageStaleDays': max(1, min(int(request.staleDays), 365)),
        'mailContext': {'dummyMode': settings.get('dummyMode')},
    }
    if is_dummy_mode(settings):
        app_module.dummy_state.insert_job(job_id, created_at, criteria_payload,
                                          summary_length, summary, job_messages)
    else:
        insert_job(job_id, created_at, criteria_payload, summary_length, summary, job_messages)

    app_module._record_log(
        'create_triage_bucket_summary',
        'ok',
        f"Created triage summary for {bucket_id} with {len(job_messages)} messages",
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
        messages=[
            MessageItem(
                id=str(message.get('id', '')),
                subject=str(message.get('subject', '')),
                sender=str(message.get('sender', '')),
                date=str(message.get('date', '')),
            )
            for message in job_messages
        ],
        summary=summary,
    )
