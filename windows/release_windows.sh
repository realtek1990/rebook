#!/usr/bin/env bash
# ── ReBook Windows — Lokalny sync + push do GitHub Actions ──────────────────
# Syncuje backend, commituje i pushuje → GitHub Actions builduje .exe
#
# Usage: ./windows/release_windows.sh [version]
# Example: ./windows/release_windows.sh 2.2.1

set -e
VERSION="${1:-2.2.1}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "🪟  ReBook Windows Release v$VERSION"
echo "============================================"

# 1. Sync backend files
bash "$SCRIPT_DIR/build_win_dist.sh"

# 2. Update version in installer.iss
sed -i '' "s/#define MyAppVersion \".*\"/#define MyAppVersion \"$VERSION\"/" \
    "$SCRIPT_DIR/installer.iss"
echo "✅ installer.iss → v$VERSION"

# 3. Commit & push → GitHub Actions triggers
cd "$REPO_ROOT"
git add windows/ assets/ .github/
git commit -m "chore: sync Windows installer v$VERSION" || echo "(nothing new to commit)"
git push origin main

echo ""
echo "🚀 Pushed! GitHub Actions is building:"
echo "   → https://github.com/realtek1990/rebook/actions"
echo ""
echo "After ~10 min, download ReBook-Setup-$VERSION.exe from:"
echo "   → https://github.com/realtek1990/rebook/actions (Artifacts)"
echo ""
echo "To create a full release with tag:"
echo "   git tag v$VERSION && git push origin v$VERSION"
