from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings, strategies as st

from backend import app as backend_app
from backend import routers_devtools


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

query_dict = st.dictionaries(
    st.text(min_size=1, max_size=16),
    st.text(max_size=40),
    max_size=6,
)


def _devtools_disabled_app_module() -> SimpleNamespace:
    return SimpleNamespace(ENABLE_DEV_TOOLS=False)


@given(params=query_dict)
@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_devtools_status_query_fuzz_never_500_when_disabled(params) -> None:
    with (
        TestClient(backend_app.app) as client,
        mock.patch.object(
            routers_devtools,
            "get_app_module",
            return_value=_devtools_disabled_app_module(),
        ),
    ):
        response = client.get("/dev/fake-mail/status", params=params)

    assert response.status_code == 200
    payload = response.json()
    assert payload["enabled"] is False
    assert payload["running"] is False


@given(payload=json_value)
@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_devtools_start_payload_fuzz_never_500_when_disabled(payload) -> None:
    with (
        TestClient(backend_app.app) as client,
        mock.patch.object(
            routers_devtools,
            "get_app_module",
            return_value=_devtools_disabled_app_module(),
        ),
    ):
        response = client.post("/dev/fake-mail/start", json=payload)

    assert response.status_code == 200
    payload_body = response.json()
    assert payload_body["enabled"] is False
    assert payload_body["running"] is False


@given(payload=json_value)
@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_devtools_stop_payload_fuzz_never_500_when_disabled(payload) -> None:
    with (
        TestClient(backend_app.app) as client,
        mock.patch.object(
            routers_devtools,
            "get_app_module",
            return_value=_devtools_disabled_app_module(),
        ),
    ):
        response = client.post("/dev/fake-mail/stop", json=payload)

    assert response.status_code == 200
    payload_body = response.json()
    assert payload_body["enabled"] is False
    assert payload_body["running"] is False
