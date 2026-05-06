from __future__ import annotations

from backend import app as backend_app


def test_decomposed_router_endpoints_are_registered() -> None:
    route_map: set[tuple[str, str]] = set()

    for route in backend_app.app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods:
            continue
        for method in methods:
            route_map.add((method.upper(), path))

    expected_routes = {
        ("GET", "/settings"),
        ("POST", "/settings"),
        ("POST", "/settings/test-connection"),
        ("POST", "/settings/dummy-mode"),
        ("GET", "/settings/system-message-defaults"),
        ("POST", "/summaries"),
        ("GET", "/jobs/{job_id}/messages/{message_id}"),
        ("POST", "/actions/mark-read"),
        ("POST", "/actions/tag-summarised"),
        ("POST", "/actions/email-summary"),
        ("POST", "/actions/undo"),
        ("POST", "/actions/undo/logs/{log_id}"),
        ("GET", "/logs"),
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
