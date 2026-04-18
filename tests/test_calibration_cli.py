import os
import subprocess
import sys
import pytest


@pytest.mark.skipif(os.environ.get("RUN_CALIBRATE_TEST") != "1", reason="Calibration tests disabled by default")
def test_calibrate_cli_runs_when_ollama_available():
    # This integration test will attempt to contact a local Ollama server.
    # It is skipped by default; enable with RUN_CALIBRATE_TEST=1 in CI or locally.
    proc = subprocess.run(
        [sys.executable, "scripts/calibrate_timeout_catalog.py",
            "--models", "llama-2-13b", "--iterations", "1"],
        capture_output=True,
        check=False,
        text=True,
        timeout=120,
    )
    # Accept either success or graceful abort when Ollama is not available
    assert proc.returncode in (0, 2)
