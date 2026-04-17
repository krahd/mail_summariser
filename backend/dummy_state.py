from __future__ import annotations

from copy import deepcopy
from typing import Any

_dummy_jobs: dict[str, dict[str, Any]] = {}
_dummy_logs: list[dict[str, Any]] = []
_dummy_undo_stack: dict[str, dict[str, Any]] = {}


def reset_dummy_session_store() -> None:
    _dummy_jobs.clear()
    _dummy_logs.clear()
    _dummy_undo_stack.clear()


def insert_job(job_id: str, created_at: str, criteria: dict[str, Any], summary_length: int, summary_text: str, messages: list[dict[str, Any]]) -> None:
    _dummy_jobs[job_id] = {
        'id': job_id,
        'created_at': created_at,
        'criteria_json': deepcopy(criteria),
        'summary_length': summary_length,
        'summary_text': summary_text,
        'messages_json': deepcopy(messages),
    }


def get_job(job_id: str) -> dict[str, Any] | None:
    job = _dummy_jobs.get(job_id)
    return deepcopy(job) if job is not None else None


def insert_log(log_id: str, timestamp: str, action: str, status: str, details: str, job_id: str | None = None) -> None:
    _dummy_logs.append({
        'id': log_id,
        'timestamp': timestamp,
        'action': action,
        'status': status,
        'details': details,
        'job_id': job_id,
    })


def list_logs() -> list[dict[str, Any]]:
    return deepcopy(_dummy_logs)


def push_undo(payload: dict[str, Any], created_at: str) -> None:
    payload_copy = deepcopy(payload)
    payload_copy['created_at'] = created_at
    _dummy_undo_stack[payload['log_id']] = payload_copy


def pop_undo_by_log_id(log_id: str) -> dict[str, Any] | None:
    payload = _dummy_undo_stack.pop(log_id, None)
    return deepcopy(payload) if payload else None


def pop_latest_undo() -> dict[str, Any] | None:
    """Pop and return the most recently pushed undo payload, or None if none exist."""
    if not _dummy_undo_stack:
        return None
    # dict preserves insertion order; take the last inserted key
    last_key = next(reversed(_dummy_undo_stack))
    return pop_undo_by_log_id(last_key)


def list_undoable_log_ids() -> set[str]:
    return set(_dummy_undo_stack)


def dummy_store_counts() -> dict[str, int]:
    return {'jobs': len(_dummy_jobs), 'logs': len(_dummy_logs), 'undo': len(_dummy_undo_stack)}
