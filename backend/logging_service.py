from datetime import datetime
from uuid import uuid4

from backend.db import insert_log


def now_iso() -> str:
    return datetime.now().isoformat(timespec='seconds')


def log_action(action: str, status: str, details: str, job_id: str | None = None) -> str:
    log_id = f'log-{uuid4()}'
    insert_log(log_id=log_id, timestamp=now_iso(), action=action, status=status, details=details, job_id=job_id)
    return log_id
