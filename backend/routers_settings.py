from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.config import DEFAULT_SETTINGS, DEFAULT_SYSTEM_MESSAGES
from backend.db import reset_database, set_setting, list_settings
from backend.mail_service import test_mail_connection, reset_dummy_mailbox
from backend.router_context import get_app_module
from backend.schemas import (
    AppSettings,
    DatabaseResetRequest,
    DatabaseResetResponse,
    SystemMessageDefaultsResponse,
)


router = APIRouter()


@router.get('/settings', response_model=AppSettings)
def get_settings() -> AppSettings:
    app_module = get_app_module()

    try:
        current = app_module.list_settings()
    except Exception:  # pylint: disable=broad-except
        current = {}
    app_module.logger.debug(
        "settings_read dummy_default=%s dummy_persisted=%s",
        DEFAULT_SETTINGS.get('dummyMode'),
        current.get('dummyMode'),
    )
    return AppSettings(**app_module._masked_settings_payload())


@router.get('/settings/system-message-defaults', response_model=SystemMessageDefaultsResponse)
def get_system_message_defaults() -> SystemMessageDefaultsResponse:
    return SystemMessageDefaultsResponse(**DEFAULT_SYSTEM_MESSAGES)


@router.post('/settings')
def save_settings(settings: AppSettings) -> dict[str, str]:
    app_module = get_app_module()

    data = settings.model_dump()

    # Handle legacy top-level secret masking
    for key_name in app_module.SECRET_SETTING_KEYS:
        if data.get(key_name) == '__MASKED__':
            data.pop(key_name)

    # Handle account-level secret masking
    if isinstance(data.get('mailAccounts'), list):
        current_settings = list_settings()
        current_accounts = current_settings.get('mailAccounts', [])
        # Build a map of account IDs to current account data for secret preservation
        current_accounts_by_id = {
            acc.get('id'): acc for acc in current_accounts if isinstance(acc, dict)
        }

        sanitized_accounts = []
        for account in data['mailAccounts']:
            if isinstance(account, dict):
                sanitized_account = account.copy()
                account_id = account.get('id', '')
                for secret_key in app_module.ACCOUNT_SECRET_KEYS:
                    if sanitized_account.get(secret_key) == '__MASKED__':
                        # Try to restore the current secret from the database
                        if account_id in current_accounts_by_id:
                            stored_secret = current_accounts_by_id[account_id].get(secret_key, '')
                            if stored_secret:
                                # Restore the stored value
                                sanitized_account[secret_key] = stored_secret
                            else:
                                # No stored secret; remove the masked sentinel so field is empty
                                sanitized_account.pop(secret_key, None)
                        else:
                            # Account is new; remove the masked sentinel
                            sanitized_account.pop(secret_key, None)
                sanitized_accounts.append(sanitized_account)
            else:
                sanitized_accounts.append(account)
        data['mailAccounts'] = sanitized_accounts

    for key, value in data.items():
        set_setting(key, value)
    app_module._record_log('save_settings', 'ok', 'Settings updated',
                           settings=settings.model_dump())
    return {'status': 'ok'}


@router.post('/settings/test-connection')
def test_connection(settings: dict) -> dict:
    try:
        payload = settings if isinstance(settings, dict) else settings.model_dump()
        return test_mail_connection(payload)
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/settings/dummy-mode')
def set_dummy_mode(payload: dict) -> dict:
    app_module = get_app_module()

    try:
        data = payload if isinstance(payload, dict) else payload.model_dump()
        dummy_mode = bool(data.get('dummyMode'))
        set_setting('dummyMode', dummy_mode)
        if not dummy_mode:
            app_module.dummy_state.reset_dummy_session_store()
        return {'dummyMode': dummy_mode}
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/admin/database/reset', response_model=DatabaseResetResponse)
def admin_reset_database(request: DatabaseResetRequest) -> DatabaseResetResponse:
    app_module = get_app_module()

    if request.confirmation != 'RESET DATABASE':
        raise HTTPException(status_code=400, detail='Confirmation text must be RESET DATABASE')
    removed = reset_database(DEFAULT_SETTINGS)
    app_module.dummy_state.reset_dummy_session_store()
    reset_dummy_mailbox()
    return DatabaseResetResponse(
        status='ok',
        message='Local database reset to defaults.',
        removed=removed,
        settings=AppSettings(**app_module._masked_settings_payload()),
    )
