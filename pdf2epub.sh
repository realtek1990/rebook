#!/bin/bash
# pdf2epub.sh — Konwertuje PDF (skan) na Markdown za pomocą Marker, potem na EPUB via pandoc
# Użycie: ./pdf2epub.sh plik.pdf [język]
# Przykład: ./pdf2epub.sh skan.pdf pl
#           ./pdf2epub.sh skan.pdf en

set -e

MARKER_ENV="/Users/mac/.gemini/antigravity/scratch/marker-env"
MARKER="${MARKER_ENV}/bin/marker_single"

if [ -z "$1" ]; then
    echo "❌ Użycie: $0 plik.pdf [język: pl/en/es/...]"
    exit 1
fi

INPUT_PDF="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
BASENAME="$(basename "$1" .pdf)"
OUTPUT_DIR="$(dirname "$INPUT_PDF")/marker_output"
LANG="${2:-pl}"

echo "📄 Plik:  $INPUT_PDF"
echo "🌍 Język: $LANG"
echo "📁 Wynik: $OUTPUT_DIR/"
echo ""

# Krok 1: PDF → Markdown (Marker z OCR)
echo "🔄 Krok 1/2: Konwersja PDF → Markdown (Marker + OCR)..."
"${MARKER_ENV}/bin/python3.11" -m marker.scripts.convert_single \
    "$INPUT_PDF" \
    "$OUTPUT_DIR" \
    --langs "$LANG" 2>&1 | grep -v "^$"

# Znajdź wygenerowany markdown
MD_FILE=$(find "$OUTPUT_DIR" -name "*.md" -type f | head -1)

if [ -z "$MD_FILE" ]; then
    echo "❌ Nie znaleziono pliku .md w $OUTPUT_DIR"
    exit 1
fi

echo "✅ Markdown: $MD_FILE"

# Krok 2: Markdown → EPUB (pandoc)
EPUB_FILE="$(dirname "$INPUT_PDF")/${BASENAME}.epub"

if command -v pandoc &>/dev/null; then
    echo "🔄 Krok 2/2: Konwersja Markdown → EPUB (pandoc)..."
    pandoc "$MD_FILE" -o "$EPUB_FILE" \
        --metadata title="$BASENAME" \
        --metadata lang="$LANG" \
        --toc \
        --epub-chapter-level=1
    echo "✅ EPUB: $EPUB_FILE"
else
    echo "⚠️ pandoc nie zainstalowany. Zainstaluj: brew install pandoc"
    echo "   Potem ręcznie: pandoc \"$MD_FILE\" -o \"$EPUB_FILE\""
fi

echo ""
echo "🎉 Gotowe!"
