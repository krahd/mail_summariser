import json
import sqlite3
from contextlib import contextmanager
from typing import Any

from config import DB_PATH

UNDO_LOG_ACTIONS = {
    "mark_read": "mark_read",
    "tag_add": "tag_summarised",
    "email_sent": "email_summary",
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
            """
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
            """
        )
    backfill_legacy_undo_log_ids()


def _decode_undo_payload(raw_payload: Any) -> dict[str, Any] | None:
    try:
        payload = json.loads(raw_payload)
    except (TypeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _undo_payload_log_action(payload: dict[str, Any]) -> str | None:
    payload_type = payload.get("type")
    if not isinstance(payload_type, str):
        return None
    return UNDO_LOG_ACTIONS.get(payload_type)


def backfill_legacy_undo_log_ids() -> int:
    updated_rows = 0
    with get_conn() as conn:
        undo_rows = conn.execute(
            "SELECT id, created_at, payload_json FROM undo_stack ORDER BY id ASC"
        ).fetchall()
        if not undo_rows:
            return 0

        action_placeholders = ", ".join("?" for _ in UNDO_LOG_ACTIONS.values())
        log_rows = conn.execute(
            f"""
            SELECT id, timestamp, action, job_id
            FROM logs
            WHERE action IN ({action_placeholders})
            ORDER BY timestamp ASC, id ASC
            """,
            tuple(UNDO_LOG_ACTIONS.values()),
        ).fetchall()
        if not log_rows:
            return 0

        logs_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for log in log_rows:
            job_id = log.get("job_id")
            key = (str(log["action"]), job_id if isinstance(job_id, str) else "")
            logs_by_key.setdefault(key, []).append(log)

        used_log_ids: set[str] = set()
        decoded_payloads: dict[int, dict[str, Any]] = {}
        for row in undo_rows:
            payload = _decode_undo_payload(row["payload_json"])
            if payload is None:
                continue
            decoded_payloads[row["id"]] = payload
            log_id = payload.get("log_id")
            if isinstance(log_id, str) and log_id:
                used_log_ids.add(log_id)

        for row in undo_rows:
            payload = decoded_payloads.get(row["id"])
            if payload is None:
                continue
            existing_log_id = payload.get("log_id")
            if isinstance(existing_log_id, str) and existing_log_id:
                continue

            action = _undo_payload_log_action(payload)
            if action is None:
                continue

            job_id = payload.get("job_id")
            job_key = job_id if isinstance(job_id, str) else ""
            candidates = logs_by_key.get((action, job_key), [])
            if not candidates:
                continue

            created_at = row["created_at"] if isinstance(row["created_at"], str) else ""
            match: dict[str, Any] | None = None
            for candidate in reversed(candidates):
                candidate_id = candidate["id"]
                if candidate_id in used_log_ids:
                    continue
                timestamp = candidate["timestamp"] if isinstance(candidate["timestamp"], str) else ""
                if created_at and timestamp and timestamp > created_at:
                    continue
                match = candidate
                break

            if match is None:
                for candidate in reversed(candidates):
                    candidate_id = candidate["id"]
                    if candidate_id not in used_log_ids:
                        match = candidate
                        break

            if match is None:
                continue

            payload["log_id"] = match["id"]
            conn.execute(
                "UPDATE undo_stack SET payload_json = ? WHERE id = ?",
                (json.dumps(payload), row["id"]),
            )
            used_log_ids.add(match["id"])
            updated_rows += 1

    return updated_rows


def get_setting(key: str, default: Any = None) -> Any:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        return json.loads(row["value"])


def set_setting(key: str, value: Any) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO settings(key, value)
            VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, json.dumps(value)),
        )


def list_settings() -> dict[str, Any]:
    with get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {row["key"]: json.loads(row["value"]) for row in rows}


def insert_job(job_id: str, created_at: str, criteria: dict[str, Any], summary_length: int, summary_text: str, messages: list[dict[str, Any]]) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO jobs(id, created_at, criteria_json, summary_length, summary_text, messages_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                created_at,
                json.dumps(criteria),
                summary_length,
                summary_text,
                json.dumps(messages),
            ),
        )


def get_job(job_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        row["criteria_json"] = json.loads(row["criteria_json"])
        row["messages_json"] = json.loads(row["messages_json"])
        return row


def list_logs() -> list[dict[str, Any]]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM logs ORDER BY timestamp DESC, id DESC").fetchall()


def insert_log(log_id: str, timestamp: str, action: str, status: str, details: str, job_id: str | None = None) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO logs(id, timestamp, action, status, details, job_id) VALUES (?, ?, ?, ?, ?, ?)",
            (log_id, timestamp, action, status, details, job_id),
        )


def push_undo(payload: dict[str, Any], created_at: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO undo_stack(created_at, payload_json) VALUES (?, ?)",
            (created_at, json.dumps(payload)),
        )


def pop_undo() -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, payload_json FROM undo_stack ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        conn.execute("DELETE FROM undo_stack WHERE id = ?", (row["id"],))
        return json.loads(row["payload_json"])


def list_undoable_log_ids() -> set[str]:
    undoable_log_ids: set[str] = set()
    with get_conn() as conn:
        rows = conn.execute("SELECT payload_json FROM undo_stack ORDER BY id ASC").fetchall()
        for row in rows:
            payload = _decode_undo_payload(row["payload_json"])
            if payload is None:
                continue
            log_id = payload.get("log_id")
            if isinstance(log_id, str) and log_id:
                undoable_log_ids.add(log_id)
    return undoable_log_ids


def pop_undo_by_log_id(log_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, payload_json FROM undo_stack ORDER BY id DESC"
        ).fetchall()
        for row in rows:
            payload = _decode_undo_payload(row["payload_json"])
            if payload is not None and payload.get("log_id") == log_id:
                conn.execute("DELETE FROM undo_stack WHERE id = ?", (row["id"],))
                return payload
    return None
