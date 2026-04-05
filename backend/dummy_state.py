from __future__ import annotations

from copy import deepcopy
from threading import Lock
from typing import Any


class _DummySessionStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._next_undo_id = 1
        self._jobs: dict[str, dict[str, Any]] = {}
        self._logs: list[dict[str, Any]] = []
        self._undo_stack: list[dict[str, Any]] = []

    def reset(self) -> None:
        with self._lock:
            self._next_undo_id = 1
            self._jobs = {}
            self._logs = []
            self._undo_stack = []

    def insert_job(
        self,
        job_id: str,
        created_at: str,
        criteria: dict[str, Any],
        summary_length: int,
        summary_text: str,
        messages: list[dict[str, Any]],
    ) -> None:
        job = {
            "id": job_id,
            "created_at": created_at,
            "criteria_json": deepcopy(criteria),
            "summary_length": summary_length,
            "summary_text": summary_text,
            "messages_json": deepcopy(messages),
        }
        with self._lock:
            self._jobs[job_id] = job

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return deepcopy(job) if job is not None else None

    def list_logs(self) -> list[dict[str, Any]]:
        with self._lock:
            ordered = sorted(
                self._logs,
                key=lambda item: (str(item.get("timestamp", "")), str(item.get("id", ""))),
                reverse=True,
            )
            return deepcopy(ordered)

    def insert_log(
        self,
        log_id: str,
        timestamp: str,
        action: str,
        status: str,
        details: str,
        job_id: str | None = None,
    ) -> None:
        log = {
            "id": log_id,
            "timestamp": timestamp,
            "action": action,
            "status": status,
            "details": details,
            "job_id": job_id,
        }
        with self._lock:
            self._logs.append(log)

    def push_undo(self, payload: dict[str, Any], created_at: str) -> None:
        with self._lock:
            entry = {
                "id": self._next_undo_id,
                "created_at": created_at,
                "payload_json": deepcopy(payload),
            }
            self._next_undo_id += 1
            self._undo_stack.append(entry)

    def pop_undo(self) -> dict[str, Any] | None:
        with self._lock:
            if not self._undo_stack:
                return None
            entry = self._undo_stack.pop()
            return deepcopy(entry["payload_json"])

    def list_undoable_log_ids(self) -> set[str]:
        with self._lock:
            return {
                str(entry["payload_json"].get("log_id"))
                for entry in self._undo_stack
                if isinstance(entry.get("payload_json"), dict) and entry["payload_json"].get("log_id")
            }

    def pop_undo_by_log_id(self, log_id: str) -> dict[str, Any] | None:
        with self._lock:
            for index in range(len(self._undo_stack) - 1, -1, -1):
                payload = self._undo_stack[index].get("payload_json")
                if isinstance(payload, dict) and payload.get("log_id") == log_id:
                    entry = self._undo_stack.pop(index)
                    return deepcopy(entry["payload_json"])
        return None

    def counts(self) -> dict[str, int]:
        with self._lock:
            return {
                "jobs": len(self._jobs),
                "logs": len(self._logs),
                "undo": len(self._undo_stack),
            }


_STORE = _DummySessionStore()


def reset_dummy_session_store() -> None:
    _STORE.reset()


def insert_job(
    job_id: str,
    created_at: str,
    criteria: dict[str, Any],
    summary_length: int,
    summary_text: str,
    messages: list[dict[str, Any]],
) -> None:
    _STORE.insert_job(job_id, created_at, criteria, summary_length, summary_text, messages)


def get_job(job_id: str) -> dict[str, Any] | None:
    return _STORE.get_job(job_id)


def list_logs() -> list[dict[str, Any]]:
    return _STORE.list_logs()


def insert_log(
    log_id: str,
    timestamp: str,
    action: str,
    status: str,
    details: str,
    job_id: str | None = None,
) -> None:
    _STORE.insert_log(log_id, timestamp, action, status, details, job_id)


def push_undo(payload: dict[str, Any], created_at: str) -> None:
    _STORE.push_undo(payload, created_at)


def pop_undo() -> dict[str, Any] | None:
    return _STORE.pop_undo()


def list_undoable_log_ids() -> set[str]:
    return _STORE.list_undoable_log_ids()


def pop_undo_by_log_id(log_id: str) -> dict[str, Any] | None:
    return _STORE.pop_undo_by_log_id(log_id)


def dummy_store_counts() -> dict[str, int]:
    return _STORE.counts()
