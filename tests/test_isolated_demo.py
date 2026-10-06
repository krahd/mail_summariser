"""Demo has its own process so its locked configuration cannot affect live tests."""
from pathlib import Path
import subprocess
import sys


def test_isolated_demo_acceptance():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, 'scripts/validate_demo_api.py'], cwd=root,
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
