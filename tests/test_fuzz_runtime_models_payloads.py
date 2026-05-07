from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings, strategies as st

from backend import app as backend_app
from backend import routers_runtime_models


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
        st.dictionaries(st.text(min_size=1, max_size=20), children, max_size=10),
    ),
    max_leaves=30,
)

query_dict = st.dictionaries(
    st.text(min_size=1, max_size=16),
    st.text(max_size=40),
    max_size=6,
)


def _fake_provider() -> SimpleNamespace:
    return SimpleNamespace(
        ensure_ollama_running=lambda _host, auto_start=True: (True, "ok"),
        list_ollama_models=lambda _host: ["llama3.2:latest"],
        is_ollama_installed=lambda _host: True,
        is_ollama_running=lambda _host: True,
        _managed_process_host=None,
        _runtime_state=SimpleNamespace(last_message="ok", last_message_host="",),
    )


@given(params=query_dict)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_runtime_status_query_fuzz_never_500(params) -> None:
    with (
        TestClient(backend_app.app) as client,
        mock.patch.object(routers_runtime_models, "_provider_module",
                          return_value=_fake_provider()),
    ):
        response = client.get("/runtime/status", params=params)

    assert response.status_code == 200


@given(payload=json_value)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_runtime_start_payload_fuzz_never_500(payload) -> None:
    with (
        TestClient(backend_app.app) as client,
        mock.patch.object(routers_runtime_models, "_provider_module",
                          return_value=_fake_provider()),
    ):
        response = client.post("/runtime/ollama/start", json=payload)

    assert response.status_code == 200


@given(payload=json_value)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_runtime_shutdown_payload_fuzz_never_500(payload) -> None:
    fake_app_module = SimpleNamespace(_schedule_backend_shutdown=lambda: None)

    with (
        TestClient(backend_app.app) as client,
        mock.patch.object(routers_runtime_models, "get_app_module", return_value=fake_app_module),
    ):
        response = client.post("/runtime/shutdown", json=payload)

    assert response.status_code == 200


@given(params=query_dict)
@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_models_options_query_fuzz_never_500(params) -> None:
    with (
        TestClient(backend_app.app) as client,
        mock.patch.object(routers_runtime_models, "_provider_module",
                          return_value=_fake_provider()),
    ):
        response = client.get("/models/options", params=params)

    assert response.status_code in {200, 422}


@given(params=query_dict)
@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_models_catalog_query_fuzz_never_500(params) -> None:
    with (
        TestClient(backend_app.app) as client,
        mock.patch.object(routers_runtime_models, "_provider_module",
                          return_value=_fake_provider()),
    ):
        response = client.get("/models/catalog", params=params)

    assert response.status_code in {200, 422}
