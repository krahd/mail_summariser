"""Process-locked synthetic onboarding. No mail/model transport is available here.

This is deliberately a local, single-process demo, not an authentication layer for
hosting the live application. All imports into the existing services are lazy.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import wraps
import hashlib
import json
from pathlib import Path
import re
from threading import RLock
from time import monotonic
from uuid import uuid4

from fastapi import HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, StrictBool

from backend.config import DEMO_MODE

_lock = RLock()
_previews: dict[str, tuple[float, str]] = {}
PREVIEW_TTL = 300


def serial_demo(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if DEMO_MODE:
            with _lock:
                return fn(*args, **kwargs)
        return fn(*args, **kwargs)
    return wrapped


def _fingerprint(plan: dict) -> str:
    return hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()


def issue_preview(plan: dict) -> str:
    now = monotonic()
    for token, (expiry, _) in list(_previews.items()):
        if expiry <= now:
            _previews.pop(token, None)
    while len(_previews) >= 128:
        _previews.pop(next(iter(_previews)))
    token = str(uuid4())
    _previews[token] = (now + PREVIEW_TTL, _fingerprint(plan))
    return token


def consume_preview(plan: dict, token: object) -> None:
    preview = _previews.pop(str(token), None)
    if preview is None or preview[0] <= monotonic() or preview[1] != _fingerprint(plan):
        raise HTTPException(409, 'Preview missing, expired, used, or changed. Preview this action again.')


def sample_messages() -> list[dict]:
    now = datetime.now(timezone.utc)
    rows = [
        ('Project decision', 'alex@example.com', 'Could you confirm the launch checklist by Friday? The draft still needs the accessibility review.', True, True, False, ['work'], 0),
        ('Invoice line items', 'finance@example.com', 'Please confirm the invoice line items. The draft includes travel costs that need your review before approval.', True, False, False, ['finance'], 1),
        ('Design review notes', 'sam@example.com', 'The revised layouts are ready. Let me know which version you prefer and whether you need another review.', True, False, False, ['work'], 2),
        ('Newsletter: workshop notes', 'newsletter@example.com', 'This month: practical workshop notes and recordings. No response is requested.', True, False, False, ['newsletter'], 3),
        ('Old unanswered question', 'lee@example.com', 'Could you review the installation plan? Waiting for a decision before scheduling the next stage.', True, False, False, ['work'], 21),
        ('Booking confirmed', 'bookings@example.com', 'Your fictional demo appointment is confirmed. This is a sample receipt; no payment was taken.', False, False, True, ['receipt'], 1),
        ('Build complete', 'updates@example.com', 'The synthetic build finished. All fixture checks completed successfully.', True, False, False, ['updates'], 0),
        ('Archived reference', 'archive@example.com', 'Reference notes retained in the sample archive for testing folder scopes and undo.', False, False, True, ['work'], 8),
    ]
    return [dict(id=f'demo-{i:03}', subject=subject, sender=sender, recipient='you@example.com',
                 date=(now-timedelta(days=days)).isoformat(timespec='seconds'), body=body,
                 unread=unread, flagged=flagged, replied=replied, keywords=keywords,
                 mailbox='Archive' if i == 8 else 'INBOX',
                 listId='demo-news.example.com' if i == 4 else '')
            for i, (subject, sender, body, unread, flagged, replied, keywords, days) in enumerate(rows, 1)]


@serial_demo
def sync_demo_index() -> dict:
    if not DEMO_MODE:
        raise HTTPException(404, 'Isolated demo is not running.')
    from backend import db
    from backend.mail_index_service import sync_mailbox
    # This database belongs solely to this ephemeral demo process. Preserve the
    # last complete index if a sample sync fails; explicit retry rebuilds it.
    previous = db.list_all_index_messages()
    try:
        for message in previous:
            db.delete_index_message(message['id'])
        count = 0
        for mailbox in ('INBOX', 'Archive'):
            result = sync_mailbox({'id': 'sample', 'dummyMode': True}, mailbox)
            count += result['indexed']
    except Exception as exc:
        for message in db.list_all_index_messages():
            db.delete_index_message(message['id'])
        for message in previous:
            db.upsert_index_message(message)
        raise HTTPException(503, 'Sample index refresh failed. The previous index was retained. Inspect Log for completed actions; retry Sync or Undo.') from exc
    return {'accountId': 'sample', 'mailbox': 'INBOX', 'scanned': count, 'indexed': count, 'errors': 0}


@serial_demo
def reset_demo() -> dict:
    if not DEMO_MODE:
        raise HTTPException(404, 'Isolated demo is not running.')
    from backend.mail_service import reset_dummy_mailbox
    from backend.router_context import get_app_module
    from backend.db import set_setting
    _previews.clear()
    reset_dummy_mailbox()
    get_app_module().dummy_state.reset_dummy_session_store()
    set_setting('safeMode', True)
    return sync_demo_index()


class DemoSafety(BaseModel):
    safeMode: StrictBool


# Default-deny every route not needed by the existing review/triage browser.
_READ_ROUTES = re.compile(r'(?:/|/index\.html|/(?:app|api)\.js|/styles\.css|/health|/settings(?:/system-message-defaults)?|/logs|/mail/scopes|/mail/triage/dashboard|/mail/index/messages(?:/[^/]+)?|/jobs/[^/]+/messages/[^/]+)')
_WRITE_ROUTES = re.compile(r'(?:/summaries|/mail/triage/buckets/[^/]+/summary|/mail/index/sync|/actions/jobs/[^/]+/(?:preview|apply)|/actions/undo(?:/logs/[^/]+)?|/demo/(?:reset|safe-mode))')


def install_demo(app) -> None:
    @app.middleware('http')
    async def demo_boundary(request, call_next):
        host = request.url.hostname
        origin = request.headers.get('origin')
        if host not in ('127.0.0.1', 'localhost', 'testserver') or (origin and origin != str(request.base_url).rstrip('/')):
            return JSONResponse({'detail': 'Demo accepts same-origin loopback requests only.'}, status_code=403)
        path = request.url.path
        allowed = (request.method == 'GET' and _READ_ROUTES.fullmatch(path)) or (request.method == 'POST' and _WRITE_ROUTES.fullmatch(path))
        if not allowed:
            return JSONResponse({'detail': 'Unavailable in isolated demo. No live accounts, email sending, model providers, runtime controls or settings changes.'}, status_code=403)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    @app.post('/demo/safe-mode')
    @serial_demo
    def demo_safe_mode(payload: DemoSafety):
        from backend.db import set_setting
        _previews.clear()
        set_setting('safeMode', payload.safeMode)
        return {'safeMode': payload.safeMode}

    @app.post('/demo/reset')
    def demo_reset():
        return reset_demo()

    web_root = Path(__file__).resolve().parents[1] / 'webapp'

    @app.get('/', response_class=HTMLResponse)
    @app.get('/index.html', response_class=HTMLResponse)
    def demo_index():
        return (web_root / 'index.html').read_text().replace('<body>', '<body data-isolated-demo="true">')

    app.mount('/', StaticFiles(directory=web_root), name='demo-web')
