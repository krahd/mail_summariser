from datetime import datetime
from uuid import uuid4

from db import insert_log


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def log_action(action: str, status: str, details: str, job_id: str | None = None) -> None:
    insert_log(
        log_id=f"log-{uuid4()}",
        timestamp=now_iso(),
        action=action,
        status=status,
        details=details,
        job_id=job_id,
    )
