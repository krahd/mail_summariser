from __future__ import annotations

from typing import Any
from unittest import mock

from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings, strategies as st

from backend import app as backend_app
from backend import routers_summaries


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
        st.lists(children, max_size=6),
        st.dictionaries(st.text(min_size=1, max_size=24), children, max_size=8),
    ),
    max_leaves=24,
)

criteria_key = st.sampled_from(
    [
        "keyword",
        "rawSearch",
        "sender",
        "recipient",
        "tag",
        "unreadOnly",
        "readOnly",
        "replied",
        "useAnd",
    ]
)

criteria_shape = st.one_of(
    json_value,
    st.dictionaries(criteria_key, json_value, max_size=9),
)

summary_payload_shape = st.fixed_dictionaries(
    {
        "criteria": criteria_shape,
        "summaryLength": json_value,
    },
    optional={
        "unknown": json_value,
    },
)


@st.composite
def random_payload(draw: Any) -> dict[str, Any]:
    payload = draw(st.dictionaries(st.text(min_size=1, max_size=24), json_value, max_size=8))
    if draw(st.booleans()):
        payload["criteria"] = draw(criteria_shape)
    if draw(st.booleans()):
        payload["summaryLength"] = draw(json_value)
    return payload


def _status_is_handled(response_status: int) -> bool:
    return response_status in {200, 400, 422}


@given(payload=summary_payload_shape)
@settings(
    max_examples=120,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_summary_endpoint_fuzzes_criteria_shape_without_server_crash(payload: dict[str, Any]) -> None:
    backend_app._reset_dummy_sandbox()

    with (
        TestClient(backend_app.app) as client,
        mock.patch.object(routers_summaries, "search_messages", return_value=[]),
        mock.patch.object(
            routers_summaries,
            "summarize_messages",
            return_value=(
                "Fuzz summary",
                {"status": "ok", "provider": "fuzz", "model": "fuzz-model"},
            ),
        ),
    ):
        response = client.post("/summaries", json=payload)

    assert _status_is_handled(response.status_code)

    if response.status_code == 200:
        body = response.json()
        assert isinstance(body.get("jobId"), str)
        assert isinstance(body.get("summary"), str)
        assert isinstance(body.get("messages"), list)


@given(payload=random_payload())
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_summary_endpoint_fuzzes_random_payload_shapes_without_server_crash(payload: dict[str, Any]) -> None:
    backend_app._reset_dummy_sandbox()

    with (
        TestClient(backend_app.app) as client,
        mock.patch.object(routers_summaries, "search_messages", return_value=[]),
        mock.patch.object(
            routers_summaries,
            "summarize_messages",
            return_value=(
                "Fuzz summary",
                {"status": "ok", "provider": "fuzz", "model": "fuzz-model"},
            ),
        ),
    ):
        response = client.post("/summaries", json=payload)

    assert _status_is_handled(response.status_code)
