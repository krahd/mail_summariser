from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from backend import db


JUNK_OR_TRASH_MAILBOXES = {
    'junk',
    'junk e-mail',
    'junk mail',
    'spam',
    'trash',
    'deleted',
    'deleted messages',
}

_DEFAULT_EXCLUDED_MAILBOXES = ['Trash', 'Deleted Messages', 'Junk']


def _now_iso() -> str:
    return datetime.now().isoformat(timespec='seconds')


def _normalise_text(value: Any) -> str:
    return str(value or '').strip()


def _normalise_text_list(value: Any) -> list[str]:
    if value in (None, ''):
        return []
    items: list[Any]
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = [value]

    results: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = _normalise_text(item)
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        results.append(text)
    return results


def _scope_id_from_name(name: str) -> str:
    base = re.sub(r'[^a-z0-9]+', '_', name.strip().lower()).strip('_')
    return base or 'saved_scope'


def _default_scope_query(*, unread: bool | None = None, flagged: bool | None = None,
                         any_terms: list[dict[str, Any]] | None = None,
                         mailboxes: list[str] | None = None) -> dict[str, Any]:
    query: dict[str, Any] = {
        'accounts': ['*'],
        'excludeMailboxes': list(_DEFAULT_EXCLUDED_MAILBOXES),
    }
    if mailboxes:
        query['mailboxes'] = mailboxes
    if unread is not None:
        query['unread'] = unread
    if flagged is not None:
        query['flagged'] = flagged
    if any_terms:
        query['any'] = any_terms
    return query


DEFAULT_SAVED_SCOPES: list[dict[str, Any]] = [
    {
        'id': 'unread_or_flagged_all',
        'name': 'Unread or Flagged all',
        'description': 'Unread or flagged messages in the inboxes of all enabled accounts, excluding junk and trash.',
        'query': _default_scope_query(
            mailboxes=['INBOX'],
            any_terms=[{'unread': True}, {'flagged': True}],
        ),
        'sortOrder': 10,
    },
    {
        'id': 'flagged_all',
        'name': 'Flagged all',
        'description': 'Flagged messages in the inboxes of all enabled accounts, excluding junk and trash.',
        'query': _default_scope_query(
            mailboxes=['INBOX'],
            flagged=True,
        ),
        'sortOrder': 20,
    },
    {
        'id': 'unread_all',
        'name': 'Unread all',
        'description': 'Unread messages in the inboxes of all enabled accounts, excluding junk and trash.',
        'query': _default_scope_query(
            mailboxes=['INBOX'],
            unread=True,
        ),
        'sortOrder': 30,
    },
    {
        'id': 'lists_fing',
        'name': 'Unread or Flagged, Lists_Fing',
        'description': 'Unread or flagged messages that match the Fing list tag or list metadata, excluding junk and trash.',
        'query': _default_scope_query(
            any_terms=[
                {'unread': True},
                {'flagged': True},
            ],
        ) | {
            'all': [
                {
                    'any': [
                        {'tag': 'List_Fing'},
                        {'listIdContains': 'fing.edu.uy'},
                    ],
                },
                {'notMailboxKind': 'junk_or_trash'},
            ],
        },
        'sortOrder': 40,
    },
    {
        'id': 'finance',
        'name': 'Finance',
        'description': 'Finance-related mail that matches invoice, billing, or finance keywords.',
        'query': _default_scope_query(
            any_terms=[
                {'tag': 'finance'},
                {'keyword': 'invoice'},
                {'senderContains': 'billing@'},
                {'listIdContains': 'finance'},
            ],
        ),
        'sortOrder': 50,
    },
]


def ensure_default_saved_scopes() -> None:
    existing_ids = {scope['id'] for scope in db.list_saved_scopes()}
    now = _now_iso()
    for scope in DEFAULT_SAVED_SCOPES:
        if scope['id'] in existing_ids:
            continue
        db.upsert_saved_scope(scope, created_at=now, updated_at=now)


def list_saved_scopes() -> list[dict[str, Any]]:
    ensure_default_saved_scopes()
    return db.list_saved_scopes()


def get_saved_scope(scope_id: str) -> dict[str, Any] | None:
    ensure_default_saved_scopes()
    return db.get_saved_scope(scope_id)


def _generate_unique_scope_id(name: str) -> str:
    base = _scope_id_from_name(name)
    candidate = base
    suffix = 2
    existing_ids = {scope['id'] for scope in db.list_saved_scopes()}
    while candidate in existing_ids:
        candidate = f'{base}_{suffix}'
        suffix += 1
    return candidate


def create_saved_scope(payload: dict[str, Any]) -> dict[str, Any]:
    ensure_default_saved_scopes()
    scope = dict(payload)
    scope_id = _normalise_text(scope.get('id'))
    if not scope_id:
        scope_id = _generate_unique_scope_id(_normalise_text(scope.get('name')))
    if db.get_saved_scope(scope_id) is not None:
        raise ValueError(f'Saved scope {scope_id!r} already exists')
    scope['id'] = scope_id
    db.upsert_saved_scope(scope)
    return db.get_saved_scope(scope_id) or scope


def update_saved_scope(scope_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    ensure_default_saved_scopes()
    resolved_scope_id = _normalise_text(scope_id)
    if not resolved_scope_id:
        raise ValueError('Scope id is required')
    current = db.get_saved_scope(resolved_scope_id)
    if current is None:
        raise LookupError(f'Saved scope {resolved_scope_id!r} not found')
    scope = dict(payload)
    requested_scope_id = _normalise_text(scope.get('id'))
    if requested_scope_id and requested_scope_id != resolved_scope_id:
        raise ValueError('Scope id in payload must match the path parameter')
    scope['id'] = resolved_scope_id
    db.upsert_saved_scope(scope)
    return db.get_saved_scope(resolved_scope_id) or scope


def delete_saved_scope(scope_id: str) -> bool:
    ensure_default_saved_scopes()
    return db.delete_saved_scope(scope_id)


def _mailbox_is_junk_or_trash(mailbox_path: str) -> bool:
    normalized = _normalise_text(mailbox_path).lower()
    if not normalized:
        return False
    if normalized in JUNK_OR_TRASH_MAILBOXES:
        return True
    return any(token in normalized for token in ('junk', 'trash', 'deleted', 'spam'))


def _message_haystack(message: dict[str, Any]) -> str:
    recipients = message.get('recipients') or []
    if not isinstance(recipients, list):
        recipients = [recipients]
    keywords = message.get('keywords') or []
    if not isinstance(keywords, list):
        keywords = [keywords]
    parts = [
        message.get('subject', ''),
        message.get('sender', ''),
        ' '.join(str(item) for item in recipients),
        message.get('date', ''),
        message.get('listId', ''),
        message.get('bodyPreview', ''),
        message.get('bodyText', ''),
        ' '.join(str(item) for item in keywords),
    ]
    return ' '.join(str(part) for part in parts if str(part).strip()).lower()


def _matches_any_tag(message: dict[str, Any], requested_tags: list[str]) -> bool:
    if not requested_tags:
        return True
    message_keywords = {str(item).strip().lower() for item in (message.get('keywords') or []) if str(item).strip()}
    for tag in requested_tags:
        if tag.lower() in message_keywords:
            return True
    return False


def _matches_direct_terms(query: dict[str, Any], message: dict[str, Any]) -> bool:
    accounts = _normalise_text_list(query.get('accounts'))
    if accounts and '*' not in {account.lower() for account in accounts}:
        account_id = _normalise_text(message.get('accountId')).lower()
        if account_id not in {account.lower() for account in accounts}:
            return False

    mailboxes = _normalise_text_list(query.get('mailboxes'))
    mailbox_path = _normalise_text(message.get('mailboxPath'))
    if mailboxes and mailbox_path.lower() not in {mailbox.lower() for mailbox in mailboxes}:
        return False

    exclude_mailboxes = _normalise_text_list(query.get('excludeMailboxes'))
    if exclude_mailboxes and mailbox_path.lower() in {mailbox.lower() for mailbox in exclude_mailboxes}:
        return False

    if _normalise_text(query.get('notMailboxKind')).lower() == 'junk_or_trash' and _mailbox_is_junk_or_trash(mailbox_path):
        return False

    unread = query.get('unread')
    if unread is not None:
        is_unread = '\\seen' not in {str(flag).lower() for flag in (message.get('flags') or [])}
        if bool(unread) != is_unread:
            return False

    flagged = query.get('flagged')
    if flagged is not None:
        is_flagged = '\\flagged' in {str(flag).lower() for flag in (message.get('flags') or [])}
        if bool(flagged) != is_flagged:
            return False

    tag = query.get('tag')
    if tag not in (None, ''):
        requested_tags = _normalise_text_list(tag)
        if not _matches_any_tag(message, requested_tags):
            return False

    keyword = _normalise_text(query.get('keyword'))
    if keyword and keyword.lower() not in _message_haystack(message):
        return False

    sender_contains = _normalise_text(query.get('senderContains'))
    if sender_contains and sender_contains.lower() not in _normalise_text(message.get('sender')).lower():
        return False

    subject_contains = _normalise_text(query.get('subjectContains'))
    if subject_contains and subject_contains.lower() not in _normalise_text(message.get('subject')).lower():
        return False

    list_id_contains = _normalise_text(query.get('listIdContains') or query.get('listId'))
    if list_id_contains and list_id_contains.lower() not in _normalise_text(message.get('listId')).lower():
        return False

    keywords = query.get('keywords')
    if keywords not in (None, ''):
        requested_keywords = _normalise_text_list(keywords)
        if requested_keywords and not _matches_any_tag(message, requested_keywords):
            return False

    return True


def _matches_nested_groups(query: dict[str, Any], message: dict[str, Any]) -> bool:
    any_groups = query.get('any')
    if any_groups is not None:
        if not isinstance(any_groups, list):
            return False
        if not any_groups:
            return False
        if not any(_message_matches_query(group, message) for group in any_groups if isinstance(group, dict)):
            return False

    all_groups = query.get('all')
    if all_groups is not None:
        if not isinstance(all_groups, list):
            return False
        if not all(_message_matches_query(group, message) for group in all_groups if isinstance(group, dict)):
            return False

    return True


def _message_matches_query(query: dict[str, Any], message: dict[str, Any]) -> bool:
    if not isinstance(query, dict):
        return False
    if not _matches_direct_terms(query, message):
        return False
    return _matches_nested_groups(query, message)


def list_messages_for_scope(scope_id: str, limit: int = 200,
                           include_body_text: bool = False) -> list[dict[str, Any]]:
    ensure_default_saved_scopes()
    scope = db.get_saved_scope(scope_id)
    if scope is None:
        raise LookupError(f'Saved scope {scope_id!r} not found')
    try:
        safe_limit = max(1, min(int(limit or 200), 200))
    except (TypeError, ValueError):
        safe_limit = 200

    messages = []
    for message in db.list_all_index_messages():
        if _message_matches_query(scope.get('query', {}), message):
            projected = dict(message)
            if not include_body_text:
                projected.pop('bodyText', None)
            messages.append(projected)
        if len(messages) >= safe_limit:
            break
    return messages


def scope_messages_for_summary(scope_id: str, limit: int = 200) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    scope = get_saved_scope(scope_id)
    if scope is None:
        raise LookupError(f'Saved scope {scope_id!r} not found')
    messages = list_messages_for_scope(scope_id, limit=limit, include_body_text=True)
    return scope, messages
