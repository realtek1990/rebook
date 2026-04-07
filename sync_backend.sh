#!/bin/bash
# sync_backend.sh — Copies backend files from macOS app (single source of truth) to Windows + Linux dist/
# Run this BEFORE building the .exe or Linux binary
set -e

MAC_APP="$(dirname "$0")/ReBook.app/Contents/Resources/app"
WIN_DIST="$(dirname "$0")/windows/dist"
LNX_DIST="$(dirname "$0")/linux/dist"

BACKEND_FILES="converter.py corrector.py i18n.py image_translator.py"

echo "🔄 Syncing backend files: macOS → Windows + Linux dist/"

for dest in "$WIN_DIST" "$LNX_DIST"; do
    mkdir -p "$dest"
    for f in $BACKEND_FILES; do
        if [ -f "$MAC_APP/$f" ]; then
            cp "$MAC_APP/$f" "$dest/$f"
            echo "  ✅ $(basename $dest)/$f"
        else
            echo "  ❌ MISSING: $MAC_APP/$f"
            exit 1
        fi
    done
done

# Also copy platform GUIs → dist/
if [ -f "$(dirname "$0")/windows/rebook_win.py" ]; then
    cp "$(dirname "$0")/windows/rebook_win.py" "$WIN_DIST/rebook_win.py"
    echo "  ✅ rebook_win.py"
fi

if [ -f "$(dirname "$0")/linux/rebook_linux.py" ]; then
    cp "$(dirname "$0")/linux/rebook_linux.py" "$LNX_DIST/rebook_linux.py"
    echo "  ✅ rebook_linux.py"
fi

# Copy requirements
if [ -f "$(dirname "$0")/windows/requirements_win.txt" ]; then
    cp "$(dirname "$0")/windows/requirements_win.txt" "$WIN_DIST/requirements.txt"
    echo "  ✅ requirements.txt (Windows)"
fi

echo ""
echo "✅ Sync complete! All backend files are now identical."
echo "   You can now build the Windows .exe or Linux binary with PyInstaller."
