import sys
import asyncio
from pathlib import Path
import json

# Add app to path
sys.path.insert(0, "/Users/mac/.gemini/antigravity/scratch/PDF-Converter.app/Contents/Resources/app")

try:
    from server import EpubBook, create_epub
    import corrector
    import fitz
except ImportError as e:
    print(f"Missing import: {e}")
    sys.exit(1)

# Paths
pdf_path = Path("/Users/mac/.pdf2epub-app/uploads/336695ea/HassanS_-_Psychomanipulacja_w_sektach.pdf")
if not pdf_path.exists():
    pdf_path = Path("/Users/mac/.pdf2epub-app/uploads/41b62bde/HassanS_-_Psychomanipulacja_w_sektach.pdf")
md_path = Path("/Users/mac/Downloads/marker_output/HassanS_-_Psychomanipulacja_w_sektach/HassanS_-_Psychomanipulacja_w_sektach.md")
out_path = Path("/Users/mac/Desktop/Gotowa_Wersja_Z_Okladka_AI.epub")

async def main():
    print(f"[*] Wczytywanie pliku tekstowego Markdown: {md_path.name}")
    md_text = md_path.read_text(encoding="utf-8")
    
    print("[*] Wyciąganie okładki z oryginalnego pliku PDF...")
    doc = fitz.open(str(pdf_path))
    cover_data = None
    if len(doc) > 0:
        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
        cover_data = pix.tobytes("png")
        print("    -> Pomyślnie wyciągnięto okładkę!")
    
    print("[*] Ładowanie klucza API do korekcji przez GLM-4.5...")
    config_path = Path.home() / ".pdf2epub-app" / "config.json"
    conf = {}
    if config_path.exists():
        conf = json.loads(config_path.read_text())
    
    api_key = conf.get("api_key", "")
    llm_model = conf.get("llm_model", "zhipuai/glm-4-flash")
    if not api_key:
        print("BŁĄD: Brak klucza API GLM w konfiguracji! Ustaw API w ustawieniach apki.")
        return
        
    print(f"[*] Przetwarzanie i łamanie językowe tekstu ({len(md_text)} znaków) z użyciem {llm_model}...")
    try:
        corrected_md = await corrector.correct_markdown(md_text, llm_model, api_key)
    except Exception as e:
        print(f"BŁĄD KOREKTY API: {e}")
        return
    
    print("[*] Budowanie oficjalnego pliku EPUB...")
    book = EpubBook()
    book.set_title("Hassan - Psychomanipulacja w sektach")
    book.set_language("pl")
    if cover_data:
        book.set_cover("cover.png", cover_data)
        
    create_epub(corrected_md, str(out_path), "Hassan", book=book)
    print(f"\n[SUKCES] Wygenerowano gotową książkę pod adresem: {out_path}")

if __name__ == "__main__":
    asyncio.run(main())
