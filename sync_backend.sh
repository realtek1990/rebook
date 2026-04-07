#!/bin/bash
# sync_backend.sh — Copies backend files from macOS app (single source of truth) to Windows dist/
# Run this BEFORE building the Windows .exe
set -e

MAC_APP="$(dirname "$0")/ReBook.app/Contents/Resources/app"
WIN_DIST="$(dirname "$0")/windows/dist"

BACKEND_FILES="converter.py corrector.py i18n.py image_translator.py"

echo "🔄 Syncing backend files: macOS → Windows dist/"

for f in $BACKEND_FILES; do
    if [ -f "$MAC_APP/$f" ]; then
        cp "$MAC_APP/$f" "$WIN_DIST/$f"
        echo "  ✅ $f"
    else
        echo "  ❌ MISSING: $MAC_APP/$f"
        exit 1
    fi
done

# Also copy rebook_win.py main → dist/
if [ -f "$(dirname "$0")/windows/rebook_win.py" ]; then
    cp "$(dirname "$0")/windows/rebook_win.py" "$WIN_DIST/rebook_win.py"
    echo "  ✅ rebook_win.py"
fi

# Copy requirements
if [ -f "$(dirname "$0")/windows/requirements_win.txt" ]; then
    cp "$(dirname "$0")/windows/requirements_win.txt" "$WIN_DIST/requirements.txt"
    echo "  ✅ requirements.txt"
fi

echo ""
echo "✅ Sync complete! All backend files are now identical."
echo "   You can now build the Windows .exe with PyInstaller."
