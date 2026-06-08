from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from backend.mail_service import MailServiceError, discover_mailboxes_for_account
from backend.router_context import get_app_module
from backend.schemas import MailboxInfo

router = APIRouter()

_SAMPLE_MAILBOXES: list[dict[str, Any]] = [
    {'accountId': 'sample', 'path': 'INBOX', 'delimiter': '/', 'selectable': True, 'flags': []},
    {'accountId': 'sample', 'path': 'Lists/Fing', 'delimiter': '/', 'selectable': True, 'flags': []},
]


def _explicit_accounts(settings: dict[str, Any]) -> list[dict[str, Any]]:
    accounts = settings.get('mailAccounts') or []
    if isinstance(accounts, list):
        return [acc for acc in accounts if isinstance(acc, dict)]
    return []


def _legacy_account(settings: dict[str, Any], app_module) -> dict[str, Any] | None:
    legacy_factory = getattr(app_module, '_legacy_mail_account_payload', None)
    if not callable(legacy_factory):
        return None
    account = legacy_factory(settings)
    if isinstance(account, dict) and bool(account.get('enabled', True)):
        return account
    return None


def _resolve_account(account_id: str, settings: dict[str, Any], app_module) -> dict[str, Any] | None:
    accounts = _explicit_accounts(settings)
    if accounts:
        for acc in accounts:
            if str(acc.get('id', '')) == account_id:
                return acc
        return None

    legacy_account = _legacy_account(settings, app_module)
    if legacy_account is not None and str(legacy_account.get('id', '')) == account_id:
        return legacy_account
    return None


def _mailbox_info(account_id: str, mailbox: dict[str, Any]) -> MailboxInfo:
    raw_flags = mailbox.get('flags', []) or []
    return MailboxInfo(
        accountId=account_id,
        path=str(mailbox.get('path', '')),
        delimiter=mailbox.get('delimiter'),
        selectable=bool(mailbox.get('selectable', True)),
        flags=[str(flag) for flag in raw_flags if str(flag).strip()],
    )


def _configured_accounts(settings: dict[str, Any], app_module) -> list[dict[str, Any]]:
    accounts = _explicit_accounts(settings)
    if accounts:
        return accounts
    legacy_account = _legacy_account(settings, app_module)
    return [legacy_account] if legacy_account is not None else []


@router.get('/mail/accounts/{account_id}/mailboxes', response_model=list[MailboxInfo])
def get_account_mailboxes(account_id: str) -> list[MailboxInfo]:
    app_module = get_app_module()
    settings = app_module._merged_settings()

    if bool(settings.get('dummyMode', True)):
        return [MailboxInfo(**m) for m in _SAMPLE_MAILBOXES]

    account = _resolve_account(account_id, settings, app_module)
    if account is None:
        raise HTTPException(status_code=404, detail=f'Account {account_id!r} not found')

    try:
        raw_mailboxes = discover_mailboxes_for_account(account)
    except MailServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return [_mailbox_info(account_id, mailbox) for mailbox in raw_mailboxes]


@router.get('/mail/mailboxes', response_model=list[MailboxInfo])
def get_all_mailboxes() -> list[MailboxInfo]:
    app_module = get_app_module()
    settings = app_module._merged_settings()

    if bool(settings.get('dummyMode', True)):
        return [MailboxInfo(**m) for m in _SAMPLE_MAILBOXES]

    all_mailboxes: list[MailboxInfo] = []
    for account in _configured_accounts(settings, app_module):
        if not isinstance(account, dict):
            continue
        if not account.get('enabled', True):
            continue
        account_id = str(account.get('id', ''))
        try:
            raw_mailboxes = discover_mailboxes_for_account(account)
            for m in raw_mailboxes:
                all_mailboxes.append(_mailbox_info(account_id, m))
        except MailServiceError:
            all_mailboxes.append(MailboxInfo(
                accountId=account_id,
                path='',
                selectable=False,
                flags=['\\Error'],
                displayName=f'Error loading mailboxes for {account_id}',
            ))

    return all_mailboxes
