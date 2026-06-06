from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from backend.mail_service import MailServiceError, discover_mailboxes_for_account
from backend.router_context import get_app_module
from backend.schemas import MailboxInfo

router = APIRouter()

_SAMPLE_MAILBOXES: list[dict[str, Any]] = [
    {'accountId': 'sample', 'path': 'INBOX', 'delimiter': '/', 'selectable': True, 'flags': [], 'displayName': 'Inbox'},
    {'accountId': 'sample', 'path': 'Lists/Fing', 'delimiter': '/', 'selectable': True, 'flags': [], 'displayName': 'Lists/Fing'},
]


def _resolve_account(account_id: str, settings: dict[str, Any]) -> dict[str, Any] | None:
    accounts = settings.get('mailAccounts') or []
    if isinstance(accounts, list):
        for acc in accounts:
            if isinstance(acc, dict) and str(acc.get('id', '')) == account_id:
                return acc
    return None


@router.get('/mail/accounts/{account_id}/mailboxes', response_model=list[MailboxInfo])
def get_account_mailboxes(account_id: str) -> list[MailboxInfo]:
    app_module = get_app_module()
    settings = app_module._merged_settings()

    if bool(settings.get('dummyMode', True)):
        return [MailboxInfo(**m) for m in _SAMPLE_MAILBOXES]

    account = _resolve_account(account_id, settings)
    if account is None:
        raise HTTPException(status_code=404, detail=f'Account {account_id!r} not found')

    try:
        raw_mailboxes = discover_mailboxes_for_account(account)
    except MailServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return [
        MailboxInfo(
            accountId=account_id,
            path=m['path'],
            delimiter=m.get('delimiter'),
            selectable=m.get('selectable', True),
            flags=m.get('flags', []),
            displayName=m.get('path', ''),
        )
        for m in raw_mailboxes
    ]


@router.get('/mail/mailboxes', response_model=list[MailboxInfo])
def get_all_mailboxes() -> list[MailboxInfo]:
    app_module = get_app_module()
    settings = app_module._merged_settings()

    if bool(settings.get('dummyMode', True)):
        return [MailboxInfo(**m) for m in _SAMPLE_MAILBOXES]

    accounts = settings.get('mailAccounts') or []
    all_mailboxes: list[MailboxInfo] = []
    for account in accounts:
        if not isinstance(account, dict):
            continue
        if not account.get('enabled', True):
            continue
        account_id = str(account.get('id', ''))
        try:
            raw_mailboxes = discover_mailboxes_for_account(account)
            for m in raw_mailboxes:
                all_mailboxes.append(MailboxInfo(
                    accountId=account_id,
                    path=m['path'],
                    delimiter=m.get('delimiter'),
                    selectable=m.get('selectable', True),
                    flags=m.get('flags', []),
                    displayName=m.get('path', ''),
                ))
        except MailServiceError:
            all_mailboxes.append(MailboxInfo(
                accountId=account_id,
                path='',
                selectable=False,
                flags=['\\Error'],
                displayName=f'Error loading mailboxes for {account_id}',
            ))

    return all_mailboxes
