#!/bin/bash
set -euo pipefail

SCHEME="MailSummariser"
CONFIGURATION="Debug"

echo "Building $SCHEME..."
xcodebuild -scheme "$SCHEME" -configuration "$CONFIGURATION" build >/dev/null

APP_PATH="$(
  xcodebuild -scheme "$SCHEME" -configuration "$CONFIGURATION" -showBuildSettings 2>/dev/null \
    | awk -F ' = ' '
        /TARGET_BUILD_DIR/ { build_dir=$2 }
        /FULL_PRODUCT_NAME/ { product_name=$2 }
        END { print build_dir "/" product_name }
      '
)"

if [ ! -d "$APP_PATH" ]; then
  echo "App not found: $APP_PATH"
  exit 1
fi

echo "Running: $APP_PATH"
open "$APP_PATH"