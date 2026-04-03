#!/bin/bash
set -euo pipefail

SCHEME="MailSummariser"
CONFIGURATION="Release"
ARCHIVE_PATH="dist/MailSummariser.xcarchive"
EXPORT_PATH="dist/macos-app"

mkdir -p dist

xcodebuild \
  -scheme "$SCHEME" \
  -configuration "$CONFIGURATION" \
  -archivePath "$ARCHIVE_PATH" \
  archive

APP_PATH="$ARCHIVE_PATH/Products/Applications/MailSummariser.app"
if [[ ! -d "$APP_PATH" ]]; then
  echo "Expected app bundle not found at $APP_PATH" >&2
  exit 1
fi

rm -rf "$EXPORT_PATH"
mkdir -p "$EXPORT_PATH"
cp -R "$APP_PATH" "$EXPORT_PATH/"

echo "Built macOS app artifact at $EXPORT_PATH/MailSummariser.app"
