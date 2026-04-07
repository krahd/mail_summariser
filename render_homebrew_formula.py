#!/usr/bin/env python3
"""Render the Homebrew formula for the packaged backend release."""

from __future__ import annotations

import argparse
import re
import textwrap
from pathlib import Path
from urllib.parse import urlparse

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render Homebrew formula")
    parser.add_argument("--release-tag", required=True, help="Release tag such as v1.2.3")
    parser.add_argument("--macos-url", required=True,
                        help="GitHub release URL for the macOS backend archive")
    parser.add_argument("--macos-sha256", required=True,
                        help="SHA256 for the macOS backend archive")
    parser.add_argument("--linux-url", required=True,
                        help="GitHub release URL for the Linux backend archive")
    parser.add_argument("--linux-sha256", required=True,
                        help="SHA256 for the Linux backend archive")
    parser.add_argument("--output", required=True, help="Path to write the rendered formula")
    return parser.parse_args()


def validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"Expected an https URL, got: {url}")
    return url


def validate_sha256(value: str) -> str:
    sha256_value = value.strip().lower()
    if not SHA256_PATTERN.fullmatch(sha256_value):
        raise ValueError(f"Expected a 64-character SHA256 digest, got: {value}")
    return sha256_value


def release_version(release_tag: str) -> str:
    tag = release_tag.strip()
    if not tag:
        raise ValueError("Release tag must not be empty")
    return tag[1:] if tag.startswith("v") and len(tag) > 1 else tag


def render_formula(*, version: str, macos_url: str, macos_sha256: str, linux_url: str, linux_sha256: str) -> str:
    return textwrap.dedent(
        f'''\
        class MailSummariser < Formula
          desc "Local-first mail workflow backend"
          homepage "https://github.com/krahd/Mail-Summariser"
          version "{version}"
          license "MIT"

          on_macos do
            on_arm do
              url "{macos_url}"
              sha256 "{macos_sha256}"
            end
          end

          on_linux do
            on_intel do
              url "{linux_url}"
              sha256 "{linux_sha256}"
            end
          end

          def install
            binary_name = if OS.mac?
              "mail_summariser-backend-macos-arm64"
            else
              "mail_summariser-backend-linux-x64"
            end

            libexec.install binary_name => "mail_summariser-backend"

            (bin/"mail_summariser").write <<~SH
              #!/usr/bin/env bash
              set -euo pipefail
              if [[ -z "${{MAIL_SUMMARISER_DATA_DIR:-}}" ]]; then
                if [[ "$(uname -s)" == "Darwin" ]]; then
                  export MAIL_SUMMARISER_DATA_DIR="$HOME/Library/Application Support/MailSummariser"
                else
                  export MAIL_SUMMARISER_DATA_DIR="${{XDG_DATA_HOME:-$HOME/.local/share}}/mail_summariser"
                fi
              fi
              exec "#{{libexec}}/mail_summariser-backend" "$@"
            SH
            chmod 0755, bin/"mail_summariser"
          end

          test do
            shell_output("#{{bin}}/mail_summariser --help")
          end
        end
        '''
    )


def main() -> int:
    args = parse_args()

    formula = render_formula(
        version=release_version(args.release_tag),
        macos_url=validate_url(args.macos_url),
        macos_sha256=validate_sha256(args.macos_sha256),
        linux_url=validate_url(args.linux_url),
        linux_sha256=validate_sha256(args.linux_sha256),
    )

    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(formula, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
