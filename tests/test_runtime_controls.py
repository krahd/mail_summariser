
from __future__ import annotations
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from typing import Any

import importlib
import importlib.util

# Prefer dynamic import to avoid static analyzers flagging missing third-party
# modules in editor environments that don't have test dependencies installed.
if importlib.util.find_spec("fastapi.testclient") is not None:
    _mod = importlib.import_module("fastapi.testclient")
    TestClient = getattr(_mod, "TestClient")
else:  # pragma: no cover - editor/dev-env fallback
    class _StubResponse:
        status_code: int = 200

        def json(self) -> Any:
            return {}

    class TestClient:  # type: ignore[misc]
        """Lightweight fallback TestClient for editor diagnostics.

        The real `fastapi.testclient.TestClient` is required to run tests; this
        fallback only exists so editors (Pylance) won't report missing imports
        or unbound-variable/attribute diagnostics when the FastAPI package is
        not installed in the environment used by the editor.
        """

        def __init__(self, _app: object) -> None:
            del _app

        def __enter__(self) -> "TestClient":
            return self

        def __exit__(self, _exc_type, _exc, _tb) -> bool:  # type: ignore[override]
            return False

        def get(self, _path: str, **_kwargs) -> _StubResponse:
            return _StubResponse()

        def post(self, _path: str, json=None, **_kwargs) -> _StubResponse:
            return _StubResponse()


# Module-level placeholders for dynamically-imported backend modules
model_provider_service: Any = None
db: Any = None
backend_app: Any = None


# backend modules are imported dynamically in setUp after sys.path is configured

class _FakeProcess:
    def __init__(self, pid: int = 43210) -> None:
        self.pid = pid
        self._terminated = False

    def poll(self) -> int | None:
        return 0 if self._terminated else None

    def send_signal(self, _sig) -> None:
        self._terminated = True


class RuntimeControlTests(unittest.TestCase):
    def setUp(self) -> None:
        # ensure backend path is on sys.path then import backend modules
        REPO_ROOT = Path(__file__).resolve().parents[1]
        BACKEND_DIR = REPO_ROOT / "backend"
        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))

        # import backend modules dynamically after sys.path has been configured
        globals()["model_provider_service"] = importlib.import_module("model_provider_service")
        globals()["db"] = importlib.import_module("db")
        globals()["backend_app"] = importlib.import_module("app")

        self.temp_dir = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.temp_dir.name) / "mail_summariser.sqlite3"
        self.original_defaults = backend_app.DEFAULT_SETTINGS.copy()
        self.original_dev_tools_enabled = backend_app.ENABLE_DEV_TOOLS
        backend_app.DEFAULT_SETTINGS["ollamaAutoStart"] = False
        backend_app.DEFAULT_SETTINGS["ollamaStartOnStartup"] = False
        backend_app.DEFAULT_SETTINGS["ollamaStopOnExit"] = False
        backend_app.ENABLE_DEV_TOOLS = False
        backend_app._backend_shutdown_requested = False
        backend_app._shutdown_callback = None
        backend_app._fake_mail_manager.shutdown()
        backend_app._reset_dummy_sandbox()
        model_provider_service._clear_managed_process()
        model_provider_service._runtime_state.last_message = "Ollama status not checked yet"
        model_provider_service._runtime_state.last_message_host = ""
        model_provider_service._runtime_state.last_message_model = ""
        model_provider_service._runtime_state.last_message_warning = False

    def tearDown(self) -> None:
        backend_app.DEFAULT_SETTINGS.clear()
        backend_app.DEFAULT_SETTINGS.update(self.original_defaults)
        backend_app.ENABLE_DEV_TOOLS = self.original_dev_tools_enabled
        backend_app._backend_shutdown_requested = False
        backend_app._shutdown_callback = None
        backend_app._fake_mail_manager.shutdown()
        backend_app._reset_dummy_sandbox()
        model_provider_service._clear_managed_process()
        self.temp_dir.cleanup()

    def _client(self) -> TestClient:
        return TestClient(backend_app.app)

    def test_runtime_status_reports_install_action_when_ollama_missing(self) -> None:
        with mock.patch.object(model_provider_service, "is_ollama_installed", return_value=False):
            with self._client() as client:
                response = client.get("/runtime/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["ollama"]["startupAction"], "install")
        self.assertFalse(payload["ollama"]["installed"])
        self.assertIn("Install Ollama", payload["ollama"]["message"])

    def test_runtime_status_reports_start_action_when_ollama_is_stopped(self) -> None:
        with (
            mock.patch.object(model_provider_service, "is_ollama_installed", return_value=True),
            mock.patch.object(model_provider_service, "is_ollama_running", return_value=False),
        ):
            with self._client() as client:
                response = client.get("/runtime/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["ollama"]["startupAction"], "start")
        self.assertFalse(payload["ollama"]["running"])
        self.assertEqual(payload["ollama"]["modelName"], backend_app.DEFAULT_SETTINGS["modelName"])

    def test_startup_auto_start_warms_model_and_tracks_owned_process(self) -> None:
        backend_app.DEFAULT_SETTINGS["ollamaStartOnStartup"] = True
        state = {"running": False}

        def fake_is_running(_host: str) -> bool:
            return state["running"]

        def fake_start(**_kwargs):
            state["running"] = True
            return (True, "started")

        with (
            mock.patch.object(model_provider_service, "is_ollama_installed", return_value=True),
            mock.patch.object(model_provider_service, "is_ollama_running",
                              side_effect=fake_is_running),
            mock.patch.object(model_provider_service, "ensure_ollama_running_verbose",
                              side_effect=fake_start),
            mock.patch.object(model_provider_service, "list_ollama_models",
                              return_value=[backend_app.DEFAULT_SETTINGS["modelName"]]),
            mock.patch.object(model_provider_service, "ensure_model_ready", return_value=True),
        ):
            with self._client() as client:
                payload = client.get("/runtime/status").json()

        self.assertTrue(payload["ollama"]["running"])
        self.assertTrue(payload["ollama"]["startedByApp"])
        self.assertEqual(payload["ollama"]["startupAction"], "none")
        self.assertIn("ready with model", payload["ollama"]["message"].lower())

    def test_runtime_start_endpoint_returns_warning_when_model_is_missing(self) -> None:
        state = {"running": False}

        def fake_is_running(_host: str) -> bool:
            return state["running"]

        def fake_start(**_kwargs):
            state["running"] = True
            return (True, "started")

        with (
            mock.patch.object(model_provider_service, "is_ollama_installed", return_value=True),
            mock.patch.object(model_provider_service, "is_ollama_running",
                              side_effect=fake_is_running),
            mock.patch.object(model_provider_service, "ensure_ollama_running_verbose",
                              side_effect=fake_start),
            mock.patch.object(model_provider_service, "list_ollama_models", return_value=[]),
        ):
            with self._client() as client:
                response = client.post("/runtime/ollama/start", json={})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "warning")
        self.assertTrue(payload["runtime"]["ollama"]["running"])
        self.assertIn("not installed", payload["message"])

    def test_runtime_shutdown_endpoint_schedules_shutdown(self) -> None:
        scheduled: list[bool] = []

        def fake_schedule(delay_seconds: float = 0.2) -> None:
            del delay_seconds
            backend_app._backend_shutdown_requested = True
            scheduled.append(True)

        with mock.patch.object(backend_app, "_schedule_backend_shutdown", side_effect=fake_schedule):
            with self._client() as client:
                response = client.post("/runtime/shutdown", json={})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertTrue(scheduled)

    def test_stop_managed_ollama_only_targets_owned_processes(self) -> None:
        stopped, message = model_provider_service.stop_managed_ollama(True)
        self.assertFalse(stopped)
        self.assertIn("No Ollama process started by mail_summariser", message)

        fake_process = _FakeProcess()
        model_provider_service._mark_managed_process(fake_process, "http://127.0.0.1:11434")
        stopped, message = model_provider_service.stop_managed_ollama(True)
        self.assertTrue(stopped)
        self.assertTrue(fake_process._terminated)
        self.assertIn("Stopped app-managed Ollama", message)

    def test_fake_mail_status_reports_disabled_when_dev_tools_are_off(self) -> None:
        with self._client() as client:
            response = client.get("/dev/fake-mail/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["enabled"])
        self.assertFalse(payload["running"])

    def test_fake_mail_start_and_stop_are_idempotent_when_enabled(self) -> None:
        backend_app.ENABLE_DEV_TOOLS = True
        with self._client() as client:
            first_start = client.post("/dev/fake-mail/start", json={})
            second_start = client.post("/dev/fake-mail/start", json={})
            first_stop = client.post("/dev/fake-mail/stop", json={})
            second_stop = client.post("/dev/fake-mail/stop", json={})

        self.assertEqual(first_start.status_code, 200)
        self.assertEqual(second_start.status_code, 200)
        self.assertTrue(first_start.json()["running"])
        self.assertTrue(second_start.json()["running"])
        self.assertEqual(first_start.json()["imapPort"], second_start.json()["imapPort"])
        self.assertEqual(first_stop.status_code, 200)
        self.assertEqual(second_stop.status_code, 200)
        self.assertFalse(first_stop.json()["running"])
        self.assertFalse(second_stop.json()["running"])


if __name__ == "__main__":
    unittest.main()
