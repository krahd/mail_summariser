from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from backend.db import insert_job
from backend.mail_service import is_dummy_mode
from backend.router_context import get_app_module
from backend.saved_scope_service import (
    create_saved_scope as create_saved_scope_record,
    delete_saved_scope as delete_saved_scope_record,
    list_messages_for_scope,
    list_saved_scopes as list_saved_scope_records,
    scope_messages_for_summary,
    update_saved_scope as update_saved_scope_record,
)
from backend.schemas import (
    MailIndexMessageSummary,
    MessageItem,
    SavedScope,
    SavedScopeCreateRequest,
    SavedScopeSummaryRequest,
    SummaryResponse,
)
from backend.summary_service import summarize_messages


router = APIRouter(prefix='/mail/scopes')


def _safe_summary_length(value: int) -> int:
    return max(1, min(int(value), 24))


def _safe_scope_limit(value: int) -> int:
    return max(1, min(int(value), 200))


def _scope_message_to_job_message(message: dict[str, object]) -> dict[str, object]:
    flags = [str(flag) for flag in (message.get('flags') or []) if str(flag).strip()]
    keywords = [flag for flag in flags if not flag.startswith('\\')]
    recipients = message.get('recipients') or []
    if not isinstance(recipients, list):
        recipients = [recipients]
    recipient = str(recipients[0]) if recipients else ''
    body_text = str(message.get('bodyText', '') or '').strip()
    body = body_text or str(message.get('bodyPreview', '') or '')
    return {
        'id': str(message.get('id', '')),
        'subject': str(message.get('subject', '')),
        'sender': str(message.get('sender', '')),
        'recipient': recipient,
        'date': str(message.get('date', '')),
        'body': body,
        'unread': '\\seen' not in {flag.lower() for flag in flags},
        'replied': '\\answered' in {flag.lower() for flag in flags},
        'flagged': '\\flagged' in {flag.lower() for flag in flags},
        'keywords': keywords,
        'listId': str(message.get('listId', '') or ''),
    }


@router.get('', response_model=list[SavedScope])
def get_saved_scopes() -> list[SavedScope]:
    return [SavedScope(**scope) for scope in list_saved_scope_records()]


@router.post('', response_model=SavedScope, status_code=201)
def create_saved_scope(request: SavedScopeCreateRequest) -> SavedScope:
    try:
        scope = create_saved_scope_record(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SavedScope(**scope)


@router.put('/{scope_id}', response_model=SavedScope)
def update_saved_scope(scope_id: str, request: SavedScopeCreateRequest) -> SavedScope:
    try:
        scope = update_saved_scope_record(scope_id, request.model_dump())
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SavedScope(**scope)


@router.delete('/{scope_id}')
def delete_saved_scope(scope_id: str) -> dict[str, str]:
    if not delete_saved_scope_record(scope_id):
        raise HTTPException(status_code=404, detail=f'Saved scope {scope_id!r} not found')
    return {'status': 'ok'}


@router.get('/{scope_id}/messages', response_model=list[MailIndexMessageSummary])
def get_saved_scope_messages(scope_id: str, limit: int = 200) -> list[MailIndexMessageSummary]:
    try:
        safe_limit = _safe_scope_limit(limit)
        messages = list_messages_for_scope(scope_id, safe_limit)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [MailIndexMessageSummary(**message) for message in messages]


@router.post('/{scope_id}/summary', response_model=SummaryResponse)
def create_saved_scope_summary(scope_id: str, request: SavedScopeSummaryRequest) -> SummaryResponse:
    app_module = get_app_module()
    settings = app_module._merged_settings()

    try:
        scope, indexed_messages = scope_messages_for_summary(scope_id, request.limit)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    summary_length = _safe_summary_length(request.summaryLength)
    job_messages = [_scope_message_to_job_message(message) for message in indexed_messages]
    summary, meta = summarize_messages(job_messages, summary_length, settings=settings)

    job_id = f'job-{uuid4()}'
    created_at = datetime.now().isoformat(timespec='seconds')
    criteria_payload = {
        'scopeId': scope_id,
        'scopeName': scope.get('name', ''),
        'scopeQuery': scope.get('query', {}),
        'scopeLimit': _safe_scope_limit(request.limit),
        'mailContext': {'dummyMode': settings.get('dummyMode')},
    }
    if is_dummy_mode(settings):
        app_module.dummy_state.insert_job(job_id, created_at, criteria_payload,
                                          summary_length, summary, job_messages)
    else:
        insert_job(job_id, created_at, criteria_payload, summary_length, summary, job_messages)

    app_module._record_log(
        'create_scope_summary',
        'ok',
        f'Created scope summary {scope_id} with {len(job_messages)} messages',
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
