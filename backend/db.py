from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.config import DB_PATH as DEFAULT_DB_PATH

DB_PATH = DEFAULT_DB_PATH


def _connect() -> sqlite3.Connection:
    path = Path(DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _now_iso() -> str:
    return datetime.now().isoformat(timespec='seconds')


def _first_text(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ''


def _string_list(value: Any) -> list[str]:
    if value is None or value == '':
        return []
    items: list[Any]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            items = [value]
        else:
            items = parsed if isinstance(parsed, list) else [parsed]
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = [value]

    results: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item or '').strip()
        if not text or text in seen:
            continue
        seen.add(text)
        results.append(text)
    return results


def _preview_text(value: Any, limit: int = 280) -> str:
    text = str(value or '').strip()
    if not text:
        return ''
    return ' '.join(text.split())[:limit]


def _bool_int(value: Any, default: bool = False) -> int:
    if value is None:
        return 1 if default else 0
    return 1 if bool(value) else 0


def _decode_json_list(value: Any) -> list[str]:
    if value in (None, ''):
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    try:
        decoded = json.loads(str(value))
    except json.JSONDecodeError:
        return _string_list(value)
    if isinstance(decoded, list):
        return [str(item) for item in decoded if str(item).strip()]
    return _string_list(decoded)


def _decode_index_message(row: sqlite3.Row) -> dict[str, Any]:
    return {
        'id': row['id'],
        'accountId': row['account_id'],
        'mailboxPath': row['mailbox_path'],
        'uid': row['uid'],
        'messageIdHeader': row['message_id_header'],
        'subject': row['subject'],
        'sender': row['sender'],
        'recipients': _decode_json_list(row['recipients_json']),
        'date': row['date'],
        'flags': _decode_json_list(row['flags_json']),
        'keywords': _decode_json_list(row['keywords_json']),
        'listId': row['list_id'],
        'bodyPreview': row['body_preview'],
        'bodyCached': bool(row['body_cached']),
        'bodyText': row['body_text'],
        'lastSeenAt': row['last_seen_at'],
    }


def _decode_saved_scope(row: sqlite3.Row) -> dict[str, Any]:
    try:
        query = json.loads(row['query_json'])
    except (TypeError, ValueError, json.JSONDecodeError):
        query = {}
    if not isinstance(query, dict):
        query = {}
    return {
        'id': row['id'],
        'name': row['name'],
        'description': row['description'],
        'query': query,
        'sortOrder': int(row['sort_order'] or 0),
        'createdAt': row['created_at'],
        'updatedAt': row['updated_at'],
    }


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                criteria_json TEXT NOT NULL,
                summary_length INTEGER NOT NULL,
                summary_text TEXT NOT NULL,
                messages_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS logs (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                details TEXT NOT NULL,
                job_id TEXT
            );
            CREATE TABLE IF NOT EXISTS undo_stack (
                log_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS mail_accounts_index (
                id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                username TEXT NOT NULL,
                imap_host TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS mailboxes_index (
                id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                path TEXT NOT NULL,
                delimiter TEXT,
                selectable INTEGER NOT NULL,
                flags_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(account_id, path)
            );
            CREATE TABLE IF NOT EXISTS messages_index (
                id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                mailbox_path TEXT NOT NULL,
                uid TEXT NOT NULL,
                message_id_header TEXT NOT NULL DEFAULT '',
                subject TEXT NOT NULL,
                sender TEXT NOT NULL,
                recipients_json TEXT NOT NULL,
                date TEXT NOT NULL,
                flags_json TEXT NOT NULL,
                keywords_json TEXT NOT NULL,
                list_id TEXT NOT NULL,
                body_preview TEXT NOT NULL,
                body_cached INTEGER NOT NULL DEFAULT 0,
                body_text TEXT NOT NULL DEFAULT '',
                last_seen_at TEXT NOT NULL,
                UNIQUE(account_id, mailbox_path, uid)
            );
            CREATE TABLE IF NOT EXISTS sync_state (
                account_id TEXT NOT NULL,
                mailbox_path TEXT NOT NULL,
                uidvalidity TEXT NOT NULL DEFAULT '',
                uidnext TEXT NOT NULL DEFAULT '',
                last_sync_at TEXT NOT NULL,
                PRIMARY KEY(account_id, mailbox_path)
            );
            CREATE TABLE IF NOT EXISTS saved_scopes (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                query_json TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )


def set_setting(key: str, value: Any) -> None:
    with _connect() as conn:
        conn.execute(
            'INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value',
            (key, json.dumps(value)),
        )


def list_settings() -> dict[str, Any]:
    with _connect() as conn:
        rows = conn.execute('SELECT key, value FROM settings').fetchall()
    return {row['key']: json.loads(row['value']) for row in rows}


def insert_job(job_id: str, created_at: str, criteria: dict[str, Any], summary_length: int, summary_text: str, messages: list[dict[str, Any]]) -> None:
    with _connect() as conn:
        conn.execute(
            'INSERT INTO jobs(id, created_at, criteria_json, summary_length, summary_text, messages_json) VALUES(?, ?, ?, ?, ?, ?)',
            (job_id, created_at, json.dumps(criteria),
             summary_length, summary_text, json.dumps(messages)),
        )


def get_job(job_id: str | None) -> dict[str, Any] | None:
    if job_id is None:
        return None
    with _connect() as conn:
        row = conn.execute('SELECT * FROM jobs WHERE id = ?', (job_id,)).fetchone()
    if row is None:
        return None
    return {
        'id': row['id'],
        'created_at': row['created_at'],
        'criteria_json': json.loads(row['criteria_json']),
        'summary_length': row['summary_length'],
        'summary_text': row['summary_text'],
        'messages_json': json.loads(row['messages_json']),
    }


def insert_log(log_id: str, timestamp: str, action: str, status: str, details: str, job_id: str | None = None) -> None:
    with _connect() as conn:
        conn.execute(
            'INSERT INTO logs(id, timestamp, action, status, details, job_id) VALUES(?, ?, ?, ?, ?, ?)',
            (log_id, timestamp, action, status, details, job_id),
        )


def list_logs() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute('SELECT * FROM logs ORDER BY timestamp, id').fetchall()
    return [dict(row) for row in rows]


def push_undo(payload: dict[str, Any], created_at: str) -> None:
    with _connect() as conn:
        conn.execute(
            'INSERT OR REPLACE INTO undo_stack(log_id, payload_json, created_at) VALUES(?, ?, ?)',
            (payload['log_id'], json.dumps(payload), created_at),
        )


def pop_undo_by_log_id(log_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute('SELECT payload_json FROM undo_stack WHERE log_id = ?',
                           (log_id,)).fetchone()
        if row is None:
            return None
        conn.execute('DELETE FROM undo_stack WHERE log_id = ?', (log_id,))
    return json.loads(row['payload_json'])


def pop_latest_undo() -> dict[str, Any] | None:
    """Pop and return the most recently pushed undo payload from the DB, or None if none exist."""
    with _connect() as conn:
        row = conn.execute(
            'SELECT log_id FROM undo_stack ORDER BY created_at DESC LIMIT 1').fetchone()
        if row is None:
            return None
        log_id = row['log_id']
    return pop_undo_by_log_id(log_id)


def list_undoable_log_ids() -> set[str]:
    with _connect() as conn:
        rows = conn.execute('SELECT log_id FROM undo_stack').fetchall()
    return {row['log_id'] for row in rows}


def reset_database(default_settings: dict[str, Any]) -> dict[str, int]:
    init_db()
    removed = {}
    with _connect() as conn:
        # Map table names to user-facing keys (undo_stack -> undo)
        tables = (
            ('settings', 'settings'),
            ('jobs', 'jobs'),
            ('logs', 'logs'),
            ('undo_stack', 'undo'),
            ('mail_accounts_index', 'mail_accounts_index'),
            ('mailboxes_index', 'mailboxes_index'),
            ('messages_index', 'messages_index'),
            ('sync_state', 'sync_state'),
            ('saved_scopes', 'saved_scopes'),
        )
        for table, key in tables:
            removed[key] = int(conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0])
            conn.execute(f'DELETE FROM {table}')
    for key, value in default_settings.items():
        set_setting(key, value)
    try:
        from backend.saved_scope_service import ensure_default_saved_scopes  # pylint: disable=import-outside-toplevel

        ensure_default_saved_scopes()
    except Exception:  # pylint: disable=broad-except
        pass
    return removed


def upsert_saved_scope(scope: dict[str, Any], created_at: str | None = None,
                       updated_at: str | None = None) -> None:
    init_db()
    scope_id = _first_text(scope, 'id')
    if not scope_id:
        raise ValueError('Scope id is required')
    name = _first_text(scope, 'name') or scope_id
    description = _first_text(scope, 'description')
    query = scope.get('query') if scope.get('query') is not None else {}
    if not isinstance(query, dict):
        raise ValueError('Scope query must be a JSON object')
    sort_order_value = scope.get('sortOrder', scope.get('sort_order', 0))
    try:
        sort_order = int(sort_order_value or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError('Scope sortOrder must be an integer') from exc
    created_at_value = str(created_at or scope.get('createdAt') or scope.get('created_at') or _now_iso())
    updated_at_value = str(updated_at or scope.get('updatedAt') or scope.get('updated_at') or _now_iso())

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO saved_scopes(id, name, description, query_json, sort_order, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                query_json = excluded.query_json,
                sort_order = excluded.sort_order,
                updated_at = excluded.updated_at
            """,
            (scope_id, name, description, json.dumps(query), sort_order, created_at_value, updated_at_value),
        )


def list_saved_scopes() -> list[dict[str, Any]]:
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            'SELECT * FROM saved_scopes ORDER BY sort_order, created_at, id'
        ).fetchall()
    return [_decode_saved_scope(row) for row in rows]


def get_saved_scope(scope_id: str) -> dict[str, Any] | None:
    init_db()
    scope_id_value = str(scope_id or '').strip()
    if not scope_id_value:
        return None
    with _connect() as conn:
        row = conn.execute('SELECT * FROM saved_scopes WHERE id = ?', (scope_id_value,)).fetchone()
    if row is None:
        return None
    return _decode_saved_scope(row)


def delete_saved_scope(scope_id: str) -> bool:
    init_db()
    scope_id_value = str(scope_id or '').strip()
    if not scope_id_value:
        return False
    with _connect() as conn:
        result = conn.execute('DELETE FROM saved_scopes WHERE id = ?', (scope_id_value,))
    return bool(result.rowcount)


def upsert_index_account(account: dict[str, Any], updated_at: str | None = None) -> None:
    init_db()
    account_id = _first_text(account, 'id', 'accountId')
    if not account_id:
        raise ValueError('Account id is required')
    display_name = _first_text(account, 'displayName', 'display_name') or account_id
    username = _first_text(account, 'username')
    imap_host = _first_text(account, 'imapHost', 'imap_host')
    enabled = _bool_int(account.get('enabled'), default=True)
    updated_at_value = str(updated_at or account.get('updatedAt') or account.get('updated_at') or _now_iso())

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO mail_accounts_index(id, display_name, username, imap_host, enabled, updated_at)
            VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                display_name = excluded.display_name,
                username = excluded.username,
                imap_host = excluded.imap_host,
                enabled = excluded.enabled,
                updated_at = excluded.updated_at
            """,
            (account_id, display_name, username, imap_host, enabled, updated_at_value),
        )


def upsert_index_mailbox(account_id: str, mailbox: dict[str, Any], updated_at: str | None = None) -> None:
    init_db()
    mailbox_account_id = str(account_id or mailbox.get('accountId') or mailbox.get('account_id') or '').strip()
    path = _first_text(mailbox, 'path', 'mailboxPath', 'mailbox_path')
    if not mailbox_account_id:
        raise ValueError('Account id is required')
    if not path:
        raise ValueError('Mailbox path is required')
    delimiter = mailbox.get('delimiter')
    selectable = _bool_int(mailbox.get('selectable'), default=True)
    flags_json = json.dumps(_string_list(mailbox.get('flags') or mailbox.get('flags_json')))
    updated_at_value = str(updated_at or mailbox.get('updatedAt') or mailbox.get('updated_at') or _now_iso())

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO mailboxes_index(id, account_id, path, delimiter, selectable, flags_json, updated_at)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id, path) DO UPDATE SET
                delimiter = excluded.delimiter,
                selectable = excluded.selectable,
                flags_json = excluded.flags_json,
                updated_at = excluded.updated_at
            """,
            (
                _first_text(mailbox, 'id') or f'{mailbox_account_id}|{path}',
                mailbox_account_id,
                path,
                delimiter,
                selectable,
                flags_json,
                updated_at_value,
            ),
        )


def upsert_index_message(message: dict[str, Any], last_seen_at: str | None = None) -> None:
    init_db()
    account_id = _first_text(message, 'accountId', 'account_id')
    mailbox_path = _first_text(message, 'mailboxPath', 'mailbox_path')
    uid = _first_text(message, 'uid')
    if not account_id:
        raise ValueError('Account id is required')
    if not mailbox_path:
        raise ValueError('Mailbox path is required')
    if not uid:
        raise ValueError('UID is required')

    message_id = _first_text(message, 'id') or f'{account_id}|{mailbox_path}|{uid}'
    message_id_header = _first_text(message, 'messageIdHeader', 'message_id_header')
    subject = _first_text(message, 'subject')
    sender = _first_text(message, 'sender')
    recipients_json = json.dumps(_string_list(
        message.get('recipients') if message.get('recipients') is not None else
        message.get('recipients_json') if message.get('recipients_json') is not None else
        message.get('recipient')
    ))
    date = _first_text(message, 'date')
    flags_json = json.dumps(_string_list(
        message.get('flags') if message.get('flags') is not None else message.get('flags_json')
    ))
    keywords_json = json.dumps(_string_list(
        message.get('keywords') if message.get('keywords') is not None else message.get('keywords_json')
    ))
    list_id = _first_text(message, 'listId', 'list_id')
    body_text = _first_text(message, 'bodyText', 'body_text')
    body_preview = _first_text(message, 'bodyPreview', 'body_preview') or _preview_text(body_text)
    body_cached_value = message.get('bodyCached', message.get('body_cached'))
    body_cached = _bool_int(body_cached_value, default=bool(body_text))
    last_seen_at_value = str(last_seen_at or message.get('lastSeenAt') or message.get('last_seen_at') or _now_iso())

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO messages_index(
                id, account_id, mailbox_path, uid, message_id_header, subject, sender,
                recipients_json, date, flags_json, keywords_json, list_id,
                body_preview, body_cached, body_text, last_seen_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id, mailbox_path, uid) DO UPDATE SET
                id = excluded.id,
                message_id_header = CASE WHEN excluded.message_id_header <> '' THEN excluded.message_id_header ELSE messages_index.message_id_header END,
                subject = CASE WHEN excluded.subject <> '' THEN excluded.subject ELSE messages_index.subject END,
                sender = CASE WHEN excluded.sender <> '' THEN excluded.sender ELSE messages_index.sender END,
                recipients_json = CASE WHEN excluded.recipients_json <> '' THEN excluded.recipients_json ELSE messages_index.recipients_json END,
                date = CASE WHEN excluded.date <> '' THEN excluded.date ELSE messages_index.date END,
                flags_json = CASE WHEN excluded.flags_json <> '' THEN excluded.flags_json ELSE messages_index.flags_json END,
                keywords_json = CASE WHEN excluded.keywords_json <> '' THEN excluded.keywords_json ELSE messages_index.keywords_json END,
                list_id = CASE WHEN excluded.list_id <> '' THEN excluded.list_id ELSE messages_index.list_id END,
                body_preview = CASE WHEN excluded.body_preview <> '' THEN excluded.body_preview ELSE messages_index.body_preview END,
                body_cached = CASE WHEN excluded.body_cached = 1 THEN 1 ELSE messages_index.body_cached END,
                body_text = CASE WHEN excluded.body_text <> '' THEN excluded.body_text ELSE messages_index.body_text END,
                last_seen_at = excluded.last_seen_at
            """,
            (
                message_id,
                account_id,
                mailbox_path,
                uid,
                message_id_header,
                subject,
                sender,
                recipients_json,
                date,
                flags_json,
                keywords_json,
                list_id,
                body_preview,
                body_cached,
                body_text,
                last_seen_at_value,
            ),
        )


def _message_matches_criteria(message: dict[str, Any], criteria: dict[str, Any]) -> bool:
    account_id = str(criteria.get('accountId') or '').strip()
    mailbox_path = str(criteria.get('mailbox') or criteria.get('mailboxPath') or criteria.get('mailbox_path') or '').strip()
    unread = criteria.get('unread')
    flagged = criteria.get('flagged')
    tag = str(criteria.get('tag') or '').strip().lower()
    keyword = str(criteria.get('keyword') or '').strip().lower()
    list_id = str(criteria.get('listId') or '').strip().lower()
    sender = str(criteria.get('sender') or '').strip().lower()

    if account_id and message['accountId'] != account_id:
        return False
    if mailbox_path and message['mailboxPath'] != mailbox_path:
        return False
    if unread is not None:
        is_unread = '\\seen' not in {flag.lower() for flag in message['flags']}
        if bool(unread) != is_unread:
            return False
    if flagged is not None:
        is_flagged = '\\flagged' in {flag.lower() for flag in message['flags']}
        if bool(flagged) != is_flagged:
            return False
    if tag and tag not in {item.lower() for item in message['keywords']}:
        return False
    if list_id and list_id not in str(message['listId']).lower():
        return False
    if sender and sender not in str(message['sender']).lower():
        return False
    if keyword:
        haystack = ' '.join([
            str(message['subject']),
            str(message['sender']),
            ' '.join(message['recipients']),
            str(message['date']),
            str(message['listId']),
            str(message['bodyPreview']),
            str(message['bodyText']),
            ' '.join(message['keywords']),
        ]).lower()
        if keyword not in haystack:
            return False
    return True


def list_index_messages(criteria: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    init_db()
    criteria = criteria or {}
    account_id = str(criteria.get('accountId') or '').strip()
    mailbox_path = str(criteria.get('mailbox') or criteria.get('mailboxPath') or criteria.get('mailbox_path') or '').strip()
    limit_value = criteria.get('limit', 100)
    try:
        limit = max(1, min(int(limit_value or 100), 500))
    except (TypeError, ValueError):
        limit = 100

    where_clauses: list[str] = []
    params: list[Any] = []
    if account_id:
        where_clauses.append('account_id = ?')
        params.append(account_id)
    if mailbox_path:
        where_clauses.append('mailbox_path = ?')
        params.append(mailbox_path)

    query = 'SELECT * FROM messages_index'
    if where_clauses:
        query += ' WHERE ' + ' AND '.join(where_clauses)
    query += ' ORDER BY last_seen_at DESC, id DESC'

    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()

    results: list[dict[str, Any]] = []
    for row in rows:
        message = _decode_index_message(row)
        if not _message_matches_criteria(message, criteria):
            continue
        results.append({
            key: value for key, value in message.items() if key != 'bodyText'
        })
        if len(results) >= limit:
            break
    return results


def list_all_index_messages() -> list[dict[str, Any]]:
    init_db()
    with _connect() as conn:
        rows = conn.execute('SELECT * FROM messages_index ORDER BY last_seen_at DESC, id DESC').fetchall()
    return [_decode_index_message(row) for row in rows]


def get_index_message(message_id: str) -> dict[str, Any] | None:
    init_db()
    if not message_id:
        return None
    with _connect() as conn:
        row = conn.execute('SELECT * FROM messages_index WHERE id = ?', (message_id,)).fetchone()
    if row is None:
        return None
    return _decode_index_message(row)


def update_sync_state(account_id: str, mailbox_path: str, uidvalidity: str = '',
                      uidnext: str = '', last_sync_at: str | None = None) -> None:
    init_db()
    account_id_value = str(account_id or '').strip()
    mailbox_path_value = str(mailbox_path or '').strip()
    if not account_id_value:
        raise ValueError('Account id is required')
    if not mailbox_path_value:
        raise ValueError('Mailbox path is required')
    last_sync_at_value = str(last_sync_at or _now_iso())

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO sync_state(account_id, mailbox_path, uidvalidity, uidnext, last_sync_at)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(account_id, mailbox_path) DO UPDATE SET
                uidvalidity = excluded.uidvalidity,
                uidnext = excluded.uidnext,
                last_sync_at = excluded.last_sync_at
            """,
            (account_id_value, mailbox_path_value, str(uidvalidity or ''), str(uidnext or ''), last_sync_at_value),
        )
