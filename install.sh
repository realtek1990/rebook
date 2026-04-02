#!/bin/bash
# ╔═══════════════════════════════════════════════════════════════════╗
# ║          ReBook — Natywny Instalator macOS (GUI)                ║
# ╚═══════════════════════════════════════════════════════════════════╝
set -e

INSTALL_DIR="$HOME/.pdf2epub-app"
VENV_DIR="$INSTALL_DIR/env"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_BUNDLE="$SCRIPT_DIR/PDF-Converter.app"
LOG_FILE="/tmp/rebook_install.log"

# ── Helper: natywne okno dialogowe ────────────────────────────────────
native_dialog() {
    osascript -e "display dialog \"$1\" with title \"$2\" buttons {\"$3\"} default button \"$3\" with icon note" 2>/dev/null
}

native_error() {
    osascript -e "display dialog \"$1\" with title \"ReBook — Błąd\" buttons {\"OK\"} default button \"OK\" with icon stop" 2>/dev/null
}

# ── Sprawdzenie Python 3 ─────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    native_error "Nie znaleziono Python 3 na tym komputerze.\n\nZainstaluj Python 3 ze strony:\nhttps://www.python.org/downloads/\n\nlub przez Homebrew:\nbrew install python3"
    exit 1
fi

PY_VER=$(python3 --version 2>&1)

# ── Ekran powitalny ──────────────────────────────────────────────────
osascript -e '
display dialog "Witaj w instalatorze ReBook!\n\nReBook to konwerter plików PDF i EPUB ze wsparciem sztucznej inteligencji.\n\nObsługiwane modele AI:\n  • Google Gemini 3 Flash\n  • OpenAI GPT-5 / GPT-4o\n  • Anthropic Claude 4.6 Opus\n  • Mistral Medium\n  • ZhipuAI GLM-4\n  • Groq (Llama 3.3, DeepSeek)\n\nWykryto: '"$PY_VER"'" with title "📚 ReBook — Instalator" buttons {"Anuluj", "Dalej →"} default button "Dalej →" cancel button "Anuluj" with icon note
' 2>/dev/null || exit 0

# ── Wybór trybu instalacji ────────────────────────────────────────────
CHOICE=$(osascript 2>/dev/null <<'APPLESCRIPT'
set installChoice to button returned of (display dialog ¬
    "Wybierz tryb instalacji:" & return & return & ¬
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" & return & ¬
    "⚡ LEKKA (~100 MB)" & return & ¬
    "   • Konwersja EPUB → EPUB / Markdown / HTML" & return & ¬
    "   • Tłumaczenie i korekta AI (30 wątków)" & return & ¬
    "   • Wysyłka na Kindle" & return & ¬
    "   • Obsługa plików EPUB jako wejście" & return & return & ¬
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" & return & ¬
    "📦 PEŁNA (~1.2 GB)" & return & ¬
    "   • Wszystko z wersji Lekkiej" & return & ¬
    "   • + Marker OCR — rozpoznawanie tekstu z PDF" & return & ¬
    "   • + PyTorch (~400 MB) + modele AI (~500 MB)" & return & ¬
    "   • Obsługa plików PDF i EPUB jako wejście" & return & return & ¬
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" & return & ¬
    "Marker OCR można doinstalować później w każdej chwili." ¬
    with title "📚 ReBook — Wybór komponentów" ¬
    buttons {"Anuluj", "⚡ Lekka", "📦 Pełna"} ¬
    default button "⚡ Lekka" ¬
    cancel button "Anuluj" ¬
    with icon note)
return installChoice
APPLESCRIPT
) || exit 0

if [ "$CHOICE" = "📦 Pełna" ]; then
    INSTALL_MARKER=true
    MODE_LABEL="Pełna (z Marker OCR)"
else
    INSTALL_MARKER=false
    MODE_LABEL="Lekka (bez OCR)"
fi

# ── Potwierdzenie ────────────────────────────────────────────────────
osascript -e '
display dialog "Potwierdzenie instalacji:\n\n   📁 Katalog: '"$INSTALL_DIR"'\n   🔧 Tryb: '"$MODE_LABEL"'\n   🐍 Python: '"$PY_VER"'\n\nKliknij \"Instaluj\" aby rozpocząć.\nProces może potrwać kilka minut." with title "📚 ReBook — Potwierdzenie" buttons {"Anuluj", "Instaluj"} default button "Instaluj" cancel button "Anuluj" with icon note
' 2>/dev/null || exit 0

# ── Instalacja w tle z natywnym paskiem postępu ──────────────────────

# Uruchom pasek postępu w tle (natywne okno Cocoa)
osascript -e '
tell application "System Events"
    set progress description to "Instalacja ReBook..."
    set progress additional description to "Przygotowywanie środowiska..."
    set progress total steps to -1
end tell
' 2>/dev/null &

# Funkcja aktualizacji postępu
update_progress() {
    osascript -e "display notification \"$1\" with title \"📚 ReBook Installer\"" 2>/dev/null
}

# ── Krok 1: Katalog roboczy ──────────────────────────────────────────
update_progress "Tworzę katalog roboczy..."
mkdir -p "$INSTALL_DIR/jobs"

# ── Krok 2: Środowisko wirtualne ─────────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    update_progress "Tworzę środowisko Python..."
    python3 -m venv "$VENV_DIR" >> "$LOG_FILE" 2>&1
fi

source "$VENV_DIR/bin/activate"
pip install --upgrade pip -q >> "$LOG_FILE" 2>&1

# ── Krok 3: Pakiety bazowe ───────────────────────────────────────────
update_progress "Instaluję pakiety bazowe (~100 MB)..."
pip install -q \
    pyobjc-framework-Cocoa \
    markdown \
    EbookLib \
    beautifulsoup4 \
    markdownify \
    litellm \
    PyMuPDF \
    >> "$LOG_FILE" 2>&1

# ── Krok 4: Marker OCR (opcjonalnie) ─────────────────────────────────
if [ "$INSTALL_MARKER" = true ]; then
    update_progress "Instaluję Marker OCR + PyTorch (~1 GB)... To może potrwać kilka minut."
    pip install -q marker-pdf >> "$LOG_FILE" 2>&1
fi

# ── Krok 5: Kopiowanie do /Applications ──────────────────────────────
if [ -d "$APP_BUNDLE" ]; then
    COPY_APP=$(osascript -e '
    set copyChoice to button returned of (display dialog "Czy skopiować ReBook do folderu Aplikacje?\n\nPo skopiowaniu będziesz mógł uruchomić ReBook z Launchpada i Spotlight." with title "📚 ReBook — Instalacja" buttons {"Pomiń", "Kopiuj do Aplikacji"} default button "Kopiuj do Aplikacji" with icon note)
    return copyChoice
    ' 2>/dev/null) || COPY_APP="Pomiń"

    if [ "$COPY_APP" = "Kopiuj do Aplikacji" ]; then
        rm -rf "/Applications/ReBook.app" 2>/dev/null
        cp -R "$APP_BUNDLE" "/Applications/ReBook.app"
        FINAL_APP="/Applications/ReBook.app"
    else
        FINAL_APP="$APP_BUNDLE"
    fi
else
    FINAL_APP=""
fi

# ── Gotowe! ───────────────────────────────────────────────────────────
MARKER_NOTE=""
if [ "$INSTALL_MARKER" = false ]; then
    MARKER_NOTE="\n\n💡 Aby później doinstalować Marker OCR:\nUruchom Terminal i wpisz:\nsource ~/.pdf2epub-app/env/bin/activate && pip install marker-pdf"
fi

RESULT=$(osascript -e '
display dialog "✅ Instalacja zakończona pomyślnie!\n\n📚 ReBook jest gotowy do użycia.\n\nJak zacząć:\n1. Uruchom ReBook\n2. Kliknij ⚙️ Ustawienia\n3. Wybierz dostawcę AI i wklej klucz API\n4. Przeciągnij plik na okno i tłumacz!'"$MARKER_NOTE"'" with title "📚 ReBook — Sukces!" buttons {"Zamknij", "Uruchom ReBook"} default button "Uruchom ReBook" with icon note
set result to button returned of result
return result
' 2>/dev/null) || RESULT="Zamknij"

if [ "$RESULT" = "Uruchom ReBook" ] && [ -n "$FINAL_APP" ]; then
    open "$FINAL_APP"
fi
