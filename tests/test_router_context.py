from __future__ import annotations

import sys
from types import ModuleType

from backend.router_context import get_app_module


def test_get_app_module_prefers_top_level_app_module(monkeypatch) -> None:
    fake_top_level_app = ModuleType("app")
    monkeypatch.setitem(sys.modules, "app", fake_top_level_app)

    resolved = get_app_module()

    assert resolved is fake_top_level_app


def test_get_app_module_falls_back_to_backend_app(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "app", raising=False)

    resolved = get_app_module()

    assert getattr(resolved, "__name__", "") == "backend.app"
