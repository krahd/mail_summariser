from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.config import DEFAULT_SETTINGS
from backend.db import (
    delete_index_message,
    get_index_message,
    get_job,
    list_logs,
    upsert_index_message,
)
from backend.mail_service import (
    add_keyword_tag,
    is_dummy_mode,
    mark_messages_read,
    move_messages,
    move_messages_back,
    remove_keyword_tag,
    restore_messages_unread,
    send_summary_email,
    unroutable_message_ids,
)
from backend.router_context import get_app_module

router = APIRouter()

ACTION_KINDS = ('mark_read', 'tag_summarised', 'archive')


def _summarised_tag(settings: dict) -> str:
    return str(settings.get('summarisedTag') or DEFAULT_SETTINGS.get(
        'summarisedTag', 'summarised'))


def _archive_mailbox(settings: dict) -> str:
    return str(settings.get('archiveMailbox') or DEFAULT_SETTINGS.get(
        'archiveMailbox', 'Archive'))


def _archive_mailbox_for_account(settings: dict, account_id: str) -> str:
    target_account_id = str(account_id or '').strip()
    accounts = settings.get('mailAccounts') or []
    if isinstance(accounts, list):
        for account in accounts:
            if not isinstance(account, dict):
                continue
            if str(account.get('id') or '').strip() != target_account_id:
                continue
            account_archive = str(account.get('archiveMailbox') or '').strip()
            if account_archive:
                return account_archive
    return _archive_mailbox(settings)


def _result_payload(result: object) -> dict:
    return result if isinstance(result, dict) else {}


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def _load_job(app_module, job_id: str | None, settings: dict) -> dict | None:
    if is_dummy_mode(settings):
        return app_module.dummy_state.get_job(job_id)
    return get_job(job_id)


def _job_message_dicts(job: dict) -> list[dict]:
    return [m for m in (job.get('messages_json') or []) if isinstance(m, dict)]


def _message_state(message: dict, settings: dict) -> dict:
    message_id = str(message.get('id') or '')
    if message_id and not is_dummy_mode(settings):
        indexed = get_index_message(message_id)
        if indexed:
            flags = {str(flag).lower() for flag in (indexed.get('flags') or [])}
            indexed['unread'] = '\\seen' not in flags
            indexed['flagged'] = '\\flagged' in flags
            indexed['replied'] = '\\answered' in flags
            return indexed
    return message


def _dedupe(values: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or '').strip()
        if not text or text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique


def _contains_ci(values: list[str], target: str) -> bool:
    target_lower = target.lower()
    return target_lower in {str(value).lower() for value in values}


def _without_ci(values: list[str], target: str) -> list[str]:
    target_lower = target.lower()
    return [str(value) for value in values if str(value).lower() != target_lower]


def _upsert_index_entry(entry: dict) -> None:
    try:
        upsert_index_message(entry)
    except ValueError:
        return


def _set_index_seen(message_ids: list[str], seen: bool, settings: dict) -> None:
    if is_dummy_mode(settings):
        return
    for message_id in _dedupe(message_ids):
        entry = get_index_message(message_id)
        if not entry:
            continue
        flags = [str(flag) for flag in (entry.get('flags') or []) if str(flag).strip()]
        if seen:
            if not _contains_ci(flags, '\\Seen'):
                flags.append('\\Seen')
        else:
            flags = _without_ci(flags, '\\Seen')
        entry['flags'] = flags
        _upsert_index_entry(entry)


def _set_index_tag(message_ids: list[str], tag: str, present: bool, settings: dict) -> None:
    if is_dummy_mode(settings):
        return
    tag_value = str(tag or '').strip()
    if not tag_value:
        return
    for message_id in _dedupe(message_ids):
        entry = get_index_message(message_id)
        if not entry:
            continue
        flags = [str(flag) for flag in (entry.get('flags') or []) if str(flag).strip()]
        keywords = [str(keyword) for keyword in (entry.get('keywords') or []) if str(keyword).strip()]
        if present:
            if not _contains_ci(flags, tag_value):
                flags.append(tag_value)
            if not _contains_ci(keywords, tag_value):
                keywords.append(tag_value)
        else:
            flags = _without_ci(flags, tag_value)
            keywords = _without_ci(keywords, tag_value)
        entry['flags'] = flags
        entry['keywords'] = keywords
        _upsert_index_entry(entry)


def _move_index_entries(moved_entries: list[dict], settings: dict) -> None:
    if is_dummy_mode(settings):
        return
    for moved in moved_entries:
        source_id = str(moved.get('id') or '').strip()
        moved_id = str(moved.get('movedId') or '').strip()
        target_mailbox = str(moved.get('targetMailbox') or '').strip()
        new_uid = str(moved.get('newUid') or '').strip()
        if not source_id or not moved_id or not target_mailbox or not new_uid:
            continue
        entry = get_index_message(source_id)
        if not entry:
            continue
        delete_index_message(source_id)
        entry['id'] = moved_id
        entry['mailboxPath'] = target_mailbox
        entry['uid'] = new_uid
        _upsert_index_entry(entry)


def _restore_moved_index_entries(restored_entries: list[dict], settings: dict) -> None:
    if is_dummy_mode(settings):
        return
    for restored in restored_entries:
        moved_id = str(restored.get('movedId') or '').strip()
        restored_id = str(restored.get('restoredId') or restored.get('id') or '').strip()
        source_mailbox = str(restored.get('sourceMailbox') or '').strip()
        restored_uid = str(restored.get('restoredUid') or '').strip()
        if not moved_id or not restored_id or not source_mailbox or not restored_uid:
            continue
        entry = get_index_message(moved_id)
        if not entry:
            continue
        delete_index_message(moved_id)
        entry['id'] = restored_id
        entry['mailboxPath'] = source_mailbox
        entry['uid'] = restored_uid
        _upsert_index_entry(entry)


def _sync_index_after_apply(action: str, changed_ids: list[str], undo_fragment: dict,
                            settings: dict) -> None:
    if action == 'mark_read':
        _set_index_seen(changed_ids, True, settings)
    elif action == 'tag_summarised':
        _set_index_tag(changed_ids, str(undo_fragment.get('tag') or _summarised_tag(settings)),
                       True, settings)
    elif action == 'archive':
        _move_index_entries(undo_fragment.get('moved', []) or [], settings)


def _sync_index_after_undo(payload: dict, result: dict, settings: dict) -> None:
    action = payload.get('action')
    if action == 'mark_read':
        restored_ids = [str(item) for item in (result.get('restore_unread_ids') or [])]
        _set_index_seen(restored_ids, False, settings)
    elif action == 'tag_summarised':
        removed_ids = [str(item) for item in (result.get('removed_message_ids') or [])]
        _set_index_tag(removed_ids, str(payload.get('tag') or _summarised_tag(settings)),
                       False, settings)
    elif action == 'move':
        _restore_moved_index_entries(result.get('restored', []) or [], settings)


def _undo_payload_has_changes(action: str, undo_fragment: dict) -> bool:
    if action == 'archive':
        return bool(undo_fragment.get('moved'))
    return bool(undo_fragment.get('message_ids'))


def _build_action_plan(action: str, job_id: str, messages: list[dict], settings: dict) -> dict:
    """Best-effort preview of what an action would change. Advisory only."""
    tag = _summarised_tag(settings)
    tag_lower = tag.lower()
    target_mailbox = _archive_mailbox(settings)
    unroutable = set(unroutable_message_ids([str(m.get('id') or '') for m in messages], settings))

    changed_items: list[dict] = []
    skipped_items: list[dict] = []

    for message in messages:
        state = _message_state(message, settings)
        message_id = str(message.get('id') or '')
        base = {
            'id': message_id,
            'accountId': str(message.get('accountId') or state.get('accountId') or ''),
            'mailboxPath': str(message.get('mailboxPath') or state.get('mailboxPath') or ''),
            'uid': str(message.get('uid') or state.get('uid') or ''),
            'subject': str(message.get('subject') or state.get('subject') or ''),
            'sender': str(message.get('sender') or state.get('sender') or ''),
        }
        if message_id in unroutable:
            skipped_items.append({**base, 'willChange': False,
                                  'reason': 'account not configured or disabled'})
            continue
        if action == 'mark_read':
            if bool(state.get('unread')):
                changed_items.append({**base, 'currentState': 'unread',
                                      'plannedState': 'read', 'willChange': True})
            else:
                skipped_items.append({**base, 'currentState': 'read', 'plannedState': 'read',
                                      'willChange': False, 'reason': 'already read'})
        elif action == 'tag_summarised':
            keywords = [str(k).lower() for k in (state.get('keywords') or [])]
            if tag_lower in keywords:
                skipped_items.append({**base, 'currentState': f'tagged:{tag}',
                                      'plannedState': f'tagged:{tag}', 'willChange': False,
                                      'reason': 'already tagged'})
            else:
                changed_items.append({**base, 'currentState': 'untagged',
                                      'plannedState': f'tagged:{tag}', 'willChange': True})
        elif action == 'archive':
            source_mailbox = base['mailboxPath'] or 'INBOX'
            target_mailbox = _archive_mailbox_for_account(settings, base['accountId'])
            base['targetMailbox'] = target_mailbox
            if source_mailbox == target_mailbox:
                skipped_items.append({**base, 'currentState': source_mailbox,
                                      'plannedState': target_mailbox, 'willChange': False,
                                      'reason': 'already in archive'})
            else:
                changed_items.append({**base, 'currentState': source_mailbox,
                                      'plannedState': target_mailbox, 'willChange': True})

    groups: dict[tuple[str, str], dict] = {}
    for item in changed_items:
        key = (item['accountId'], item['mailboxPath'])
        groups.setdefault(key, {'accountId': key[0], 'mailboxPath': key[1],
                                'changeCount': 0, 'skipCount': 0})['changeCount'] += 1
    for item in skipped_items:
        key = (item['accountId'], item['mailboxPath'])
        groups.setdefault(key, {'accountId': key[0], 'mailboxPath': key[1],
                                'changeCount': 0, 'skipCount': 0})['skipCount'] += 1

    warnings: list[str] = []
    if unroutable:
        warnings.append(f'{len(unroutable)} message(s) could not be routed to a configured account.')

    return {
        'jobId': job_id,
        'action': action,
        'tag': tag if action == 'tag_summarised' else '',
        'targetMailbox': target_mailbox if action == 'archive' else '',
        'totalMessages': len(messages),
        'changeCount': len(changed_items),
        'skipCount': len(skipped_items),
        'items': changed_items,
        'skipped': skipped_items,
        'groups': list(groups.values()),
        'warnings': warnings,
        'safeMode': _bool(settings.get('safeMode')),
    }


def _require_action(payload: dict) -> str:
    action = str((payload or {}).get('action') or '').strip()
    if action not in ACTION_KINDS:
        raise HTTPException(status_code=400,
                            detail=f"Unsupported action; expected one of {ACTION_KINDS}")
    return action


@router.post('/actions/jobs/{job_id}/preview')
def actions_preview(job_id: str, payload: dict) -> dict:
    app_module = get_app_module()
    try:
        action = _require_action(payload)
        settings = app_module._merged_settings()
        job = _load_job(app_module, job_id, settings)
        if job is None:
            raise HTTPException(status_code=404, detail='Job not found')
        plan = _build_action_plan(action, job_id, _job_message_dicts(job), settings)
        return plan
    except HTTPException:
        raise
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _apply_action(action: str, message_ids: list[str], settings: dict) -> tuple[list[str], list[str], dict]:
    """Run an action, returning (changed_ids, failed_ids, undo_payload_fragment)."""
    if action == 'mark_read':
        result = _result_payload(mark_messages_read(message_ids, settings))
        changed = result.get('restore_unread_ids', []) or []
        failed = result.get('failed_message_ids', []) or []
        return changed, failed, {'action': 'mark_read', 'message_ids': changed}
    if action == 'tag_summarised':
        tag = _summarised_tag(settings)
        result = _result_payload(add_keyword_tag(message_ids, tag, settings))
        changed = result.get('added_message_ids', []) or []
        failed = result.get('failed_message_ids', []) or []
        return changed, failed, {'action': 'tag_summarised', 'message_ids': changed, 'tag': tag}
    if action == 'archive':
        target = _archive_mailbox(settings)
        result = _result_payload(move_messages(message_ids, target, settings))
        moved = result.get('moved', []) or []
        failed = result.get('failed_message_ids', []) or []
        changed = [str(entry.get('id')) for entry in moved]
        return changed, failed, {'action': 'move', 'moved': moved}
    raise HTTPException(status_code=400, detail='Unsupported action')


@router.post('/actions/jobs/{job_id}/apply')
def actions_apply(job_id: str, payload: dict) -> dict:
    app_module = get_app_module()
    try:
        action = _require_action(payload)
        settings = app_module._merged_settings()
        job = _load_job(app_module, job_id, settings)
        if job is None:
            raise HTTPException(status_code=404, detail='Job not found')
        messages = _job_message_dicts(job)
        plan = _build_action_plan(action, job_id, messages, settings)
        action_message_ids = _dedupe([str(item.get('id') or '') for item in plan['items']])

        safe_mode = _bool(settings.get('safeMode'))
        dry_run = safe_mode or _bool((payload or {}).get('dryRun'))

        if dry_run:
            would_change = [item['id'] for item in plan['items']]
            details = (f"dry_run action={action} would_change={len(would_change)} "
                       f"skipped={plan['skipCount']} safe_mode={safe_mode}")
            app_module._record_log(action, 'dry_run', details, job_id=job_id, settings=settings)
            return {
                'status': 'ok', 'jobId': job_id, 'action': action, 'applied': False,
                'safeMode': safe_mode, 'changedIds': would_change, 'failedIds': [],
                'skippedIds': [item['id'] for item in plan['skipped']], 'logId': '',
                'preview': plan,
            }

        changed, failed, undo_fragment = _apply_action(action, action_message_ids, settings)
        terminal_ids = set(changed) | set(failed)
        skipped = _dedupe(
            [str(item.get('id') or '') for item in plan['skipped']]
            + [mid for mid in action_message_ids if mid not in terminal_ids]
        )
        details = f"{action} success={len(changed)} failed={len(failed)} skipped={len(skipped)}"
        if failed:
            details += f" failed_message_ids={failed}"
        log_id = app_module._record_log(action, 'ok', details, job_id=job_id, settings=settings)
        if changed:
            _sync_index_after_apply(action, changed, undo_fragment, settings)
        if _undo_payload_has_changes(action, undo_fragment):
            app_module._push_undo({**undo_fragment, 'log_id': log_id, 'job_id': job_id})
        return {
            'status': 'ok', 'jobId': job_id, 'action': action, 'applied': True,
            'safeMode': safe_mode, 'changedIds': changed, 'failedIds': failed,
            'skippedIds': skipped, 'logId': log_id, 'preview': plan,
        }
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
        job = _load_job(app_module, job_id, settings)
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


def _perform_undo(payload: dict, settings: dict, app_module) -> None:
    action = payload.get('action')
    job_id = payload.get('job_id')
    message_ids = payload.get('message_ids', []) or []
    if action == 'mark_read':
        result = _result_payload(restore_messages_unread(message_ids, settings))
        restored_ids = result.get('restore_unread_ids', []) or []
        failed_ids = result.get('failed_message_ids', []) or []
        _sync_index_after_undo(payload, result, settings)
        details = f"restored {len(restored_ids)} messages"
        if failed_ids:
            details += f" failed_message_ids={failed_ids}"
        app_module._record_log('undo', 'ok', details, job_id=job_id, settings=settings)
    elif action == 'tag_summarised':
        tag = str(payload.get('tag') or _summarised_tag(settings))
        result = _result_payload(remove_keyword_tag(message_ids, tag, settings))
        removed_ids = result.get('removed_message_ids', []) or []
        failed_ids = result.get('failed_message_ids', []) or []
        _sync_index_after_undo(payload, result, settings)
        details = f"removed tags from {len(removed_ids)} messages"
        if failed_ids:
            details += f" failed_message_ids={failed_ids}"
        app_module._record_log('undo', 'ok', details, job_id=job_id, settings=settings)
    elif action == 'move':
        result = _result_payload(move_messages_back(payload.get('moved', []) or [], settings))
        restored_ids = result.get('restored_message_ids', []) or []
        failed_ids = result.get('failed_message_ids', []) or []
        _sync_index_after_undo(payload, result, settings)
        details = f"moved back {len(restored_ids)} messages"
        if failed_ids:
            details += f" failed_message_ids={failed_ids}"
        app_module._record_log('undo', 'ok', details, job_id=job_id, settings=settings)
    else:
        app_module._record_log(
            'undo', 'ok', f'performed undo for action {action}', job_id=job_id, settings=settings)


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
        _perform_undo(payload, settings, app_module)
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
        _perform_undo(payload, settings, app_module)
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
