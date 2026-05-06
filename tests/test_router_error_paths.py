from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from fastapi.testclient import TestClient

from backend import app as backend_app
from backend.mail_service import MailServiceError
from backend import routers_actions, routers_devtools, routers_settings, routers_summaries


SUMMARY_PAYLOAD = {
    "criteria": {
        "keyword": "",
        "rawSearch": "",
        "sender": "",
        "recipient": "",
        "unreadOnly": True,
        "readOnly": False,
        "replied": None,
        "tag": "",
        "useAnd": True,
    },
    "summaryLength": 5,
}


def test_settings_test_connection_returns_400_on_mail_probe_error() -> None:
    with TestClient(backend_app.app) as client, mock.patch.object(
        routers_settings,
        "test_mail_connection",
        side_effect=RuntimeError("probe failed"),
    ):
        response = client.post("/settings/test-connection", json={"dummyMode": True})

    assert response.status_code == 400
    assert response.json()["detail"] == "probe failed"


def test_settings_dummy_mode_returns_400_when_write_fails() -> None:
    with TestClient(backend_app.app) as client, mock.patch.object(
        routers_settings,
        "set_setting",
        side_effect=RuntimeError("write failed"),
    ):
        response = client.post("/settings/dummy-mode", json={"dummyMode": False})

    assert response.status_code == 400
    assert response.json()["detail"] == "write failed"


def test_summaries_returns_400_when_search_layer_raises() -> None:
    with TestClient(backend_app.app) as client, mock.patch.object(
        routers_summaries,
        "search_messages",
        side_effect=MailServiceError("invalid search criteria"),
    ):
        response = client.post("/summaries", json=SUMMARY_PAYLOAD)

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid search criteria"


def test_actions_mark_read_returns_400_when_mail_operation_fails() -> None:
    fake_job = {"messages_json": [{"id": "mid-1"}]}

    with (
        TestClient(backend_app.app) as client,
        mock.patch.object(routers_actions, "is_dummy_mode", return_value=False),
        mock.patch.object(routers_actions, "get_job", return_value=fake_job),
        mock.patch.object(
            routers_actions,
            "mark_messages_read",
            side_effect=RuntimeError("mark failed"),
        ),
    ):
        response = client.post("/actions/mark-read", json={"jobId": "job-123"})

    assert response.status_code == 400
    assert response.json()["detail"] == "mark failed"


def test_actions_undo_log_returns_404_when_log_payload_missing() -> None:
    fake_app_module = SimpleNamespace(
        _merged_settings=lambda: {"dummyMode": True},
        dummy_state=SimpleNamespace(pop_undo_by_log_id=lambda _log_id: None),
    )

    with (
        TestClient(backend_app.app) as client,
        mock.patch.object(routers_actions, "get_app_module", return_value=fake_app_module),
        mock.patch.object(routers_actions, "is_dummy_mode", return_value=True),
    ):
        response = client.post("/actions/undo/logs/missing-log-id", json={})

    assert response.status_code == 404
    assert response.json()["detail"] == "No undo found for log"


def test_actions_undo_returns_404_when_stack_is_empty() -> None:
    fake_app_module = SimpleNamespace(
        _merged_settings=lambda: {"dummyMode": True},
        dummy_state=SimpleNamespace(pop_latest_undo=lambda: None),
    )

    with (
        TestClient(backend_app.app) as client,
        mock.patch.object(routers_actions, "get_app_module", return_value=fake_app_module),
        mock.patch.object(routers_actions, "is_dummy_mode", return_value=True),
    ):
        response = client.post("/actions/undo", json={})

    assert response.status_code == 404
    assert response.json()["detail"] == "No undo found"


def test_devtools_start_returns_disabled_payload_when_flag_off() -> None:
    original = backend_app.ENABLE_DEV_TOOLS
    backend_app.ENABLE_DEV_TOOLS = False

    try:
        with TestClient(backend_app.app) as client:
            response = client.post("/dev/fake-mail/start", json={})
    finally:
        backend_app.ENABLE_DEV_TOOLS = original

    assert response.status_code == 200
    payload = response.json()
    assert payload["enabled"] is False
    assert payload["running"] is False


def test_devtools_stop_returns_disabled_payload_when_flag_off() -> None:
    original = backend_app.ENABLE_DEV_TOOLS
    backend_app.ENABLE_DEV_TOOLS = False

    try:
        with TestClient(backend_app.app) as client:
            response = client.post("/dev/fake-mail/stop", json={})
    finally:
        backend_app.ENABLE_DEV_TOOLS = original

    assert response.status_code == 200
    payload = response.json()
    assert payload["enabled"] is False
    assert payload["running"] is False
