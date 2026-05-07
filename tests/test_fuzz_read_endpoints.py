from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings, strategies as st

from backend import app as backend_app
from backend import routers_summaries


query_dict = st.dictionaries(
    st.text(min_size=1, max_size=16),
    st.text(max_size=40),
    max_size=8,
)

path_text = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="-_"),
    min_size=1,
    max_size=24,
)

job_id_strategy = st.one_of(st.just("job-1"), path_text)
message_id_strategy = st.one_of(st.just("m-1"), path_text)


def _dummy_app_module_for_job_lookup() -> SimpleNamespace:
    def _get_job(job_id: str) -> dict | None:
        if job_id != "job-1":
            return None
        return {
            "messages_json": [
                {
                    "id": "m-1",
                    "subject": "Subject",
                    "sender": "sender@example.com",
                    "recipient": "recipient@example.com",
                    "date": "2026-01-01",
                    "body": "Body",
                }
            ]
        }

    return SimpleNamespace(
        _merged_settings=lambda: {"dummyMode": True},
        dummy_state=SimpleNamespace(get_job=_get_job),
    )


@given(params=query_dict)
@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_settings_read_query_fuzz_never_500(params) -> None:
    with TestClient(backend_app.app) as client:
        response = client.get("/settings", params=params)

    assert response.status_code == 200


@given(params=query_dict)
@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_settings_system_defaults_query_fuzz_never_500(params) -> None:
    with TestClient(backend_app.app) as client:
        response = client.get("/settings/system-message-defaults", params=params)

    assert response.status_code == 200


@given(params=query_dict)
@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_health_query_fuzz_never_500(params) -> None:
    with TestClient(backend_app.app) as client:
        response = client.get("/health", params=params)

    assert response.status_code == 200


@given(job_id=job_id_strategy, message_id=message_id_strategy)
@settings(max_examples=140, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_job_message_path_fuzz_never_500(job_id: str, message_id: str) -> None:
    fake_app_module = _dummy_app_module_for_job_lookup()

    with (
        TestClient(backend_app.app) as client,
        mock.patch.object(routers_summaries, "get_app_module", return_value=fake_app_module),
        mock.patch.object(routers_summaries, "is_dummy_mode", return_value=True),
    ):
        response = client.get(f"/jobs/{job_id}/messages/{message_id}")

    assert response.status_code in {200, 404}
