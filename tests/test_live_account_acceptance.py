from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_live_account.py"
spec = importlib.util.spec_from_file_location("validate_live_account", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def base_env() -> dict[str, str]:
    return {
        module.OPT_IN: "1",
        "MAIL_SUMMARISER_IMAP_HOST": "imap.example.test",
        "MAIL_SUMMARISER_IMAP_USERNAME": "person@example.test",
        "MAIL_SUMMARISER_IMAP_PASSWORD": "imap-secret",
        "MAIL_SUMMARISER_SMTP_HOST": "smtp.example.test",
        "MAIL_SUMMARISER_SMTP_PASSWORD": "smtp-secret",
    }


def test_refuses_live_run_without_explicit_opt_in():
    env = base_env()
    env.pop(module.OPT_IN)
    with pytest.raises(ValueError, match=module.OPT_IN):
        module.run_acceptance(env)


def test_build_settings_caps_limit_and_keeps_safe_mode():
    env = base_env() | {"MAIL_SUMMARISER_LIVE_LIMIT": "999"}
    settings, account, mailbox, limit = module.build_transient_settings(env)
    assert limit == module.MAX_LIMIT
    assert settings["safeMode"] is True
    assert settings["dummyMode"] is False
    assert account["id"] == "live-acceptance"
    assert mailbox == "INBOX"


def test_live_acceptance_report_excludes_secrets_and_message_content(monkeypatch):
    env = base_env()
    monkeypatch.setattr(module, "test_mail_connection", lambda settings: {
        "status": "ok", "imap": {"status": "ok"}, "smtp": {"status": "ok"}
    })
    monkeypatch.setattr(module, "discover_mailboxes_for_account", lambda account: [
        {"path": "INBOX", "selectable": True},
        {"path": "Archive", "selectable": True},
    ])
    seen = {}
    def fake_search(criteria, settings):
        seen["criteria"] = criteria
        seen["settings"] = settings
        return [{"subject": "top secret", "body": "do not print", "sender": "secret@example.test"}]
    monkeypatch.setattr(module, "search_messages", fake_search)

    report = module.run_acceptance(env)
    rendered = str(report)
    assert report["status"] == "passed"
    assert report["search"]["fetched"] == 1
    assert seen["criteria"].limit == module.DEFAULT_LIMIT
    assert seen["criteria"].mailboxes == ["INBOX"]
    for secret in ("imap-secret", "smtp-secret", "person@example.test", "top secret", "do not print", "secret@example.test"):
        assert secret not in rendered
    assert report["privacy"] == {
        "credentialsPersisted": False,
        "messageContentReported": False,
        "identityReported": False,
    }


def test_connection_failure_stops_before_mailbox_or_search(monkeypatch):
    env = base_env()
    monkeypatch.setattr(module, "test_mail_connection", lambda settings: {
        "status": "warning", "imap": {"status": "ok"}, "smtp": {"status": "error"}
    })
    monkeypatch.setattr(module, "discover_mailboxes_for_account", lambda account: pytest.fail("mailbox discovery should not run"))
    monkeypatch.setattr(module, "search_messages", lambda criteria, settings: pytest.fail("search should not run"))
    with pytest.raises(RuntimeError, match="both IMAP and SMTP"):
        module.run_acceptance(env)
