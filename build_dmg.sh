#!/bin/bash
# ── ReBook DMG Builder ─────────────────────────────────────────────
# Creates a distributable ReBook.dmg with the app and /Applications symlink.
# Usage: ./build_dmg.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="ReBook"
DMG_NAME="${APP_NAME}.dmg"
STAGING="${SCRIPT_DIR}/.dmg_staging"

echo "📦 Building ${DMG_NAME}..."

# Clean
rm -rf "${STAGING}" "${SCRIPT_DIR}/${DMG_NAME}"
mkdir -p "${STAGING}"

# Copy app + Applications symlink
cp -R "${SCRIPT_DIR}/${APP_NAME}.app" "${STAGING}/"
ln -sf /Applications "${STAGING}/Applications"

# Remove __pycache__ — .pyc files change on every run and invalidate codesign
echo "🧹 Cleaning __pycache__..."
find "${STAGING}/${APP_NAME}.app" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Sign the app bundle (adhoc) — required for macOS to allow launch
echo "🔏 Signing ${APP_NAME}.app..."
codesign --force --deep --sign - "${STAGING}/${APP_NAME}.app"
codesign --verify --deep "${STAGING}/${APP_NAME}.app"
echo "   Signature OK"

# Build compressed DMG
hdiutil create \
    -volname "${APP_NAME}" \
    -srcfolder "${STAGING}" \
    -ov \
    -format UDZO \
    "${SCRIPT_DIR}/${DMG_NAME}"

# Clean staging
rm -rf "${STAGING}"

SIZE=$(du -h "${SCRIPT_DIR}/${DMG_NAME}" | cut -f1)
echo ""
echo "✅ ${DMG_NAME} created (${SIZE})"
echo "   → ${SCRIPT_DIR}/${DMG_NAME}"
