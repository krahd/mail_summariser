from __future__ import annotations

import json
import sqlite3
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


def get_job(job_id: str) -> dict[str, Any] | None:
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
    removed = {}
    with _connect() as conn:
        # Map table names to user-facing keys (undo_stack -> undo)
        tables = (('settings', 'settings'), ('jobs', 'jobs'),
                  ('logs', 'logs'), ('undo_stack', 'undo'))
        for table, key in tables:
            removed[key] = int(conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0])
            conn.execute(f'DELETE FROM {table}')
    for key, value in default_settings.items():
        set_setting(key, value)
    return removed
