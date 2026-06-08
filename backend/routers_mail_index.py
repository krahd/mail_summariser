from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend import db
from backend.mail_index_service import MailServiceError, _resolve_account, sync_mailbox
from backend.router_context import get_app_module
from backend.schemas import (
    MailIndexMessageDetail,
    MailIndexMessageSummary,
    MailIndexSyncRequest,
    MailIndexSyncResponse,
)


router = APIRouter(prefix='/mail/index')


@router.post('/sync', response_model=MailIndexSyncResponse)
def sync_mail_index(request: MailIndexSyncRequest) -> MailIndexSyncResponse:
    app_module = get_app_module()
    try:
        settings = app_module._merged_settings()
        account = _resolve_account(settings, request.accountId)
        result = sync_mailbox(account, request.mailbox, request.limit)
        return MailIndexSyncResponse(**result)
    except HTTPException:
        raise
    except MailServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get('/messages', response_model=list[MailIndexMessageSummary])
def list_mail_index_messages(accountId: str | None = None, mailbox: str | None = None,
                             unread: bool | None = None, flagged: bool | None = None,
                             tag: str | None = None, keyword: str | None = None,
                             listId: str | None = None, sender: str | None = None,
                             limit: int = 100) -> list[MailIndexMessageSummary]:
    criteria = {
        'accountId': accountId,
        'mailbox': mailbox,
        'unread': unread,
        'flagged': flagged,
        'tag': tag,
        'keyword': keyword,
        'listId': listId,
        'sender': sender,
        'limit': limit,
    }
    messages = db.list_index_messages(criteria)
    return [MailIndexMessageSummary(**message) for message in messages]


@router.get('/messages/{message_id}', response_model=MailIndexMessageDetail)
def get_mail_index_message(message_id: str) -> MailIndexMessageDetail:
    message = db.get_index_message(message_id)
    if message is None:
        raise HTTPException(status_code=404, detail='Message not found')
    return MailIndexMessageDetail(**message)
