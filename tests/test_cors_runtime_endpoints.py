from __future__ import annotations

from fastapi.testclient import TestClient

from backend import app as backend_app


def test_runtime_status_preflight_allows_localhost_dev_port() -> None:
    with TestClient(backend_app.app) as client:
        response = client.options(
            "/runtime/status",
            headers={
                "Origin": "http://localhost:8000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "X-API-Key",
            },
        )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:8000"


def test_models_catalog_preflight_allows_loopback_dev_port() -> None:
    with TestClient(backend_app.app) as client:
        response = client.options(
            "/models/catalog?query=&limit=80",
            headers={
                "Origin": "http://127.0.0.1:8000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "X-API-Key",
            },
        )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://127.0.0.1:8000"
