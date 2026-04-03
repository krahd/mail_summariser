#!/usr/bin/env python3
"""Build platform-specific backend binaries with PyInstaller."""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = REPO_ROOT / "dist"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build backend binary")
    parser.add_argument(
        "--platform",
        choices=["macos", "linux", "windows"],
        required=True,
        help="Target platform for the binary build",
    )
    parser.add_argument("--arch", default="x64", help="Architecture label for artifact naming")
    return parser.parse_args()


def detect_host_platform() -> str:
    host = platform.system().lower()
    if host == "darwin":
        return "macos"
    if host == "linux":
        return "linux"
    if host == "windows":
        return "windows"
    raise RuntimeError(f"Unsupported host platform: {platform.system()}")


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=REPO_ROOT)


def main() -> int:
    args = parse_args()
    host_platform = detect_host_platform()
    if host_platform != args.platform:
        print(
            f"ERROR: cannot build {args.platform} binary from {host_platform}. "
            "Use CI matrix or matching host platform.",
            file=sys.stderr,
        )
        return 2

    if shutil.which("pyinstaller") is None:
        print("ERROR: pyinstaller not found. Install with: pip install pyinstaller", file=sys.stderr)
        return 2

    DIST_DIR.mkdir(parents=True, exist_ok=True)

    separator = ";" if host_platform == "windows" else ":"
    binary_name = f"mail-summariser-backend-{args.platform}-{args.arch}"
    add_data = f"webapp{separator}webapp"

    cmd = [
        "pyinstaller",
        "--clean",
        "--noconfirm",
        "--onefile",
        "--name",
        binary_name,
        "--add-data",
        add_data,
        "backend/main.py",
    ]

    run(cmd)

    output_name = binary_name + (".exe" if host_platform == "windows" else "")
    artifact = DIST_DIR / output_name
    if not artifact.exists():
        print(f"ERROR: expected artifact not found: {artifact}", file=sys.stderr)
        return 2

    print(f"Built artifact: {artifact}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
