#!/usr/bin/env bash
# ── ReBook Windows Dist Sync ────────────────────────────────────────────────
# Kopiuje aktualny backend (macOS) do windows/dist/ przed buildem instalatora.
# Uruchamiaj po każdej zmianie corrector.py / converter.py / etc.
#
# Usage: ./windows/build_win_dist.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_SRC="$REPO_ROOT/ReBook.app/Contents/Resources/app"
WIN_DIST="$SCRIPT_DIR/dist"

mkdir -p "$WIN_DIST"

echo "🔄 Syncing backend → windows/dist/"
for f in corrector.py converter.py image_translator.py i18n.py manual_convert.py; do
    cp "$APP_SRC/$f" "$WIN_DIST/$f"
    echo "   ✅ $f"
done

cp "$SCRIPT_DIR/rebook_win.py" "$WIN_DIST/rebook_win.py"
echo "   ✅ rebook_win.py"

cp "$SCRIPT_DIR/requirements_win.txt" "$WIN_DIST/requirements.txt"
echo "   ✅ requirements.txt (windows)"

echo "🔄 Downloading Python installer (for bundle)..."
curl -sL "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe" -o "$WIN_DIST/python-installer.exe"
echo "   ✅ python-installer.exe"

echo ""
echo "✅ Sync complete: $(ls "$WIN_DIST" | wc -l | tr -d ' ') files in windows/dist/"
echo "   → Commit & push, GitHub Actions will build ReBook-Setup.exe automatically."
