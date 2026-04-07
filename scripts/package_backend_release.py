#!/usr/bin/env python3
"""Package built backend binaries into release-friendly archives."""

from __future__ import annotations

import argparse
import tarfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = REPO_ROOT / "dist"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Package backend release artifact")
    parser.add_argument("--platform", choices=["macos", "linux", "windows"], required=True)
    parser.add_argument("--arch", required=True)
    parser.add_argument("--input", required=True, help="Path to built backend binary")
    parser.add_argument("--output-dir", default=str(DIST_DIR / "packages"))
    return parser.parse_args()


def package_tar_gz(source: Path, destination: Path) -> None:
    with tarfile.open(destination, "w:gz") as archive:
        archive.add(source, arcname=source.name)


def package_zip(source: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(source, arcname=source.name)


def main() -> int:
    args = parse_args()
    source = Path(args.input).resolve()
    if not source.exists():
        raise FileNotFoundError(f"Input artifact not found: {source}")

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    base_name = f"mail_summariser-backend-{args.platform}-{args.arch}"
    if args.platform == "windows":
        destination = output_dir / f"{base_name}.zip"
        package_zip(source, destination)
    else:
        destination = output_dir / f"{base_name}.tar.gz"
        package_tar_gz(source, destination)

    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
