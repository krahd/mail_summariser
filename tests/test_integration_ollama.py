import os
import shutil
import socket
import time

from typing import Any
from modelito import ollama_service

pytest: Any = None
try:
    import importlib

    pytest = importlib.import_module("pytest")
except Exception:
    import types

    pytest = types.SimpleNamespace(
        mark=types.SimpleNamespace(skipif=lambda *a, **k: (lambda f: f)),
        skip=lambda *a, **k: None,
    )



def _find_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.mark.skipif(os.environ.get("RUN_OLLAMA_INTEGRATION") != "1", reason="Integration tests disabled")
def test_start_and_stop_ollama_server():
    # require ollama binary present
    if shutil.which("ollama") is None:
        pytest.skip("ollama binary not found on PATH")

    port = _find_free_port()
    host_binding = f"127.0.0.1:{port}"
    base_url = "http://127.0.0.1"

    proc = None
    try:
        proc = ollama_service.start_detached_ollama_serve(host=host_binding)
        # give the server a small window to start
        deadline = time.time() + 30
        while time.time() < deadline:
            if ollama_service.server_is_up(base_url, port):
                break
            time.sleep(0.5)
        assert ollama_service.server_is_up(base_url, port), "Ollama did not become ready"
    finally:
        # attempt graceful stop
        try:
            ollama_service.stop_service(base_url, port, verbose=True)
        except Exception:
            pass
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass
