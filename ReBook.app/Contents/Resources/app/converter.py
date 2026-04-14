"""ReBook — Standalone conversion pipeline (PDF/EPUB/MD → EPUB/HTML/MD).

Synchronous module usable by both the native macOS GUI and the web interface.
Delegates AI correction/translation to corrector.py.
"""
import json
import os
import re
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Callable, Optional

import markdown as md_lib
from ebooklib import epub

import corrector
import image_translator

if sys.platform == "win32":
    WORKSPACE_DIR = Path.home() / ".rebook"
else:
    WORKSPACE_DIR = Path.home() / ".pdf2epub-app"




# ─── Public API ───────────────────────────────────────────────────────────────

def convert_file(
    input_path: str,
    output_format: str = "epub",
    use_llm: bool = False,
    use_translate: bool = False,
    translate_images: bool = False,
    verify_translation: bool = False,
    lang_from: str = "",
    lang_to: str = "polski",
    progress_callback: Optional[Callable[[str, int, str], None]] = None,
    page_start: int = 0,
    page_end: int = 0,
) -> str:
    """Run the full conversion pipeline synchronously.

    Args:
        input_path: Path to input file (PDF, EPUB, or MD).
        output_format: 'epub', 'html', or 'md'.
        use_llm: Enable AI correction/translation.
        use_translate: Translate instead of correcting (requires use_llm).
        lang_from: Source language (empty = auto-detect).
        lang_to: Target language.
        progress_callback: ``fn(stage, percent, message)`` called on updates.
        page_start: First PDF page to process (1-indexed, 0 = from beginning).
        page_end: Last PDF page to process (1-indexed, 0 = to end).

    Returns:
        Absolute path to the output file.
    """
    src = Path(input_path)

    def report(stage: str, pct: int, msg: str):
        if progress_callback:
            progress_callback(stage, pct, msg)

    job_dir = WORKSPACE_DIR / "jobs" / uuid.uuid4().hex[:8]
    job_dir.mkdir(parents=True, exist_ok=True)
    images_dir = job_dir / "images"
    images_dir.mkdir(exist_ok=True)
    # Collect images that need embedding in EPUB output
    collected_images = {}  # filename -> bytes

    # ── Stage 1: Text Extraction / OCR ────────────────────────────────────
    ext = src.suffix.lower()
    ocr_already_translated = False  # True when OCR+translate was done in one step

    if ext == ".md":
        report("ocr", 100, "Pominięto OCR — plik Markdown")
        md_text = src.read_text(encoding="utf-8")

    elif ext == ".epub":
        report("ocr", 10, "Rozpakowywanie EPUB…")
        md_text, collected_images = _extract_epub(src, images_dir)
        report("ocr", 100, f"Ekstrakcja EPUB zakończona ({len(collected_images)} ilustracji)")

    else:  # .pdf
        report("ocr", 0, "OCR — rozpoznawanie tekstu…")
        cfg = corrector.get_config()
        cloud_text = None
        if corrector.is_cloud_ocr_available(cfg):
            # Combined OCR+translate in one Gemini request (saves ~50% tokens)
            ocr_cfg = corrector.get_ocr_config(cfg)
            can_combine = (use_translate and lang_to
                           and ocr_cfg.get("provider", "auto") in ("gemini", "auto")
                           and ocr_cfg.get("llm_provider") == "gemini")
            try:
                if can_combine:
                    report("ocr", 5, f"OCR + tłumaczenie → {lang_to} (Gemini Flash-Lite per-page)…")
                    cloud_result = corrector.ocr_pdf(
                        str(src), config=cfg, progress_callback=progress_callback,
                        translate_lang=lang_to, translate_from=lang_from,
                        page_start=page_start, page_end=page_end,
                    )
                    # Handle new tuple format (text, images) from per-page engine
                    if isinstance(cloud_result, tuple):
                        cloud_text, pdf_images = cloud_result
                        collected_images.update(pdf_images)
                    else:
                        cloud_text = cloud_result
                    ocr_already_translated = True
                else:
                    cloud_result = corrector.ocr_pdf(
                        str(src), config=cfg, progress_callback=progress_callback,
                        page_start=page_start, page_end=page_end,
                    )
                    if isinstance(cloud_result, tuple):
                        cloud_text, pdf_images = cloud_result
                        collected_images.update(pdf_images)
                    else:
                        cloud_text = cloud_result
            except Exception as e:
                report("ocr", 0, f"⚠️ Cloud OCR nie powiodło się ({e}) — próbuję lokalną ekstrakcję…")
                ocr_already_translated = False
        if cloud_text is not None:
            md_text = cloud_text
        else:
            md_text = _fitz_extract_text(src, progress_callback)
        report("ocr", 100, "OCR zakończone")

    # ── Stage 2: AI Correction / Translation ──────────────────────────────
    md_original = md_text  # save original for verification pass
    if use_llm and not ocr_already_translated:
        label = "Tłumaczenie" if use_translate else "Korekcja AI"
        report("correction", 0, f"{label} — inicjalizacja…")

        if not corrector.is_api_available():
            raise RuntimeError("⚠️ BRAK KLUCZA API!\nWejdź w Ustawienia (⚙️) u góry po prawej, wybierz dostawcę AI i wklej poprawny klucz swojego konta aby uruchomić tryb tłumaczenia/korekty.")

        # Checkpoint sidecar: named after input file + language pair
        # e.g. MyBook_ang_pol.rebook_progress.json  (next to the input file)
        _ckpt_suffix = f"_{(lang_from or 'auto')[:3]}_{lang_to[:3]}".lower() if use_translate else ""
        _ckpt_path   = str(src.with_name(src.stem + _ckpt_suffix + ".rebook_progress.json"))

        def on_llm(cur, tot, msg):
            pct = int(cur / tot * 100) if tot else 0
            report("correction", pct, f"{label} ({cur}/{tot})")

        md_text = corrector.correct_markdown(
            md_text,
            use_translate=use_translate,
            lang_to=lang_to,
            lang_from=lang_from,
            progress_callback=on_llm,
            checkpoint_path=_ckpt_path,
        )
        report("correction", 100, f"{label} zakończona")

    elif ocr_already_translated:
        report("correction", 100, "✅ Tłumaczenie wykonane podczas OCR (oszczędność ~50% tokenów)")

    # FIX Luka 1: Always deduplicate markdown after AI, regardless of translate/correct mode
    if use_llm:
        md_text = corrector._deduplicate_markdown(md_text)

    # ── Stage 2.5: Verification Pass (opt-in) ──────────────────────────────
    if use_llm and use_translate and verify_translation:
        report("verification", 0, "🔍 Weryfikacja tłumaczenia…")

        def on_verify(cur, tot, msg):
            pct = int(cur / tot * 100) if tot else 0
            report("verification", pct, msg)

        md_text = corrector.verify_translation(
            original_markdown=md_original,
            translated_markdown=md_text,
            lang_from=lang_from or "angielski",
            lang_to=lang_to,
            progress_callback=on_verify,
        )
        report("verification", 100, "✅ Weryfikacja zakończona")

    # ── Stage 2.75: Image Translation (Nano Banana 2) ────────────────────
    translated_images = {}
    if translate_images and use_translate and collected_images:
        report("images", 0, "🎨 Tłumaczenie ilustracji…")

        def on_img(cur, tot, msg):
            pct = int(cur / tot * 100) if tot else 0
            report("images", pct, msg)

        translated_images = image_translator.process_book_images(
            images=collected_images,
            lang_from=lang_from or "angielski",
            lang_to=lang_to,
            progress_callback=on_img,
        )
        report("images", 100,
            f"✅ Przetłumaczono {len(translated_images)}/{len(collected_images)} ilustracji")

    # ── Stage 3: Export ───────────────────────────────────────────────────
    report("export", 50, f"Eksport → {output_format.upper()}…")
    basename = src.stem

    # When translating, add target language suffix to filename
    if use_translate and lang_to:
        lang_suffix = lang_to.strip().lower()[:3]  # "ang", "pol", "nie", etc.
        basename = f"{basename}_{lang_suffix}"

    # Map common language names to ISO 639-1 codes for EPUB metadata
    _lang_codes = {
        "polski": "pl", "angielski": "en", "english": "en",
        "niemiecki": "de", "francuski": "fr", "hiszpański": "es",
        "włoski": "it", "portugalski": "pt", "rosyjski": "ru",
        "ukraiński": "uk", "czeski": "cs", "słowacki": "sk",
        "chiński": "zh", "japoński": "ja", "koreański": "ko",
        "turecki": "tr", "arabski": "ar", "holenderski": "nl",
        "szwedzki": "sv", "norweski": "no", "duński": "da",
        "fiński": "fi", "węgierski": "hu", "rumuński": "ro",
    }
    epub_lang = _lang_codes.get(lang_to.strip().lower(), "pl") if use_translate else "pl"
    epub_title = f"{src.stem} [{lang_to}]" if use_translate else src.stem

    if output_format == "epub":
        out = job_dir / f"{basename}.epub"
        book = epub.EpubBook()
        book.set_identifier(f"rebook-{uuid.uuid4().hex[:8]}")
        book.set_title(epub_title)
        book.set_language(epub_lang)
        _extract_cover(src, book)
        # Embed all collected images into the EPUB
        # Both original and translated versions (translated in images_translated/ subfolder)
        for img_name, img_data in collected_images.items():
            mime = "image/png" if img_name.endswith(".png") else "image/jpeg"
            # Original image
            img_item = epub.EpubImage()
            img_item.file_name = f"images/{img_name}"
            img_item.media_type = mime
            img_item.content = img_data
            book.add_item(img_item)
            # Translated image (if available)
            if img_name in translated_images:
                tr_item = epub.EpubImage()
                tr_item.file_name = f"images_translated/{img_name}"
                tr_item.media_type = "image/png"  # Nano Banana outputs PNG
                tr_item.content = translated_images[img_name]
                book.add_item(tr_item)
        # If images were translated, update markdown references
        # to use translated versions (originals remain accessible)
        if translated_images:
            for img_name in translated_images:
                md_text = md_text.replace(
                    f"images/{img_name}",
                    f"images_translated/{img_name}"
                )
        _create_epub(md_text, str(out), basename, book)

    elif output_format == "html":
        out = job_dir / f"{basename}.html"
        body = md_lib.markdown(md_text, extensions=["tables", "smarty"])
        out.write_text(
            f'<!DOCTYPE html><html lang="pl"><head><meta charset="utf-8">'
            f"<title>{basename}</title>"
            "<style>body{font-family:Georgia,serif;max-width:800px;"
            "margin:2em auto;line-height:1.6;padding:0 1em}"
            "h1{font-size:1.8em}h2{font-size:1.4em}"
            "table{border-collapse:collapse;width:100%}"
            "td,th{border:1px solid #ccc;padding:.3em .5em}</style></head>"
            f"<body>{body}</body></html>",
            encoding="utf-8",
        )

    else:  # markdown
        out = job_dir / f"{basename}.md"
        out.write_text(md_text, encoding="utf-8")

    report("done", 100, f"Gotowe! → {out.name}")
    return str(out)



# ─── Internal helpers ─────────────────────────────────────────────────────────

def _extract_epub(epub_path: Path, images_dir: Path) -> tuple[str, dict]:
    """Extract EPUB to Markdown, preserving all images.
    Returns (markdown_text, {filename: image_bytes}).
    """
    import ebooklib
    import ebooklib.epub as epub_in
    from bs4 import BeautifulSoup, Comment
    from markdownify import markdownify as md_conv

    book = epub_in.read_epub(str(epub_path))
    collected_images = {}

    # First pass: extract ALL images and save them
    for item in book.get_items_of_type(ebooklib.ITEM_IMAGE):
        fname = Path(item.file_name).name
        collected_images[fname] = item.get_content()
        # Also save to disk so markdown can reference them
        (images_dir / fname).write_bytes(item.get_content())

    # Second pass: extract text, rewriting image src to our path
    parts = []
    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            html = item.get_content().decode("utf-8", errors="ignore")
            html = re.sub(r"<\?xml[^>]*\?>", "", html)
            html = re.sub(r"<!DOCTYPE[^>]*>", "", html, flags=re.IGNORECASE)
            soup = BeautifulSoup(html, "html.parser")
            for c in soup.find_all(string=lambda t: isinstance(t, Comment)):
                c.extract()
            # Fix image paths to use our local filenames
            for img_tag in soup.find_all("img"):
                src = img_tag.get("src", "")
                fname = Path(src).name
                if fname in collected_images:
                    img_tag["src"] = f"images/{fname}"
            parts.append(md_conv(str(soup), heading_style="ATX", escape_asterisks=False))
    return "\n\n".join(parts), collected_images


def _fitz_extract_text(pdf: Path, cb) -> str:
    """Local fallback: extract text layer from PDF using fitz (PyMuPDF).
    Works for PDFs with embedded text layer. Does NOT do OCR on scanned images.
    """
    try:
        import fitz
    except ImportError:
        raise RuntimeError(
            "Brak zainstalowanego PyMuPDF.\n"
            "Uruchom: pip install PyMuPDF"
        )

    doc = fitz.open(str(pdf))
    total = len(doc)
    if cb:
        cb("ocr", 5, f"Lokalna ekstrakcja tekstu — {total} stron…")

    pages = []
    for i in range(total):
        text = doc[i].get_text().strip()
        if text:
            pages.append(text)
        if cb and (i + 1) % 20 == 0:
            pct = 5 + int(i / total * 90)
            cb("ocr", pct, f"Ekstrakcja tekstu: {i+1}/{total}…")
    doc.close()

    if not pages:
        raise RuntimeError(
            "PDF nie zawiera warstwy tekstowej (skan).\n"
            "Do przetworzenia skanów PDF wymagany jest klucz Gemini API.\n"
            "Wpisz go w Ustawieniach (⚙️) → Klucz API."
        )

    return "\n\n".join(pages)


def _extract_cover(src: Path, book):
    ext = src.suffix.lower()
    if ext == ".pdf":
        try:
            import fitz
            doc = fitz.open(str(src))
            if len(doc) > 0:
                pix = doc.load_page(0).get_pixmap(matrix=fitz.Matrix(3.0, 3.0))
                book.set_cover("cover.png", pix.tobytes("png"))
        except Exception:
            pass
    elif ext == ".epub":
        try:
            import ebooklib
            import ebooklib.epub as epub_in
            in_book = epub_in.read_epub(str(src))
            for it in in_book.get_items_of_type(ebooklib.ITEM_IMAGE):
                if "cover" in it.id.lower() or "cover" in it.file_name.lower():
                    e = Path(it.file_name).suffix or ".jpg"
                    book.set_cover(f"cover{e}", it.get_content())
                    break
        except Exception:
            pass


def _create_epub(md_text: str, output_path: str, title: str, book):
    chapters_raw = re.split(r"(?=^#{1,2}\s)", md_text, flags=re.MULTILINE)

    css = epub.EpubItem(
        uid="style", file_name="style/default.css", media_type="text/css",
        content=b"body{font-family:Georgia,serif;line-height:1.7;margin:1em;color:#222}"
                b"h1{font-size:1.8em;margin-top:2em;border-bottom:1px solid #ccc;padding-bottom:.3em}"
                b"h2{font-size:1.4em;margin-top:1.5em}h3{font-size:1.2em}"
                b"table{border-collapse:collapse;width:100%;margin:1em 0}"
                b"td,th{border:1px solid #ccc;padding:.3em .5em}"
                b"blockquote{border-left:3px solid #ccc;margin-left:0;padding-left:1em;color:#555}"
                b"p{margin:.5em 0}",
    )
    book.add_item(css)

    conv = md_lib.Markdown(extensions=["tables", "smarty"])
    spine = ["nav"]
    toc = []

    for i, ch_md in enumerate(chapters_raw):
        if not ch_md.strip():
            continue
        m = re.match(r"^(#{1,3})\s+(.+)", ch_md.strip())
        lvl = len(m.group(1)) if m else 99
        ch_title = re.sub(r"<[^>]+>", "", m.group(2)).strip() if m else f"Część {i+1}"
        ch_title = ch_title or f"Część {i+1}"

        conv.reset()
        html = conv.convert(ch_md)
        ch = epub.EpubHtml(title=ch_title[:80], file_name=f"ch_{i:03d}.xhtml", lang="pl")
        ch.content = f"<html><body>{html}</body></html>"
        ch.add_item(css)
        book.add_item(ch)
        spine.append(ch)
        if lvl <= 2:
            toc.append(ch)

    book.toc = toc
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = spine
    epub.write_epub(output_path, book, {})


# ─── Pipeline Orchestrator ────────────────────────────────────────────────────

def translate_epub(
    input_epub: str,
    lang_from: str = "angielski",
    lang_to: str = "polski",
    verify_translation: bool = False,
    translate_images: bool = False,
    progress_callback: Optional[Callable[[str, int, str], None]] = None,
) -> str:
    """Translate an existing EPUB file using AI.

    Takes an EPUB, extracts its text, runs AI translation, and produces a new
    translated EPUB in the same job directory. Does NOT do OCR/conversion.

    Returns:
        Absolute path to the translated EPUB file.
    """
    src = Path(input_epub)

    def report(stage: str, pct: int, msg: str):
        if progress_callback:
            progress_callback(stage, pct, msg)

    job_dir = WORKSPACE_DIR / "jobs" / uuid.uuid4().hex[:8]
    job_dir.mkdir(parents=True, exist_ok=True)
    images_dir = job_dir / "images"
    images_dir.mkdir(exist_ok=True)

    report("extract", 5, "Wypakowuję EPUB…")
    md_text, collected_images = _extract_epub(src, images_dir)
    report("extract", 20, f"Ekstrakcja zakończona ({len(collected_images)} ilustracji)")

    if not corrector.is_api_available():
        raise RuntimeError(
            "⚠️ BRAK KLUCZA API!\n"
            "Wejdź w Ustawienia (⚙️) i skonfiguruj klucz AI."
        )

    md_original = md_text
    report("correction", 0, "Tłumaczenie AI — inicjalizacja…")

    def on_llm(cur, tot, msg):
        pct = int(cur / tot * 100) if tot else 0
        report("correction", pct, f"Tłumaczenie ({cur}/{tot})")

    # Checkpoint sidecar for translate_epub
    _ckpt_suffix = f"_{(lang_from or 'auto')[:3]}_{lang_to[:3]}".lower()
    _ckpt_path   = str(src.with_name(src.stem + _ckpt_suffix + ".rebook_progress.json"))

    md_text = corrector.correct_markdown(
        md_text,
        use_translate=True,
        lang_to=lang_to,
        lang_from=lang_from,
        progress_callback=on_llm,
        checkpoint_path=_ckpt_path,
    )
    md_text = corrector._deduplicate_markdown(md_text)
    report("correction", 100, "Tłumaczenie zakończone")

    if verify_translation:
        report("verification", 0, "🔍 Weryfikacja tłumaczenia…")

        def on_verify(cur, tot, msg):
            pct = int(cur / tot * 100) if tot else 0
            report("verification", pct, msg)

        md_text = corrector.verify_translation(
            original_markdown=md_original,
            translated_markdown=md_text,
            lang_from=lang_from or "angielski",
            lang_to=lang_to,
            progress_callback=on_verify,
        )
        report("verification", 100, "✅ Weryfikacja zakończona")

    translated_images = {}
    if translate_images and collected_images:
        report("images", 0, "🎨 Tłumaczenie ilustracji…")

        def on_img(cur, tot, msg):
            pct = int(cur / tot * 100) if tot else 0
            report("images", pct, msg)

        translated_images = image_translator.process_book_images(
            images=collected_images,
            lang_from=lang_from or "angielski",
            lang_to=lang_to,
            progress_callback=on_img,
        )

    lang_suffix = lang_to.strip().lower()[:3]
    basename = f"{src.stem}_{lang_suffix}"
    out = job_dir / f"{basename}.epub"

    _lang_codes = {
        "polski": "pl", "angielski": "en", "english": "en",
        "niemiecki": "de", "francuski": "fr", "hiszpański": "es",
        "włoski": "it", "portugalski": "pt", "rosyjski": "ru",
    }
    epub_lang = _lang_codes.get(lang_to.strip().lower(), "pl")
    epub_title = f"{src.stem} [{lang_to}]"

    book = epub.EpubBook()
    book.set_identifier(f"rebook-{uuid.uuid4().hex[:8]}")
    book.set_title(epub_title)
    book.set_language(epub_lang)
    _extract_cover(src, book)

    for img_name, img_data in collected_images.items():
        mime = "image/png" if img_name.endswith(".png") else "image/jpeg"
        img_item = epub.EpubImage()
        img_item.file_name = f"images/{img_name}"
        img_item.media_type = mime
        img_item.content = img_data
        book.add_item(img_item)
        if img_name in translated_images:
            tr_item = epub.EpubImage()
            tr_item.file_name = f"images_translated/{img_name}"
            tr_item.media_type = "image/png"
            tr_item.content = translated_images[img_name]
            book.add_item(tr_item)

    if translated_images:
        for img_name in translated_images:
            md_text = md_text.replace(f"images/{img_name}", f"images_translated/{img_name}")

    _create_epub(md_text, str(out), basename, book)
    report("done", 100, f"Gotowe! → {out.name}")
    return str(out)


class PipelineConfig:
    """Configuration for a multi-step pipeline run."""

    def __init__(
        self,
        # Step toggles
        do_convert: bool = True,
        do_translate: bool = False,
        do_audiobook: bool = False,
        # Convert options
        output_format: str = "epub",
        ai_correct: bool = False,
        # Translate options
        lang_from: str = "angielski",
        lang_to: str = "polski",
        verify_translation: bool = False,
        translate_images: bool = False,
        # Audiobook options
        tts_voice: str = "pl-PL-MarekNeural",
        # Input EPUB (used when do_convert=False and starting from existing EPUB)
        input_epub: Optional[str] = None,
    ):
        self.do_convert = do_convert
        self.do_translate = do_translate
        self.do_audiobook = do_audiobook
        self.output_format = output_format
        self.ai_correct = ai_correct
        self.lang_from = lang_from
        self.lang_to = lang_to
        self.verify_translation = verify_translation
        self.translate_images = translate_images
        self.tts_voice = tts_voice
        self.input_epub = input_epub


class PipelineResult:
    """Result of a pipeline run."""

    def __init__(self):
        self.epub_path: Optional[str] = None          # final EPUB (after convert+translate)
        self.translated_epub_path: Optional[str] = None
        self.audiobook_dir: Optional[str] = None


def run_pipeline(
    source_path: str,
    config: PipelineConfig,
    progress_callback: Optional[Callable[[str, int, str], None]] = None,
    tts_engine=None,
) -> PipelineResult:
    """Run a multi-step pipeline: convert → translate → audiobook.

    Each step is optional and controlled by PipelineConfig flags.
    Steps run in order; each step's output becomes the next step's input.

    Args:
        source_path: Input file (PDF, EPUB, MD) or existing EPUB path.
        config: Pipeline configuration (which steps to run and their options).
        progress_callback: ``fn(stage, percent, message)`` unified progress hook.
        tts_engine: Optional TtsEngine instance (needed for do_audiobook=True).

    Returns:
        PipelineResult with paths to produced files.
    """
    result = PipelineResult()
    current_epub: Optional[str] = config.input_epub  # may be None if starting from source

    def report(stage: str, pct: int, msg: str):
        if progress_callback:
            progress_callback(stage, pct, msg)

    # ── Step 1: Convert to EPUB ───────────────────────────────────────────────
    if config.do_convert:
        report("pipeline", 0, "📄 Krok 1/3: Konwersja do EPUB…")
        current_epub = convert_file(
            input_path=source_path,
            output_format="epub",
            use_llm=config.ai_correct,
            use_translate=False,  # translation is a separate step
            lang_from=config.lang_from,
            lang_to=config.lang_to,
            progress_callback=progress_callback,
        )
        result.epub_path = current_epub
        report("pipeline", 33, f"✅ Krok 1 gotowy: {Path(current_epub).name}")
    else:
        # No conversion — use source file directly as EPUB
        current_epub = source_path if source_path.endswith(".epub") else config.input_epub
        result.epub_path = current_epub

    if current_epub is None:
        raise ValueError("Brak pliku EPUB — zaznacz krok 'Konwersja' lub wybierz istniejący EPUB")

    # ── Step 2: Translate EPUB ────────────────────────────────────────────────
    if config.do_translate:
        report("pipeline", 33, "🌐 Krok 2/3: Tłumaczenie AI…")
        translated = translate_epub(
            input_epub=current_epub,
            lang_from=config.lang_from,
            lang_to=config.lang_to,
            verify_translation=config.verify_translation,
            translate_images=config.translate_images,
            progress_callback=progress_callback,
        )
        result.translated_epub_path = translated
        result.epub_path = translated
        current_epub = translated
        report("pipeline", 66, f"✅ Krok 2 gotowy: {Path(translated).name}")

    # ── Step 3: Generate Audiobook ────────────────────────────────────────────
    if config.do_audiobook:
        if tts_engine is None:
            raise RuntimeError("TTS engine nie jest dostępny")
        report("pipeline", 66, "🎧 Krok 3/3: Generowanie audiobooka…")

        epub_file = Path(current_epub)
        out_dir = epub_file.parent / f"{epub_file.stem}_audiobook"

        # Read EPUB text for TTS using the same extraction helper
        images_dir = epub_file.parent / "images_tmp"
        images_dir.mkdir(exist_ok=True)
        md_text, _ = _extract_epub(epub_file, images_dir)

        def on_tts(cur, tot, msg):
            pct = 66 + int((cur / tot if tot else 0) * 33)
            report("pipeline", pct, msg)

        files = tts_engine.generate_audiobook(
            text=md_text,
            voice=config.tts_voice,
            output_dir=out_dir,
            on_progress=on_tts,
        )
        result.audiobook_dir = str(out_dir)
        report("pipeline", 100, f"✅ Gotowe! {len(files)} rozdziałów MP3 → {out_dir.name}")

    return result
