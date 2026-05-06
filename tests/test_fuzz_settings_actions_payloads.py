from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings, strategies as st

from backend import app as backend_app
from backend import routers_actions, routers_settings


json_scalar = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(max_size=120),
)

json_value = st.recursive(
    json_scalar,
    lambda children: st.one_of(
        st.lists(children, max_size=8),
        st.dictionaries(st.text(min_size=1, max_size=24), children, max_size=10),
    ),
    max_leaves=30,
)


def _safe_status(status_code: int) -> bool:
    return status_code in {200, 400, 404, 422}


@given(payload=json_value)
@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_settings_save_payload_fuzz_never_500(payload) -> None:
    with TestClient(backend_app.app) as client:
        response = client.post("/settings", json=payload)

    assert _safe_status(response.status_code)


@given(payload=json_value)
@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_settings_test_connection_payload_fuzz_never_500(payload) -> None:
    with (
        TestClient(backend_app.app) as client,
        mock.patch.object(routers_settings, "test_mail_connection", return_value={"mode": "dummy"}),
    ):
        response = client.post("/settings/test-connection", json=payload)

    assert response.status_code in {200, 422}


@given(payload=json_value)
@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_settings_dummy_mode_payload_fuzz_never_500(payload) -> None:
    with TestClient(backend_app.app) as client:
        response = client.post("/settings/dummy-mode", json=payload)

    assert response.status_code in {200, 422}


@given(payload=json_value)
@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_actions_mark_read_payload_fuzz_never_500(payload) -> None:
    fake_job = {"messages_json": [{"id": "m-1"}, {"id": "m-2"}]}

    with (
        TestClient(backend_app.app) as client,
        mock.patch.object(routers_actions, "is_dummy_mode", return_value=False),
        mock.patch.object(routers_actions, "get_job", return_value=fake_job),
        mock.patch.object(routers_actions, "mark_messages_read", return_value=None),
        mock.patch.object(backend_app, "_merged_settings", return_value={}),
        mock.patch.object(backend_app, "_record_log", return_value="log-1"),
        mock.patch.object(backend_app, "_push_undo", return_value=None),
    ):
        response = client.post("/actions/mark-read", json=payload)

    assert response.status_code in {200, 422}


@given(payload=json_value)
@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_actions_tag_payload_fuzz_never_500(payload) -> None:
    fake_job = {"messages_json": [{"id": "m-1"}]}

    with (
        TestClient(backend_app.app) as client,
        mock.patch.object(routers_actions, "is_dummy_mode", return_value=False),
        mock.patch.object(routers_actions, "get_job", return_value=fake_job),
        mock.patch.object(routers_actions, "add_keyword_tag", return_value=None),
        mock.patch.object(backend_app, "_merged_settings", return_value={}),
        mock.patch.object(backend_app, "_record_log", return_value="log-2"),
        mock.patch.object(backend_app, "_push_undo", return_value=None),
    ):
        response = client.post("/actions/tag-summarised", json=payload)

    assert response.status_code in {200, 422}


@given(payload=json_value)
@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_actions_email_payload_fuzz_never_500(payload) -> None:
    fake_job = {"messages_json": [{"id": "m-1"}], "summary_text": "hello"}

    with (
        TestClient(backend_app.app) as client,
        mock.patch.object(routers_actions, "is_dummy_mode", return_value=False),
        mock.patch.object(routers_actions, "get_job", return_value=fake_job),
        mock.patch.object(routers_actions, "send_summary_email", return_value=None),
        mock.patch.object(backend_app, "_merged_settings", return_value={
                          "recipientEmail": "x@example.com"}),
        mock.patch.object(backend_app, "_record_log", return_value="log-3"),
    ):
        response = client.post("/actions/email-summary", json=payload)

    assert response.status_code in {200, 422}


@given(payload=json_value)
@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_actions_undo_payload_fuzz_never_500(payload) -> None:
    fake_app_module = SimpleNamespace(
        _merged_settings=lambda: {"dummyMode": True},
        dummy_state=SimpleNamespace(pop_latest_undo=lambda: None),
    )

    with (
        TestClient(backend_app.app) as client,
        mock.patch.object(routers_actions, "get_app_module", return_value=fake_app_module),
        mock.patch.object(routers_actions, "is_dummy_mode", return_value=True),
    ):
        response = client.post("/actions/undo", json=payload)

    assert response.status_code in {404, 422}


@given(payload=json_value)
@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_actions_undo_log_payload_fuzz_never_500(payload) -> None:
    fake_app_module = SimpleNamespace(
        _merged_settings=lambda: {"dummyMode": True},
        dummy_state=SimpleNamespace(pop_undo_by_log_id=lambda _log_id: None),
    )

    with (
        TestClient(backend_app.app) as client,
        mock.patch.object(routers_actions, "get_app_module", return_value=fake_app_module),
        mock.patch.object(routers_actions, "is_dummy_mode", return_value=True),
    ):
        response = client.post("/actions/undo/logs/fuzz-log-id", json=payload)

    assert response.status_code in {404, 422}


@given(query=st.dictionaries(st.text(min_size=1, max_size=16), st.text(max_size=32), max_size=6))
@settings(max_examples=80, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_logs_endpoint_query_fuzz_never_500(query) -> None:
    fake_app_module = SimpleNamespace(
        _merged_settings=lambda: {"dummyMode": True},
        dummy_state=SimpleNamespace(
            list_logs=lambda: [],
            list_undoable_log_ids=lambda: set(),
        ),
    )

    with (
        TestClient(backend_app.app) as client,
        mock.patch.object(routers_actions, "get_app_module", return_value=fake_app_module),
        mock.patch.object(routers_actions, "is_dummy_mode", return_value=True),
    ):
        response = client.get("/logs", params=query)

    assert response.status_code == 200


@given(
    confirmation=st.text(max_size=120).filter(lambda value: value != "RESET DATABASE"),
)
@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_admin_reset_confirmation_string_edge_cases_rejected(confirmation) -> None:
    with TestClient(backend_app.app) as client:
        response = client.post("/admin/database/reset", json={"confirmation": confirmation})

    assert response.status_code == 400
    assert response.json().get("detail") == "Confirmation text must be RESET DATABASE"


@given(payload=json_value)
@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_admin_reset_malformed_payload_shapes_never_500(payload) -> None:
    if isinstance(payload, dict) and payload.get("confirmation") == "RESET DATABASE":
        return

    with TestClient(backend_app.app) as client:
        response = client.post("/admin/database/reset", json=payload)

    assert response.status_code in {400, 422}
