"""Demo has its own process so its locked configuration cannot affect live tests."""
from pathlib import Path
import subprocess
import sys


def test_isolated_demo_acceptance():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, 'scripts/validate_demo_api.py'], cwd=root,
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_demo_client_state_regressions():
    import shutil
    import pytest
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for mocked client-state checks; Chromium CI also covers these flows')
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([node, 'scripts/validate_demo_client_state.cjs'], cwd=root,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
