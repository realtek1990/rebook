#!/bin/bash
# ╔═══════════════════════════════════════════════════════════════════╗
# ║               ReBook — Instalator macOS                         ║
# ║     PDF/EPUB Converter ze wsparciem AI (Gemini, GPT, Claude)    ║
# ╚═══════════════════════════════════════════════════════════════════╝

set -e

# ── Kolory ────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

INSTALL_DIR="$HOME/.pdf2epub-app"
VENV_DIR="$INSTALL_DIR/env"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_BUNDLE="$SCRIPT_DIR/PDF-Converter.app"

# ── Nagłówek ──────────────────────────────────────────────────────────
clear
echo ""
echo -e "${MAGENTA}${BOLD}"
echo "  ╔═══════════════════════════════════════════════════╗"
echo "  ║                                                   ║"
echo "  ║     📚  R e B o o k   I n s t a l e r  📚        ║"
echo "  ║                                                   ║"
echo "  ║     PDF/EPUB → EPUB/MD/HTML                       ║"
echo "  ║     z tłumaczeniem AI (Gemini, GPT, Claude)       ║"
echo "  ║                                                   ║"
echo "  ╚═══════════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""

# ── Sprawdzenie Python 3 ─────────────────────────────────────────────
echo -e "${CYAN}${BOLD}[1/5]${NC} Sprawdzam Python 3..."
if command -v python3 &>/dev/null; then
    PY_VER=$(python3 --version 2>&1)
    echo -e "  ${GREEN}✓${NC} Znaleziono: ${BOLD}$PY_VER${NC}"
else
    echo -e "  ${RED}✗ Brak Python 3!${NC}"
    echo -e "  Zainstaluj Python 3 z ${BLUE}https://www.python.org${NC} lub przez Homebrew:"
    echo -e "  ${YELLOW}brew install python3${NC}"
    exit 1
fi

# ── Tworzenie katalogu roboczego ──────────────────────────────────────
echo ""
echo -e "${CYAN}${BOLD}[2/5]${NC} Przygotowuję katalog roboczy..."
mkdir -p "$INSTALL_DIR/jobs"
echo -e "  ${GREEN}✓${NC} Katalog: ${BOLD}$INSTALL_DIR${NC}"

# ── Środowisko wirtualne ─────────────────────────────────────────────
echo ""
echo -e "${CYAN}${BOLD}[3/5]${NC} Tworzę środowisko wirtualne Python..."
if [ -d "$VENV_DIR" ]; then
    echo -e "  ${YELLOW}⚠${NC} Środowisko już istnieje. Pomijam tworzenie."
    echo -e "  ${YELLOW}  (Aby wymusić reinstalację, usuń: $VENV_DIR)${NC}"
else
    python3 -m venv "$VENV_DIR"
    echo -e "  ${GREEN}✓${NC} Utworzono środowisko wirtualne"
fi

source "$VENV_DIR/bin/activate"
pip install --upgrade pip -q 2>/dev/null

# ── Wybor komponentów ────────────────────────────────────────────────
echo ""
echo -e "${MAGENTA}${BOLD}╔═══════════════════════════════════════════════════╗${NC}"
echo -e "${MAGENTA}${BOLD}║           WYBÓR KOMPONENTÓW                       ║${NC}"
echo -e "${MAGENTA}${BOLD}╚═══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BOLD}ReBook może działać w dwóch trybach:${NC}"
echo ""
echo -e "  ${GREEN}${BOLD}[1] Lekka instalacja${NC} (~100 MB)"
echo -e "      • Konwersja EPUB → EPUB/MD/HTML"
echo -e "      • Tłumaczenie i korekta AI (Gemini, GPT, Claude...)"
echo -e "      • Wysyłka na Kindle"
echo -e "      • ${YELLOW}Bez OCR z PDF${NC} (pliki PDF nie będą obsługiwane)"
echo ""
echo -e "  ${BLUE}${BOLD}[2] Pełna instalacja${NC} (~1.2 GB)"
echo -e "      • Wszystko z opcji 1"
echo -e "      • ${GREEN}+ Marker OCR${NC} — rozpoznawanie tekstu z PDF"
echo -e "      • Wymaga pobrania PyTorch (~400 MB) i modeli AI (~500 MB)"
echo ""
echo -e "  ${YELLOW}${BOLD}[3] Anuluj instalację${NC}"
echo ""

while true; do
    echo -ne "  ${BOLD}Wybierz opcję [1/2/3]: ${NC}"
    read -r choice
    case "$choice" in
        1) INSTALL_MARKER=false; break ;;
        2) INSTALL_MARKER=true; break ;;
        3) echo -e "\n  ${YELLOW}Instalacja anulowana.${NC}"; exit 0 ;;
        *) echo -e "  ${RED}Nieprawidłowy wybór. Wpisz 1, 2 lub 3.${NC}" ;;
    esac
done

# ── Instalacja zależności ─────────────────────────────────────────────
echo ""
echo -e "${CYAN}${BOLD}[4/5]${NC} Instaluję zależności..."

# Core dependencies (always installed)
echo -e "  ${BLUE}→${NC} Instaluję pakiety bazowe..."
pip install -q \
    pyobjc-framework-Cocoa \
    markdown \
    EbookLib \
    beautifulsoup4 \
    markdownify \
    litellm \
    PyMuPDF \
    2>&1 | tail -1

echo -e "  ${GREEN}✓${NC} Pakiety bazowe zainstalowane"

if [ "$INSTALL_MARKER" = true ]; then
    echo ""
    echo -e "  ${BLUE}→${NC} Instaluję Marker OCR + PyTorch (to może potrwać kilka minut)..."
    pip install -q marker-pdf 2>&1 | tail -3
    echo -e "  ${GREEN}✓${NC} Marker OCR zainstalowany"
else
    echo -e "  ${YELLOW}→${NC} Marker OCR pominięty (możesz doinstalować później: ${BOLD}install.sh${NC})"
fi

# ── Kopiowanie aplikacji do /Applications ─────────────────────────────
echo ""
echo -e "${CYAN}${BOLD}[5/5]${NC} Finalizuję instalację..."

if [ -d "$APP_BUNDLE" ]; then
    echo -ne "  Czy chcesz skopiować ReBook.app do /Applications? [t/n]: "
    read -r copy_app
    if [[ "$copy_app" =~ ^[tTyY]$ ]]; then
        # Remove old version if exists
        rm -rf "/Applications/ReBook.app" 2>/dev/null
        cp -R "$APP_BUNDLE" "/Applications/ReBook.app"
        echo -e "  ${GREEN}✓${NC} Skopiowano do ${BOLD}/Applications/ReBook.app${NC}"
        echo -e "  ${GREEN}✓${NC} Możesz teraz uruchomić ReBook z Launchpada lub Spotlight!"
    else
        echo -e "  ${YELLOW}→${NC} Pominięto kopiowanie. Uruchom ręcznie: ${BOLD}open $APP_BUNDLE${NC}"
    fi
else
    echo -e "  ${YELLOW}⚠${NC} Nie znaleziono PDF-Converter.app w katalogu instalatora"
    echo -e "  ${YELLOW}  Upewnij się, że install.sh jest obok PDF-Converter.app${NC}"
fi

# ── Gotowe! ───────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}"
echo "  ╔═══════════════════════════════════════════════════╗"
echo "  ║                                                   ║"
echo "  ║     ✅  Instalacja zakończona pomyślnie!          ║"
echo "  ║                                                   ║"
echo "  ╚═══════════════════════════════════════════════════╝"
echo -e "${NC}"

if [ "$INSTALL_MARKER" = false ]; then
    echo -e "  ${YELLOW}💡 Aby później doinstalować Marker OCR (obsługa PDF):${NC}"
    echo -e "     ${BOLD}source $VENV_DIR/bin/activate && pip install marker-pdf${NC}"
    echo ""
fi

echo -e "  ${BOLD}Jak zacząć:${NC}"
echo -e "  1. Uruchom ReBook z Launchpada lub: ${BOLD}open /Applications/ReBook.app${NC}"
echo -e "  2. Kliknij ⚙️ (Ustawienia) i podaj klucz API swojego dostawcy AI"
echo -e "  3. Przeciągnij plik EPUB/PDF na okno i kliknij \"Konwertuj\"!"
echo ""
echo -e "  ${CYAN}Miłego czytania! 📖${NC}"
echo ""
