from __future__ import annotations

from fastapi import APIRouter
from backend.router_context import get_app_module


router = APIRouter()


@router.get('/dev/fake-mail/status')
def dev_fake_mail_status() -> dict:
    app_module = get_app_module()

    if not app_module.ENABLE_DEV_TOOLS:
        return {
            'enabled': False,
            'running': False,
            'message': 'dev tools disabled',
            'suggestedSettings': None,
        }
    env = app_module._fake_mail_manager._environment
    if env is None:
        return {'enabled': True, 'running': False, 'message': 'stopped', 'suggestedSettings': None}
    return {
        'enabled': True,
        'running': True,
        'imapHost': '127.0.0.1',
        'imapPort': env.imap_server.server_address[1],
        'smtpHost': '127.0.0.1',
        'smtpPort': env.smtp_server.server_address[1],
        'username': getattr(env, 'username', ''),
        'password': getattr(env, 'password', ''),
        'recipientEmail': getattr(env, 'recipient_email', ''),
        'suggestedSettings': getattr(env, 'settings_payload', None) or (env.settings_payload if hasattr(env, 'settings_payload') else None),
    }


@router.post('/dev/fake-mail/start')
def dev_fake_mail_start() -> dict:
    app_module = get_app_module()

    if not app_module.ENABLE_DEV_TOOLS:
        return dev_fake_mail_status()
    env = app_module._fake_mail_manager.start()
    return {
        'enabled': True,
        'running': True,
        'imapHost': '127.0.0.1',
        'imapPort': env.imap_server.server_address[1],
        'smtpHost': '127.0.0.1',
        'smtpPort': env.smtp_server.server_address[1],
        'username': getattr(env, 'username', ''),
        'password': getattr(env, 'password', ''),
        'recipientEmail': getattr(env, 'recipient_email', ''),
        'suggestedSettings': env.settings_payload,
    }


@router.post('/dev/fake-mail/stop')
def dev_fake_mail_stop() -> dict:
    app_module = get_app_module()

    if not app_module.ENABLE_DEV_TOOLS:
        return dev_fake_mail_status()
    app_module._fake_mail_manager.shutdown()
    return {'enabled': True, 'running': False, 'message': 'stopped', 'suggestedSettings': None}
