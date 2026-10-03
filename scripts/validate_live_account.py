#!/usr/bin/env python3
"""Read-only real-account acceptance probe for Mail Summariser.

Credentials are read from environment variables only and are never persisted.
The probe authenticates IMAP/SMTP, discovers mailboxes, and performs a bounded
read-only IMAP search. Its report deliberately excludes message content,
addresses, usernames, passwords, and server error payloads.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.mail_service import (  # noqa: E402
    MailServiceError,
    discover_mailboxes_for_account,
    search_messages,
    test_mail_connection,
)
from backend.schemas import SearchCriteria  # noqa: E402

OPT_IN = "MAIL_SUMMARISER_LIVE_ACCEPT"
MAX_LIMIT = 20
DEFAULT_LIMIT = 5


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _bool_env(env: Mapping[str, str], name: str, default: bool = True) -> bool:
    value = env.get(name)
    if value is None or not value.strip():
        return default
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")


def _int_env(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _required(env: Mapping[str, str], name: str) -> str:
    value = str(env.get(name, "")).strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def build_transient_settings(env: Mapping[str, str]) -> tuple[dict[str, Any], dict[str, Any], str, int]:
    username = _required(env, "MAIL_SUMMARISER_IMAP_USERNAME")
    imap_password = _required(env, "MAIL_SUMMARISER_IMAP_PASSWORD")
    imap_host = _required(env, "MAIL_SUMMARISER_IMAP_HOST")
    smtp_host = _required(env, "MAIL_SUMMARISER_SMTP_HOST")
    smtp_password = str(env.get("MAIL_SUMMARISER_SMTP_PASSWORD", "")).strip() or imap_password
    imap_port = _int_env(env, "MAIL_SUMMARISER_IMAP_PORT", 993)
    smtp_port = _int_env(env, "MAIL_SUMMARISER_SMTP_PORT", 465)
    requested_limit = _int_env(env, "MAIL_SUMMARISER_LIVE_LIMIT", DEFAULT_LIMIT)
    limit = max(1, min(requested_limit, MAX_LIMIT))
    preferred_mailbox = str(env.get("MAIL_SUMMARISER_LIVE_MAILBOX", "INBOX")).strip() or "INBOX"

    account = {
        "id": "live-acceptance",
        "displayName": "Live acceptance",
        "enabled": True,
        "imapHost": imap_host,
        "imapPort": imap_port,
        "imapUseSSL": _bool_env(env, "MAIL_SUMMARISER_IMAP_USE_SSL", True),
        "username": username,
        "imapPassword": imap_password,
        "smtpHost": smtp_host,
        "smtpPort": smtp_port,
        "smtpUseSSL": _bool_env(env, "MAIL_SUMMARISER_SMTP_USE_SSL", True),
        "smtpPassword": smtp_password,
        "indexMailboxes": [preferred_mailbox],
    }
    settings = {
        "dummyMode": False,
        "safeMode": True,
        "mailAccounts": [account],
        "imapHost": imap_host,
        "imapPort": imap_port,
        "imapUseSSL": account["imapUseSSL"],
        "username": username,
        "imapPassword": imap_password,
        "smtpHost": smtp_host,
        "smtpPort": smtp_port,
        "smtpUseSSL": account["smtpUseSSL"],
        "smtpPassword": smtp_password,
    }
    return settings, account, preferred_mailbox, limit


def _select_mailbox(mailboxes: list[dict[str, Any]], preferred: str) -> str:
    selectable = [
        str(item.get("path", ""))
        for item in mailboxes
        if item.get("selectable") and str(item.get("path", "")).strip()
    ]
    if not selectable:
        raise RuntimeError("No selectable mailbox was discovered")
    for path in selectable:
        if path.casefold() == preferred.casefold():
            return path
    for path in selectable:
        if path.casefold() == "inbox":
            return path
    return selectable[0]


def run_acceptance(env: Mapping[str, str]) -> dict[str, Any]:
    if not _truthy(env.get(OPT_IN)):
        raise ValueError(f"Set {OPT_IN}=1 to confirm an intentional live-account read-only acceptance run")

    settings, account, preferred_mailbox, limit = build_transient_settings(env)
    connection = test_mail_connection(settings)
    imap_status = str(connection.get("imap", {}).get("status", "error"))
    smtp_status = str(connection.get("smtp", {}).get("status", "error"))
    if imap_status != "ok" or smtp_status != "ok":
        raise RuntimeError("Live connection check did not pass for both IMAP and SMTP")

    mailboxes = discover_mailboxes_for_account(account)
    chosen = _select_mailbox(mailboxes, preferred_mailbox)
    criteria = SearchCriteria(accountIds=["live-acceptance"], mailboxes=[chosen], limit=limit)
    messages = search_messages(criteria, settings)

    selectable_count = sum(1 for item in mailboxes if item.get("selectable"))
    return {
        "status": "passed",
        "mode": "live-read-only",
        "safeMode": True,
        "checkedAt": datetime.now(timezone.utc).isoformat(),
        "connection": {"imap": imap_status, "smtp": smtp_status},
        "mailboxes": {
            "discovered": len(mailboxes),
            "selectable": selectable_count,
            "selected": chosen,
        },
        "search": {"limit": limit, "fetched": len(messages)},
        "privacy": {
            "credentialsPersisted": False,
            "messageContentReported": False,
            "identityReported": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the read-only real-account acceptance gate for Mail Summariser.")
    parser.add_argument("--json", action="store_true", help="Emit a compact JSON evidence record.")
    args = parser.parse_args(argv)
    try:
        report = run_acceptance(os.environ)
    except (ValueError, RuntimeError, MailServiceError) as exc:
        print(f"Live-account acceptance failed: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    else:
        print("Mail Summariser live-account acceptance: PASSED")
        print(f"IMAP: {report['connection']['imap']} | SMTP: {report['connection']['smtp']}")
        print(f"Mailboxes: {report['mailboxes']['selectable']} selectable; selected {report['mailboxes']['selected']}")
        print(f"Bounded read-only search: {report['search']['fetched']} message(s), limit {report['search']['limit']}")
        print("Credentials were not persisted and message content/identity were not printed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
