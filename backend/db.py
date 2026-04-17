import json
import sqlite3
from contextlib import contextmanager
from typing import Any

from backend.config import DB_PATH

UNDO_LOG_ACTIONS = {
    'mark_read': 'mark_read',
    'tag_add': 'tag_summarised',
    'email_sent': 'email_summary',
}


def _dict_factory(cursor: sqlite3.Cursor, row: tuple[Any, ...]) -> dict[str, Any]:
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def _ensure_db_parent_dir() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_conn():
    _ensure_db_parent_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = _dict_factory
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            '''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS logs (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                details TEXT NOT NULL,
                job_id TEXT
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                criteria_json TEXT NOT NULL,
                summary_length INTEGER NOT NULL,
                summary_text TEXT NOT NULL,
                messages_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS undo_stack (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            '''
        )


def get_setting(key: str, default: Any = None) -> Any:
    with get_conn() as conn:
        row = conn.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
        if row is None:
            return default
        return json.loads(row['value'])


def set_setting(key: str, value: Any) -> None:
    with get_conn() as conn:
        conn.execute(
            '''
            INSERT INTO settings(key, value)
            VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            ''',
            (key, json.dumps(value)),
        )


def list_settings() -> dict[str, Any]:
    with get_conn() as conn:
        rows = conn.execute('SELECT key, value FROM settings').fetchall()
        return {row['key']: json.loads(row['value']) for row in rows}


def reset_database(default_settings: dict[str, Any]) -> dict[str, int]:
    with get_conn() as conn:
        counts = {
            'settings': int(conn.execute('SELECT COUNT(*) AS count FROM settings').fetchone()['count']),
            'logs': int(conn.execute('SELECT COUNT(*) AS count FROM logs').fetchone()['count']),
            'jobs': int(conn.execute('SELECT COUNT(*) AS count FROM jobs').fetchone()['count']),
            'undo': int(conn.execute('SELECT COUNT(*) AS count FROM undo_stack').fetchone()['count']),
        }
        conn.execute('DELETE FROM settings')
        conn.execute('DELETE FROM logs')
        conn.execute('DELETE FROM jobs')
        conn.execute('DELETE FROM undo_stack')
        for key, value in default_settings.items():
            conn.execute('INSERT INTO settings(key, value) VALUES (?, ?)', (key, json.dumps(value)))
    return counts


def insert_job(job_id: str, created_at: str, criteria: dict[str, Any], summary_length: int, summary_text: str, messages: list[dict[str, Any]]) -> None:
    with get_conn() as conn:
        conn.execute(
            '''
            INSERT INTO jobs(id, created_at, criteria_json, summary_length, summary_text, messages_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (job_id, created_at, json.dumps(criteria), summary_length, summary_text, json.dumps(messages)),
        )


def get_job(job_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute('SELECT * FROM jobs WHERE id = ?', (job_id,)).fetchone()
        if row is None:
            return None
        row['criteria_json'] = json.loads(row['criteria_json'])
        row['messages_json'] = json.loads(row['messages_json'])
        return row


def list_logs() -> list[dict[str, Any]]:
    with get_conn() as conn:
        return conn.execute('SELECT * FROM logs ORDER BY timestamp DESC, id DESC').fetchall()


def insert_log(log_id: str, timestamp: str, action: str, status: str, details: str, job_id: str | None = None) -> None:
    with get_conn() as conn:
        conn.execute(
            'INSERT INTO logs(id, timestamp, action, status, details, job_id) VALUES (?, ?, ?, ?, ?, ?)',
            (log_id, timestamp, action, status, details, job_id),
        )


def push_undo(payload: dict[str, Any], created_at: str) -> None:
    with get_conn() as conn:
        conn.execute('INSERT INTO undo_stack(created_at, payload_json) VALUES (?, ?)', (created_at, json.dumps(payload)))


def pop_undo() -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute('SELECT id, payload_json FROM undo_stack ORDER BY id DESC LIMIT 1').fetchone()
        if row is None:
            return None
        conn.execute('DELETE FROM undo_stack WHERE id = ?', (row['id'],))
        return json.loads(row['payload_json'])


def list_undoable_log_ids() -> set[str]:
    undoable_log_ids: set[str] = set()
    with get_conn() as conn:
        rows = conn.execute('SELECT payload_json FROM undo_stack ORDER BY id ASC').fetchall()
        for row in rows:
            payload = json.loads(row['payload_json'])
            log_id = payload.get('log_id')
            if isinstance(log_id, str) and log_id:
                undoable_log_ids.add(log_id)
    return undoable_log_ids


def pop_undo_by_log_id(log_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        rows = conn.execute('SELECT id, payload_json FROM undo_stack ORDER BY id DESC').fetchall()
        for row in rows:
            payload = json.loads(row['payload_json'])
            if payload.get('log_id') == log_id:
                conn.execute('DELETE FROM undo_stack WHERE id = ?', (row['id'],))
                return payload
    return None
