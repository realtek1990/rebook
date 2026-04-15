#!/usr/bin/env python3
"""Re-process bad chapters in translated EPUB using Gemma 4."""
import json, os, sys, time, base64, re, zipfile, shutil
import urllib.request
import fitz
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Config ──
EPUB_PATH = "/Users/mac/.pdf2epub-app/jobs/8b7c7f31/DaVinci_Resolve_20_Reference_Manual_pol.epub"
PDF_PATH = "/Users/mac/Downloads/DaVinci_Resolve_20_Reference_Manual.pdf"
BAD_CHAPTERS = json.load(open("/tmp/rebook_bad_chapters.json"))
OUTPUT_EPUB = "/Users/mac/.pdf2epub-app/jobs/8b7c7f31/DaVinci_Resolve_20_Reference_Manual_pol_fixed.epub"

config = json.load(open(os.path.expanduser("~/.pdf2epub-app/config.json")))
API_KEY = config.get("api_key", "")
MODEL = "gemma-4-31b-it"
WORKERS = 5  # Conservative to avoid rate limits
DPI = 200

# ── Gemma thinking strip ──
META_KEYWORDS = {"input:", "task:", "constraint:", "observation:", "rules:",
                 "output:", "note:", "header:", "section:", "bullet",
                 "the prompt", "the user", "the image",
                 "the source", "the text in the image", "the text is",
                 "the translation", "since it", "since the", "already in",
                 "wait,", "let me", "i will", "i should", "let's", "ensure",
                 "however", "in summary"}

def strip_gemma_thinking(raw):
    lines = raw.split("\n")
    last_meta = -1
    for i, line in enumerate(lines):
        s = line.strip().lower()
        if s.startswith(("*", "-")) and any(kw in s for kw in META_KEYWORDS):
            last_meta = i
    if last_meta < 0:
        return raw
    start = last_meta + 1
    while start < len(lines) and lines[start].strip() == "":
        start += 1
    if start >= len(lines):
        return raw
    cleaned = "\n".join(lines[start:])
    cleaned = re.sub(r"^    ", "", cleaned, flags=re.MULTILINE)
    # Secondary strip
    clean_lines = cleaned.split("\n")
    while clean_lines:
        s = clean_lines[0].strip().lower()
        if s == "":
            clean_lines.pop(0)
        elif s.startswith(("*", "-")) and any(kw in s for kw in META_KEYWORDS):
            clean_lines.pop(0)
        else:
            break
    cleaned = "\n".join(clean_lines)
    return cleaned if len(cleaned.strip()) > 20 else raw

# ── OCR call ──
PROMPT = """You are an OCR + translation engine. Extract ALL text from this scanned book page and translate it to polski.

RULES:
- Output ONLY the translated text in polski. No commentary, no explanations.
- Keep Markdown formatting: # headings, - lists, > quotes
- If the page is only an illustration with no text, output exactly: {{IMAGE:strona}}
- If illustration has captions/labels, extract and translate them: {{IMAGE_TEXT:strona}}\\n[translated text]
- Do NOT leave any text in the original language (except proper names, software menu items like DaVinci Resolve)
- Use [illegible] for unreadable fragments
- Do NOT describe the image. Do NOT say 'Input:', 'Output:', 'Here is', etc.
- Start directly with the extracted/translated text"""

def call_gemma(image_b64, page_num):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"
    payload = {
        "systemInstruction": {"parts": [{"text": PROMPT}]},
        "contents": [{"parts": [
            {"text": "OCR this page."},
            {"inline_data": {"mime_type": "image/png", "data": image_b64}},
        ]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 8192},
    }
    for attempt in range(3):
        try:
            data = json.dumps(payload).encode()
            req = urllib.request.Request(url, data, {"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=180) as resp:
                result = json.loads(resp.read())
            if "error" in result:
                err = result["error"]
                if err.get("code") == 429:
                    wait = 15 * (attempt + 1)
                    print(f"  ⏱ Rate limit page {page_num}, waiting {wait}s...")
                    time.sleep(wait)
                    continue
                return None, f"API error {err.get('code')}: {err.get('message', '')[:80]}"
            text = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            text = strip_gemma_thinking(text)
            return text.strip(), None
        except Exception as e:
            if attempt < 2:
                time.sleep(5 * (attempt + 1))
            else:
                return None, str(e)[:100]
    return None, "max retries"

def text_to_xhtml(text, title=""):
    """Convert markdown text to simple XHTML chapter."""
    # Escape HTML
    html = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Convert markdown
    lines = html.split("\n")
    body_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# "):
            body_lines.append(f"<h1>{stripped[2:]}</h1>")
        elif stripped.startswith("## "):
            body_lines.append(f"<h2>{stripped[3:]}</h2>")
        elif stripped.startswith("### "):
            body_lines.append(f"<h3>{stripped[4:]}</h3>")
        elif stripped.startswith("- "):
            body_lines.append(f"<p>• {stripped[2:]}</p>")
        elif stripped == "":
            continue
        else:
            body_lines.append(f"<p>{stripped}</p>")
    
    body = "\n".join(body_lines)
    return f'''<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>{title}</title></head>
<body>
{body}
</body>
</html>'''

# ── Main ──
def main():
    print(f"📖 PDF: {PDF_PATH}")
    print(f"📚 EPUB: {EPUB_PATH}")
    print(f"🔧 Bad chapters: {len(BAD_CHAPTERS)}")
    print(f"🤖 Model: {MODEL}, Workers: {WORKERS}")
    print()

    # Step 1: Render bad pages from PDF
    print("📄 Rendering pages from PDF...")
    doc = fitz.open(PDF_PATH)
    mat = fitz.Matrix(DPI / 72, DPI / 72)
    
    page_images = {}  # ch_num -> b64 image
    for bc in BAD_CHAPTERS:
        ch = bc["ch"]
        if ch >= len(doc):
            print(f"  ⚠️ ch_{ch} beyond PDF pages ({len(doc)}), skipping")
            continue
        pix = doc[ch].get_pixmap(matrix=mat)
        page_images[ch] = base64.standard_b64encode(pix.tobytes("png")).decode()
    doc.close()
    print(f"  ✅ Rendered {len(page_images)} pages")

    # Step 2: Send to Gemma in parallel
    print(f"\n🚀 Sending {len(page_images)} pages to Gemma ({WORKERS} workers)...")
    results = {}  # ch_num -> text
    errors = []
    done = [0]

    def process(ch_num):
        text, err = call_gemma(page_images[ch_num], ch_num)
        done[0] += 1
        if err:
            print(f"  ❌ ch_{ch_num}: {err}")
            errors.append(ch_num)
        else:
            tlen = len(text) if text else 0
            print(f"  ✅ ch_{ch_num} ({tlen} chars) [{done[0]}/{len(page_images)}]")
        return ch_num, text

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(process, ch): ch for ch in page_images}
        for f in as_completed(futures):
            ch_num, text = f.result()
            if text and len(text.strip()) > 5:
                results[ch_num] = text

    print(f"\n📊 Results: {len(results)} OK, {len(errors)} errors")

    # Step 3: Rebuild EPUB with fixed chapters
    print(f"\n📦 Rebuilding EPUB...")
    z_in = zipfile.ZipFile(EPUB_PATH, "r")
    z_out = zipfile.ZipFile(OUTPUT_EPUB, "w", zipfile.ZIP_DEFLATED)

    replaced = 0
    for item in z_in.infolist():
        data = z_in.read(item.filename)
        
        # Check if this chapter needs replacing
        m = re.search(r'ch_(\d+)\.xhtml', item.filename)
        if m:
            ch_num = int(m.group(1))
            if ch_num in results:
                # Replace with new content
                new_xhtml = text_to_xhtml(results[ch_num])
                z_out.writestr(item, new_xhtml.encode("utf-8"))
                replaced += 1
                continue
        
        z_out.writestr(item, data)

    z_in.close()
    z_out.close()

    size_mb = os.path.getsize(OUTPUT_EPUB) / 1024 / 1024
    print(f"  ✅ {OUTPUT_EPUB}")
    print(f"  📏 {size_mb:.1f} MB, {replaced} chapters replaced")
    print(f"\n🎉 Gotowe!")

if __name__ == "__main__":
    main()
