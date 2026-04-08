#!/bin/bash
# ── ReBook macOS Packager ─────────────────────────────────────────────────────
# Produces:
#   ReBook.dmg  — contains ReBook.app + Applications symlink + drag-to-install
#   ReBook.pkg  — flat macOS Installer with postinstall quarantine removal
#
# The .pkg inside CI is published as a separate download.
# The .dmg also includes an Install script for quick quarantine bypass.
# Usage: ./build_dmg.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="ReBook"
DMG_NAME="${APP_NAME}.dmg"
PKG_NAME="${APP_NAME}.pkg"
STAGING="${SCRIPT_DIR}/.dmg_staging"
PKG_STAGING="${SCRIPT_DIR}/.pkg_staging"

# ─────────────────────────────────────────────────────────────────────────────
# 1. Clean & sign the app bundle (ad-hoc, hardened runtime)
# ─────────────────────────────────────────────────────────────────────────────
echo "🔏 Signing ${APP_NAME}.app (ad-hoc)..."
find "${SCRIPT_DIR}/${APP_NAME}.app" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
xattr -cr "${SCRIPT_DIR}/${APP_NAME}.app" 2>/dev/null || true
codesign --force --deep --sign - --options runtime "${SCRIPT_DIR}/${APP_NAME}.app"
codesign --verify --deep "${SCRIPT_DIR}/${APP_NAME}.app"
echo "   Signature OK"

# ─────────────────────────────────────────────────────────────────────────────
# 2. Build DMG (drag-and-drop + Install.command)
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "📦 Building ${DMG_NAME}..."
rm -rf "${STAGING}" "${SCRIPT_DIR}/${DMG_NAME}"
mkdir -p "${STAGING}"
cp -R "${SCRIPT_DIR}/${APP_NAME}.app" "${STAGING}/"
ln -sf /Applications "${STAGING}/Applications"

# ── Install helper — user double-clicks this to bypass Gatekeeper ──
cat > "${STAGING}/Instaluj ReBook.command" << 'INSTALL_EOF'
#!/bin/bash
# ╔══════════════════════════════════════════════════════════╗
# ║   ReBook — Instalator macOS                              ║
# ║   Ten skrypt kopiuje ReBook do Aplikacji                 ║
# ║   i automatycznie wyłącza blokadę Gatekeeper.            ║
# ╚══════════════════════════════════════════════════════════╝
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_SRC="${SCRIPT_DIR}/ReBook.app"
APP_DST="/Applications/ReBook.app"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║       🔧 Instaluję ReBook...                ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# Copy app to /Applications (replacing old version)
if [ -d "$APP_DST" ]; then
    echo "→ Usuwam starą wersję..."
    rm -rf "$APP_DST"
fi

echo "→ Kopiuję do /Applications..."
cp -R "$APP_SRC" "$APP_DST"

# Strip quarantine flag (the key fix for Gatekeeper)
echo "→ Wyłączam blokadę Gatekeeper..."
xattr -dr com.apple.quarantine "$APP_DST" 2>/dev/null || true

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  ✅ Gotowe! Uruchamiam ReBook...             ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
open "$APP_DST"
INSTALL_EOF
chmod +x "${STAGING}/Instaluj ReBook.command"

# ── README ──
cat > "${STAGING}/PRZECZYTAJ.txt" << 'README_EOF'
╔══════════════════════════════════════════════════════════╗
║          PIERWSZE URUCHOMIENIE — WAŻNE                   ║
╚══════════════════════════════════════════════════════════╝

NAJŁATWIEJ: Kliknij dwukrotnie "Instaluj ReBook.command"
            → zainstaluje i uruchomi ReBook automatycznie.

Alternatywnie:
  1. Przeciągnij ReBook.app do Applications.
  2. Otwórz Terminal i wklej:
     xattr -dr com.apple.quarantine /Applications/ReBook.app
  3. Uruchom ReBook z Launchpada.

Pytania: github.com/realtek1990/rebook
README_EOF

hdiutil create \
    -volname "${APP_NAME}" \
    -srcfolder "${STAGING}" \
    -ov -format UDZO \
    "${SCRIPT_DIR}/${DMG_NAME}"
rm -rf "${STAGING}"
echo "✅ ${DMG_NAME} OK ($(du -h "${SCRIPT_DIR}/${DMG_NAME}" | cut -f1))"

# ─────────────────────────────────────────────────────────────────────────────
# 3. Build PKG (standard macOS Installer — auto-strips quarantine)
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "📦 Building ${PKG_NAME}..."
rm -rf "${PKG_STAGING}" "${SCRIPT_DIR}/${PKG_NAME}"

# Payload: app goes to /Applications
APP_ROOT="${PKG_STAGING}/root/Applications"
mkdir -p "${APP_ROOT}"
cp -R "${SCRIPT_DIR}/${APP_NAME}.app" "${APP_ROOT}/"

# postinstall script — strips quarantine AFTER the Installer copies the app
SCRIPTS_DIR="${PKG_STAGING}/scripts"
mkdir -p "${SCRIPTS_DIR}"
cat > "${SCRIPTS_DIR}/postinstall" << 'POSTINSTALL_EOF'
#!/bin/bash
# Remove Gatekeeper quarantine attribute so the app opens without any warnings
xattr -dr com.apple.quarantine /Applications/ReBook.app 2>/dev/null || true
exit 0
POSTINSTALL_EOF
chmod +x "${SCRIPTS_DIR}/postinstall"

# Build flat package
pkgbuild \
    --root "${APP_ROOT}" \
    --scripts "${SCRIPTS_DIR}" \
    --identifier "com.rebook.app" \
    --version "1.0" \
    --install-location "/Applications" \
    "${SCRIPT_DIR}/${PKG_NAME}"

rm -rf "${PKG_STAGING}"
echo "✅ ${PKG_NAME} OK ($(du -h "${SCRIPT_DIR}/${PKG_NAME}" | cut -f1))"
echo ""
echo "Distribution files:"
ls -lh "${SCRIPT_DIR}/${DMG_NAME}" "${SCRIPT_DIR}/${PKG_NAME}"
