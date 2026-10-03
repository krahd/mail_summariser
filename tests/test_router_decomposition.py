from __future__ import annotations

from backend import app as backend_app


def test_decomposed_router_endpoints_are_registered() -> None:
    # Assert the public API contract rather than FastAPI/Starlette's private
    # route-container representation. FastAPI 0.142+ keeps included routers as
    # nested _IncludedRouter nodes, while OpenAPI remains the stable contract.
    http_methods = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
    route_map = {
        (method.upper(), path)
        for path, operations in backend_app.app.openapi()["paths"].items()
        for method in operations
        if method.lower() in http_methods
    }

    expected_routes = {
        ("GET", "/settings"),
        ("POST", "/settings"),
        ("POST", "/settings/test-connection"),
        ("POST", "/settings/dummy-mode"),
        ("GET", "/settings/system-message-defaults"),
        ("POST", "/summaries"),
        ("GET", "/jobs/{job_id}/messages/{message_id}"),
        ("POST", "/actions/jobs/{job_id}/preview"),
        ("POST", "/actions/jobs/{job_id}/apply"),
        ("POST", "/actions/email-summary"),
        ("POST", "/actions/undo"),
        ("POST", "/actions/undo/logs/{log_id}"),
        ("GET", "/logs"),
        ("POST", "/mail/index/sync"),
        ("GET", "/mail/index/messages"),
        ("GET", "/mail/index/messages/{message_id}"),
        ("GET", "/mail/scopes"),
        ("POST", "/mail/scopes"),
        ("PUT", "/mail/scopes/{scope_id}"),
        ("DELETE", "/mail/scopes/{scope_id}"),
        ("GET", "/mail/scopes/{scope_id}/messages"),
        ("POST", "/mail/scopes/{scope_id}/summary"),
        ("GET", "/mail/triage/dashboard"),
        ("POST", "/mail/triage/buckets/{bucket_id}/summary"),
        ("GET", "/mail/accounts/{account_id}/mailboxes"),
        ("GET", "/mail/mailboxes"),
        ("GET", "/dev/fake-mail/status"),
        ("POST", "/dev/fake-mail/start"),
        ("POST", "/dev/fake-mail/stop"),
        ("GET", "/runtime/status"),
        ("POST", "/runtime/ollama/start"),
        ("POST", "/runtime/shutdown"),
        ("GET", "/models/options"),
        ("GET", "/models/catalog"),
    }

    missing = expected_routes - route_map
    assert not missing, f"Missing expected routes: {sorted(missing)}"
