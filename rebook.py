#!/usr/bin/env python3
"""
ReBook — AI-powered book translator & OCR corrector.
Converts PDF/EPUB -> Markdown -> AI -> polished EPUB.

Supports: Google Gemini (default), OpenAI, Mistral, Grok (xAI),
          and any OpenAI-compatible API (Ollama, Together, etc.)

Requirements:
  pip install -r requirements.txt
  Set your API key in .env (see .env.example)

Usage:
  python3 rebook.py book.epub output.epub --mode translate --lang-from en --lang-to pl
  python3 rebook.py scan.pdf output.epub --mode correct
  python3 rebook.py book.epub out.epub --mode translate --provider openai --model gpt-4o
"""
import argparse
import sys
import os
import json
import urllib.request
import urllib.error
import time
import subprocess
import threading
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import re

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import markdown
except ImportError:
    sys.exit("Error: Missing 'markdown' library. Install with: pip install Markdown")

try:
    import ebooklib
    import ebooklib.epub as epub
except ImportError:
    sys.exit("Error: Missing 'ebooklib'. Install with: pip install EbookLib")

# ─── Constants ───────────────────────────────────────────────────────────────

BLOCK_SIZE = 5000
print_lock = threading.Lock()

LANG_NAMES = {
    "pl": "Polish", "en": "English", "de": "German", "fr": "French",
    "es": "Spanish", "it": "Italian", "pt": "Portuguese", "nl": "Dutch",
    "cs": "Czech", "sk": "Slovak", "uk": "Ukrainian", "ru": "Russian",
    "ja": "Japanese", "ko": "Korean", "zh": "Chinese", "ar": "Arabic",
    "tr": "Turkish", "sv": "Swedish", "da": "Danish", "no": "Norwegian",
    "fi": "Finnish", "hu": "Hungarian", "ro": "Romanian", "bg": "Bulgarian",
    "hr": "Croatian", "el": "Greek", "he": "Hebrew", "th": "Thai",
    "vi": "Vietnamese", "id": "Indonesian", "ms": "Malay", "hi": "Hindi",
}

def log(msg):
    with print_lock:
        print(msg, flush=True)

# ─── Prompts (English-based, language-agnostic) ─────────────────────────────

def get_system_prompt(mode, lang_to, lang_from):
    lang_to_name = LANG_NAMES.get(lang_to, lang_to)
    lang_from_name = LANG_NAMES.get(lang_from, lang_from) if lang_from else "the source language"

    if mode == "translate":
        return f"""You are a professional book translator. Translate the following text from {lang_from_name} into {lang_to_name}.

Rules:
1. Translate in a natural, literary style — maintain the highest grammatical correctness and the author's original context.
2. Translate ABSOLUTELY EVERYTHING into {lang_to_name} — including titles, headings, quotes, captions. Leave nothing in the source language.
3. PRESERVE Markdown formatting (headings #, bold **, lists -, blockquotes >). Do not alter their syntax.
4. HEADINGS (lines starting with #): A heading should be a SHORT title only (max 1-2 sentences). If a long paragraph follows #, convert it to bold text (**text**) instead.
5. CLEAN ARTIFACTS: Remove any technical junk — XML declarations (<?xml ...?>), HTML tags (<div>, <span>, <p>), DOCTYPE, HTML entities (&amp; &nbsp; &#xA0;) — leave only clean text.
6. PRESERVE PARAGRAPH STRUCTURE: Keep the exact same paragraph breaks as in the source. Do NOT insert extra blank lines between sentences belonging to the same block.
7. Return ONLY the translation result. Do NOT include introductions, comments, notes, or sentences like "Here is the translation:" or "I preserved the formatting"."""
    else:
        return """You are an expert in correcting OCR-scanned text. Your only task is to fix errors from scanning and text recognition (OCR).

Rules:
1. Merge split words (e.g. "sep arated" -> "separated")
2. Remove random bold markers (** inside words or sentences that don't make sense)
3. Fix punctuation errors
4. Fix obvious OCR typos (e.g. "rn" instead of "m", "1" instead of "l")
5. CLEAN ARTIFACTS: Remove any XML/HTML tags (<div>, <span>, <?xml...?>, DOCTYPE, entities &amp; &nbsp;) — leave only clean text.
6. Do NOT change content, do NOT add anything, do NOT paraphrase
7. Preserve Markdown formatting (headings #, lists -, blockquotes >) if present
8. Return ONLY the corrected text, without comments or notes"""

# ─── LLM Providers ──────────────────────────────────────────────────────────

def call_gemini(url, api_key, model, system_prompt, text, timeout=600):
    """Google Gemini API (native)."""
    full_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": system_prompt + "\n\n" + text}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 8192}
    }).encode("utf-8")

    req = urllib.request.Request(full_url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    if "candidates" in result and result["candidates"]:
        content = result["candidates"][0]["content"]["parts"][0]["text"]
        tokens = result.get("usageMetadata", {}).get("totalTokenCount", 0)
        return content.strip(), tokens
    elif "promptFeedback" in result:
        raise RuntimeError(f"Safety filter: {result['promptFeedback']}")
    else:
        raise RuntimeError(f"No candidates in response: {json.dumps(result)[:200]}")


def call_openai_compatible(url, api_key, model, system_prompt, text, timeout=600):
    """OpenAI-compatible API (works with OpenAI, Mistral, Grok/xAI, Ollama, etc.)."""
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ],
        "temperature": 0.1,
        "max_tokens": 8192,
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    if "choices" in result:
        content = result["choices"][0]["message"]["content"]
        tokens = result.get("usage", {}).get("total_tokens", 0)
        return content.strip(), tokens
    else:
        raise RuntimeError(f"No choices in response: {json.dumps(result)[:200]}")


PROVIDERS = {
    "gemini": {
        "fn": call_gemini,
        "default_model": "gemini-3-flash-preview",
        "env_key": "GEMINI_API_KEY",
        "url": None,  # built into the function
    },
    "openai": {
        "fn": call_openai_compatible,
        "default_model": "gpt-4o-mini",
        "env_key": "OPENAI_API_KEY",
        "url": "https://api.openai.com/v1/chat/completions",
    },
    "mistral": {
        "fn": call_openai_compatible,
        "default_model": "magistral-medium-latest",
        "env_key": "MISTRAL_API_KEY",
        "url": "https://api.mistral.ai/v1/chat/completions",
    },
    "grok": {
        "fn": call_openai_compatible,
        "default_model": "grok-3-fast",
        "env_key": "XAI_API_KEY",
        "url": "https://api.x.ai/v1/chat/completions",
    },
    "custom": {
        "fn": call_openai_compatible,
        "default_model": "default",
        "env_key": "LLM_API_KEY",
        "url": None,  # must be set via LLM_BASE_URL
    },
}


def call_llm(block_idx, total, text, system_prompt, provider_name, retries=3):
    """Universal LLM caller with retries and rate-limit handling."""
    provider = PROVIDERS[provider_name]
    api_key = os.getenv(provider["env_key"])
    if not api_key:
        raise ValueError(f"API key '{provider['env_key']}' not set! Check your .env file.")

    model = os.getenv("LLM_MODEL", provider["default_model"])
    url = os.getenv("LLM_BASE_URL", provider["url"])
    call_fn = provider["fn"]

    for attempt in range(retries):
        t0 = time.time()
        try:
            content, tokens = call_fn(url, api_key, model, system_prompt, text)
            elapsed = time.time() - t0
            return block_idx, content, tokens, elapsed, True
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            elapsed = time.time() - t0
            log(f"    [!] Block {block_idx+1}: HTTP {e.code} ({elapsed:.0f}s, attempt {attempt+1}): {body[:200]}")
            if e.code == 429 and attempt < retries - 1:
                wait = 15 * (attempt + 1)
                log(f"        -> Rate limited. Waiting {wait}s...")
                time.sleep(wait)
                continue
        except Exception as e:
            elapsed = time.time() - t0
            log(f"    [!] Block {block_idx+1}: exception ({elapsed:.0f}s, attempt {attempt+1}): {e}")
            if attempt < retries - 1:
                time.sleep(5)
                continue

    log(f"    ❌ Block {block_idx+1}: FAILED after {retries} attempts. Using raw original.")
    return block_idx, text, 0, 0, False


# ─── Text Processing ────────────────────────────────────────────────────────

def split_to_blocks(md_text, block_size=BLOCK_SIZE):
    paragraphs = md_text.split('\n\n')
    blocks, current, current_len = [], [], 0
    for para in paragraphs:
        if current_len + len(para) > block_size and current:
            blocks.append('\n\n'.join(current))
            current, current_len = [para], len(para)
        else:
            current.append(para)
            current_len += len(para)
    if current:
        blocks.append('\n\n'.join(current))
    return blocks


# ─── EPUB Generation ────────────────────────────────────────────────────────

def generate_epub(md_text, out_path, epub_title, epub_author, epub_lang, cover_data=None, cover_ext='jpg'):
    log("\n[*] Generating EPUB...")

    book = epub.EpubBook()
    book.set_identifier('rebook-converted')
    book.set_title(epub_title)
    book.set_language(epub_lang)
    if epub_author:
        book.add_author(epub_author)
    if cover_data:
        book.set_cover(f"cover.{cover_ext}", cover_data)
        log(f"    📷 Cover added: cover.{cover_ext}")

    style = epub.EpubItem(uid="style", file_name="style/default.css", media_type="text/css",
        content=b"""
        body { font-family: Georgia, serif; line-height: 1.6; margin: 1em; }
        h1 { font-size: 1.8em; margin-top: 2em; page-break-before: always; }
        h2 { font-size: 1.4em; margin-top: 1.5em; }
        h3 { font-size: 1.2em; }
        table { border-collapse: collapse; width: 100%; margin: 1em 0; }
        td, th { border: 1px solid #ccc; padding: 0.3em 0.5em; }
        blockquote { border-left: 3px solid #ccc; margin-left: 0; padding-left: 1em; color: #555; }
        img { max-width: 100%; height: auto; }
        """)
    book.add_item(style)

    chapters_raw = re.split(r'(?=^#\s)', md_text, flags=re.MULTILINE)
    spine = ['cover', 'nav'] if cover_data else ['nav']
    toc_items = []
    md_converter = markdown.Markdown(extensions=['tables', 'smarty'])

    chapter_count = 0
    for chapter_md in chapters_raw:
        if not chapter_md.strip():
            continue
        chapter_count += 1
        title_match = re.match(r'^#\s+(.+)', chapter_md.strip())
        title = title_match.group(1).strip() if title_match else f"Part {chapter_count}"
        title = re.sub(r'<[^>]+>', '', title).strip()
        if len(title) > 100:
            title = title[:97] + '...'
        if not title:
            title = f"Part {chapter_count}"

        md_converter.reset()
        html_content = md_converter.convert(chapter_md)

        ch = epub.EpubHtml(title=title[:80], file_name=f'ch_{chapter_count:03d}.xhtml', lang=epub_lang)
        ch.content = f'<html><head><title>{title}</title></head><body>{html_content}</body></html>'
        ch.add_item(style)

        book.add_item(ch)
        spine.append(ch)
        toc_items.append(ch)

    book.toc = toc_items
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = spine

    epub.write_epub(str(out_path), book, {})
    log(f"    ✅ Saved {chapter_count} chapters: {out_path}")


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="ReBook — AI-powered book translator & OCR corrector. PDF/EPUB -> EPUB.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  %(prog)s book.epub output.epub --mode translate --lang-from en --lang-to pl
  %(prog)s scan.pdf output.epub --mode correct
  %(prog)s book.epub out.epub --provider mistral --model magistral-medium-latest
  %(prog)s book.epub out.epub --provider custom --base-url http://localhost:11434/v1/chat/completions"""
    )

    parser.add_argument("input_file", help="Input PDF or EPUB file")
    parser.add_argument("output_epub", help="Output EPUB file path")
    parser.add_argument("--mode", choices=["correct", "translate"], default="correct",
                        help="Mode: 'correct' for OCR fix, 'translate' for translation (default: correct)")
    parser.add_argument("--lang-to", default="pl", help="Target language code (default: pl)")
    parser.add_argument("--lang-from", default=None, help="Source language code (default: auto-detect)")
    parser.add_argument("--provider", choices=list(PROVIDERS.keys()), default="gemini",
                        help="LLM provider (default: gemini)")
    parser.add_argument("--model", default=None, help="Override model name for the chosen provider")
    parser.add_argument("--base-url", default=None, help="Custom API base URL (for 'custom' provider or overrides)")
    parser.add_argument("--workers", type=int, default=30, help="Parallel API threads (default: 30)")
    parser.add_argument("--title", default=None, help="EPUB title (default: inferred from filename)")
    parser.add_argument("--author", default=None, help="EPUB author")
    parser.add_argument("--marker-cmd", default="marker_single", help="Marker OCR command (default: marker_single)")
    parser.add_argument("--skip-marker", action="store_true", help="Skip Marker OCR for PDF (use raw text)")
    parser.add_argument("--md-file", default=None, help="Load pre-existing Markdown file directly")

    args = parser.parse_args()

    # Apply model/url overrides to environment
    if args.model:
        os.environ["LLM_MODEL"] = args.model
    if args.base_url:
        os.environ["LLM_BASE_URL"] = args.base_url

    in_path = Path(args.input_file).resolve()
    if not in_path.exists() and not args.md_file:
        sys.exit(f"❌ File not found: {in_path}")

    out_epub_path = Path(args.output_epub).resolve()
    book_title = args.title or in_path.stem
    system_prompt = get_system_prompt(args.mode, args.lang_to, args.lang_from)
    cover_data = None
    cover_ext = 'jpg'
    provider_name = args.provider

    provider_info = PROVIDERS[provider_name]
    model_display = os.getenv("LLM_MODEL", provider_info["default_model"])
    log(f"[*] ReBook — mode: {args.mode.upper()} | provider: {provider_name} | model: {model_display}")

    # ── Phase 1: Extract text ────────────────────────────────────────────────
    md_text = ""
    if args.md_file:
        log(f"[*] Loading Markdown: {args.md_file}")
        md_text = Path(args.md_file).read_text(encoding="utf-8")

    elif in_path.suffix.lower() == '.epub':
        log("[*] Phase 1: Extracting text from EPUB...")
        try:
            from bs4 import BeautifulSoup
            from markdownify import markdownify as mdFile
        except ImportError:
            sys.exit("❌ Missing modules: pip install beautifulsoup4 markdownify")

        epub_source = epub.read_epub(str(in_path))

        # Extract cover
        for item in epub_source.get_items():
            if item.get_type() == ebooklib.ITEM_IMAGE:
                fname = item.file_name.lower()
                if 'cover' in fname or (fname.endswith('.jpg') and len(item.get_content()) > 100000):
                    cover_data = item.get_content()
                    cover_ext = 'jpg' if fname.endswith(('.jpg', '.jpeg')) else 'png'
                    log(f"    📷 Cover found: {item.file_name} ({len(cover_data)//1024}KB)")
                    break

        # Extract text
        parts = []
        for item in epub_source.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                html = item.get_content().decode('utf-8', errors='ignore')
                soup = BeautifulSoup(html, 'html.parser')
                parts.append(mdFile(str(soup), heading_style="ATX", escape_asterisks=False))
        md_text = "\n\n".join(parts)
        log("    ✅ Extraction complete.")

    elif in_path.suffix.lower() == '.pdf':
        log("[*] Phase 1: Processing PDF...")

        # Extract cover from first page
        try:
            import fitz
            doc = fitz.open(str(in_path))
            if len(doc) > 0:
                pix = doc.load_page(0).get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
                cover_data = pix.tobytes("png")
                cover_ext = 'png'
                log(f"    📷 Cover extracted from page 1")
        except Exception:
            pass

        # Run Marker OCR
        if not args.skip_marker:
            output_dir = in_path.parent / "marker_temp_output"
            output_dir.mkdir(exist_ok=True)
            cmd = [args.marker_cmd, str(in_path), "--output_dir", str(output_dir)]
            log(f"    Running: {' '.join(cmd)}")
            try:
                subprocess.run(cmd, check=True)
                log("    ✅ OCR complete.")
            except FileNotFoundError:
                sys.exit(f"❌ Command '{args.marker_cmd}' not found. Make sure Marker is installed and in PATH.")
            except subprocess.CalledProcessError as e:
                sys.exit(f"❌ OCR failed with exit code: {e.returncode}")

            md_files = list(Path(output_dir).rglob("*.md"))
            if not md_files:
                sys.exit("❌ Marker produced no output!")
            md_text = md_files[0].read_text(encoding="utf-8")
    else:
        sys.exit(f"❌ Unsupported file type: {in_path.suffix}. Use .pdf or .epub")

    # ── Phase 2: AI Processing ───────────────────────────────────────────────
    blocks = split_to_blocks(md_text)
    total = len(blocks)
    log(f"\n[*] Phase 2: AI processing ({len(md_text):,} chars in {total} blocks, {args.workers} threads)")

    t_start = time.time()
    results = [None] * total
    total_tokens = 0
    done_count = 0
    errors = []

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(call_llm, i, total, block, system_prompt, provider_name): i
            for i, block in enumerate(blocks)
        }

        for future in as_completed(futures):
            idx, text, tok, elapsed, success = future.result()
            results[idx] = text
            total_tokens += tok
            done_count += 1
            if success:
                log(f"    ✅ Block {idx+1:03d}/{total} -> {elapsed:.0f}s ({tok} tokens) | {done_count}/{total}")
            else:
                log(f"    🚨 Block {idx+1:03d} FAILED | {done_count}/{total}")
                errors.append((idx, text))

    md_final = '\n\n'.join(r for r in results if r)
    elapsed_total = time.time() - t_start
    log(f"\n[*] Phase 2 complete in {elapsed_total/60:.1f} min | {total_tokens:,} tokens consumed")

    if errors:
        error_file = Path.cwd() / f"rebook_errors_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        error_file.write_text(
            "".join(f"=== Block {i+1} ===\n{t}\n\n" for i, t in errors),
            encoding="utf-8"
        )
        log(f"    ⚠️ {len(errors)} block(s) failed. See: {error_file}")

    # ── Phase 3: Generate EPUB ───────────────────────────────────────────────
    generate_epub(md_final, out_epub_path, book_title, args.author, args.lang_to, cover_data, cover_ext)
    log(f"\n🌟 Done! {args.mode.upper()} saved to: {out_epub_path.name}")


if __name__ == "__main__":
    main()
