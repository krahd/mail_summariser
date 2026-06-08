from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.config import DEFAULT_SETTINGS
from backend.db import get_job, list_logs
from backend.mail_service import (
    add_keyword_tag,
    is_dummy_mode,
    mark_messages_read,
    remove_keyword_tag,
    restore_messages_unread,
    send_summary_email,
)
from backend.router_context import get_app_module


router = APIRouter()


def _summarised_tag(settings: dict) -> str:
    return str(settings.get('summarisedTag') or DEFAULT_SETTINGS.get(
        'summarisedTag', 'summarised'))


def _result_payload(result: object) -> dict:
    return result if isinstance(result, dict) else {}


@router.post('/actions/mark-read')
def actions_mark_read(payload: dict) -> dict:
    app_module = get_app_module()

    try:
        job_id = payload.get('jobId') if isinstance(payload, dict) else None
        settings = app_module._merged_settings()
        job = app_module.dummy_state.get_job(job_id) if is_dummy_mode(settings) else get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail='Job not found')
        message_ids = [m.get('id') for m in job.get('messages_json', [])]
        result = _result_payload(mark_messages_read(message_ids, settings))
        restored_ids = result.get('restore_unread_ids', []) or []
        failed_ids = result.get('failed_message_ids', []) or []
        details = f"marked_read success={len(restored_ids)} failed={len(failed_ids)}"
        if failed_ids:
            details += f" failed_message_ids={failed_ids}"
        log_id = app_module._record_log('mark_read', 'ok', details,
                                        job_id=job_id, settings=settings)
        if restored_ids:
            app_module._push_undo({'action': 'mark_read', 'log_id': log_id,
                                  'job_id': job_id, 'message_ids': restored_ids})
        return {'status': 'ok', **result}
    except HTTPException:
        raise
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/actions/tag-summarised')
def actions_tag_summarised(payload: dict) -> dict:
    app_module = get_app_module()

    try:
        job_id = payload.get('jobId') if isinstance(payload, dict) else None
        settings = app_module._merged_settings()
        job = app_module.dummy_state.get_job(job_id) if is_dummy_mode(settings) else get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail='Job not found')
        message_ids = [m.get('id') for m in job.get('messages_json', [])]
        tag = _summarised_tag(settings)
        result = _result_payload(add_keyword_tag(message_ids, tag, settings))
        added_ids = result.get('added_message_ids', []) or []
        failed_ids = result.get('failed_message_ids', []) or []
        details = f"tagged_summarised success={len(added_ids)} failed={len(failed_ids)}"
        if failed_ids:
            details += f" failed_message_ids={failed_ids}"
        log_id = app_module._record_log('tag_summarised', 'ok', details,
                                        job_id=job_id, settings=settings)
        if added_ids:
            app_module._push_undo({'action': 'tag_summarised', 'log_id': log_id,
                                  'job_id': job_id, 'message_ids': added_ids, 'tag': tag})
        return {'status': 'ok', **result}
    except HTTPException:
        raise
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/actions/email-summary')
def actions_email_summary(payload: dict) -> dict:
    app_module = get_app_module()

    try:
        job_id = payload.get('jobId') if isinstance(payload, dict) else None
        settings = app_module._merged_settings()
        job = app_module.dummy_state.get_job(job_id) if is_dummy_mode(settings) else get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail='Job not found')
        summary_text = str(job.get('summary_text') or '')
        recipient = str(settings.get('recipientEmail') or '')
        send_summary_email(recipient, 'Mail summary', summary_text, settings)
        details = 'email_summary_sent'
        app_module._record_log('email_summary', 'ok', details, job_id=job_id, settings=settings)
        return {'status': 'ok'}
    except HTTPException:
        raise
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/actions/undo/logs/{log_id}')
def actions_undo_log(log_id: str) -> dict:
    app_module = get_app_module()

    try:
        settings = app_module._merged_settings()
        if is_dummy_mode(settings):
            payload = app_module.dummy_state.pop_undo_by_log_id(log_id)
        else:
            payload = app_module._get_db().pop_undo_by_log_id(log_id)
        if payload is None:
            raise HTTPException(status_code=404, detail='No undo found for log')
        action = payload.get('action')
        job_id = payload.get('job_id')
        message_ids = payload.get('message_ids', []) or []
        if action == 'mark_read':
            result = _result_payload(restore_messages_unread(message_ids, settings))
            restored_ids = result.get('restore_unread_ids', []) or []
            failed_ids = result.get('failed_message_ids', []) or []
            details = f"restored {len(restored_ids)} messages"
            if failed_ids:
                details += f" failed_message_ids={failed_ids}"
            app_module._record_log(
                'undo', 'ok', details, job_id=job_id, settings=settings)
        elif action == 'tag_summarised':
            tag = str(payload.get('tag') or _summarised_tag(settings))
            result = _result_payload(remove_keyword_tag(message_ids, tag, settings))
            removed_ids = result.get('removed_message_ids', []) or []
            failed_ids = result.get('failed_message_ids', []) or []
            details = f"removed tags from {len(removed_ids)} messages"
            if failed_ids:
                details += f" failed_message_ids={failed_ids}"
            app_module._record_log(
                'undo', 'ok', details, job_id=job_id, settings=settings)
        else:
            app_module._record_log(
                'undo', 'ok', f'performed undo for action {action}', job_id=job_id, settings=settings)
        return {'status': 'ok'}
    except HTTPException:
        raise
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/actions/undo')
def actions_undo() -> dict:
    app_module = get_app_module()

    try:
        settings = app_module._merged_settings()
        payload = app_module.dummy_state.pop_latest_undo() if is_dummy_mode(
            settings) else app_module._get_db().pop_latest_undo()
        if payload is None:
            raise HTTPException(status_code=404, detail='No undo found')
        action = payload.get('action')
        job_id = payload.get('job_id')
        message_ids = payload.get('message_ids', []) or []
        if action == 'mark_read':
            result = _result_payload(restore_messages_unread(message_ids, settings))
            restored_ids = result.get('restore_unread_ids', []) or []
            failed_ids = result.get('failed_message_ids', []) or []
            details = f"restored {len(restored_ids)} messages"
            if failed_ids:
                details += f" failed_message_ids={failed_ids}"
            app_module._record_log(
                'undo', 'ok', details, job_id=job_id, settings=settings)
        elif action == 'tag_summarised':
            tag = str(payload.get('tag') or _summarised_tag(settings))
            result = _result_payload(remove_keyword_tag(message_ids, tag, settings))
            removed_ids = result.get('removed_message_ids', []) or []
            failed_ids = result.get('failed_message_ids', []) or []
            details = f"removed tags from {len(removed_ids)} messages"
            if failed_ids:
                details += f" failed_message_ids={failed_ids}"
            app_module._record_log(
                'undo', 'ok', details, job_id=job_id, settings=settings)
        else:
            app_module._record_log(
                'undo', 'ok', f'performed undo for action {action}', job_id=job_id, settings=settings)
        return {'status': 'ok'}
    except HTTPException:
        raise
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get('/logs')
def get_logs() -> list[dict]:
    app_module = get_app_module()

    raw = app_module.dummy_state.list_logs() if is_dummy_mode(
        app_module._merged_settings()) else list_logs()
    undoable = app_module.dummy_state.list_undoable_log_ids() if is_dummy_mode(
        app_module._merged_settings()) else app_module._get_db().list_undoable_log_ids()
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
