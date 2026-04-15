#!/usr/bin/env python3
"""
Retranslacja DaVinci Resolve Manual PL używając Gemma 4 26B.
- 2 strony PDF na request (jak oryginalny pipeline)
- 8 równoległych workerów
- Strip CoT z outputu
- Buduje nowy EPUB
"""
import json, os, time, base64, re, zipfile, tempfile, shutil
import urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import fitz

# ── CONFIG ────────────────────────────────────────────────────────────────────
PDF     = "/Users/mac/Downloads/DaVinci_Resolve_20_Reference_Manual.pdf"
EPUB_IN = "/Users/mac/.pdf2epub-app/jobs/8b7c7f31/DaVinci_Resolve_20_Reference_Manual_pol_final.epub"
ORIG_EP = "/Users/mac/.pdf2epub-app/jobs/8b7c7f31/DaVinci_Resolve_20_Reference_Manual_pol.epub"
OUTPUT  = "/Users/mac/.pdf2epub-app/jobs/8b7c7f31/DaVinci_Resolve_20_Reference_Manual_pol_v2.epub"
PROGRESS= "/Users/mac/.pdf2epub-app/jobs/8b7c7f31/retranslate_progress.json"

MODEL   = "gemma-4-26b-a4b-it"
DPI     = 120          # niższe DPI → szybszy upload
WORKERS = 8            # równolegle jak oryginalny pipeline
PAGES_PER_REQ = 2      # 2 strony PDF na wywołanie
TIMEOUT = 180          # sekundy

API_KEY = json.load(open(os.path.expanduser("~/.pdf2epub-app/config.json"))).get("api_key","")
BASE    = "https://generativelanguage.googleapis.com/v1beta"

SYSTEM_PROMPT = (
    "Translate scanned book pages to Polish. "
    "Output only the translated text with Markdown structure (# headings, - lists). "
    "For illustration-only pages output {{IMAGE:strona}}. "
    "For illustrations with captions output {{IMAGE_TEXT:strona}} then translated captions."
)

# ── STRIP GEMMA CoT ───────────────────────────────────────────────────────────
def strip_cot(text: str) -> str:
    """Remove Gemma chain-of-thought thinking from output."""
    # Remove <thought>...</thought> blocks
    text = re.sub(r'<thought>.*?</thought>', '', text, flags=re.DOTALL)
    text = re.sub(r'<channel>thought.*?<channel\|>', '', text, flags=re.DOTALL)

    lines = text.split('\n')
    # Find first line with Polish content (has Polish chars or is a Markdown heading)
    # Skip bullet points that are Gemma "thinking" meta-lines
    COT_PAT = re.compile(
        r'^\s*[\*\-]\s*\*?(Input|Task|Constraint|Heading \d|Paragraph \d|Box|List|Note|Tip|Translation|Polish|Output|Step|Format|Rule)',
        re.I
    )
    TRANSLATION_MARKER = re.compile(
        r'^\s*[\*\-]\s*\*?(?:Polish|Translation|Translated text)\*?\s*:', re.I
    )

    # Find where real content starts — after CoT block
    start_idx = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        # If line has Polish chars or is a proper heading → content starts here
        if re.search(r'[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]', stripped) and not COT_PAT.match(line):
            start_idx = i
            break
        # If it's a translation marker like "* Polish: ..."
        m = TRANSLATION_MARKER.match(line)
        if m:
            # Extract content after the colon
            rest = line.split(':', 1)[1].strip() if ':' in line else ''
            lines[i] = rest
            start_idx = i
            break

    result_lines = []
    for line in lines[start_idx:]:
        # Skip remaining CoT lines
        if COT_PAT.match(line):
            continue
        result_lines.append(line)

    result = '\n'.join(result_lines).strip()
    # Clean up markdown asterisks used as bold wrappers for field names
    result = re.sub(r'\*\*([\w\s]+):\*\*', r'\1:', result)
    return result


# ── RENDER & CALL ─────────────────────────────────────────────────────────────
def render_pages(doc, page_indices: list) -> list:
    mat = fitz.Matrix(DPI/72, DPI/72)
    imgs = []
    for p in page_indices:
        if p < len(doc):
            pix = doc[p].get_pixmap(matrix=mat)
            imgs.append(base64.standard_b64encode(pix.tobytes("png")).decode())
    return imgs


def call_gemma(page_indices: list, imgs: list) -> tuple[str, str]:
    """Returns (raw_text, cleaned_text). Returns ('','') on failure."""
    parts = [{"inline_data": {"mime_type": "image/png", "data": img}} for img in imgs]
    parts.append({"text": f"Translate pages {page_indices[0]+1}-{page_indices[-1]+1}."})

    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 8192},
    }
    url = f"{BASE}/models/{MODEL}:generateContent?key={API_KEY}"

    for attempt in range(4):
        try:
            req = urllib.request.Request(
                url, json.dumps(payload).encode(), {"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                res = json.loads(r.read())
            raw = res.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            return raw, strip_cot(raw)
        except urllib.error.HTTPError as e:
            err = e.read().decode()[:200]
            if e.code == 429:
                wait = (2**attempt) * 5
                print(f"  ⏳ Rate limit (pages {page_indices}), czekam {wait}s...")
                time.sleep(wait)
                continue
            print(f"  ❌ HTTP {e.code} pages {page_indices}: {err[:80]}")
            return "", ""
        except Exception as ex:
            if attempt < 3:
                time.sleep(5)
                continue
            print(f"  ❌ Timeout/Error pages {page_indices}: {ex}")
            return "", ""
    return "", ""


# ── EPUB UTILS ────────────────────────────────────────────────────────────────
def text_to_xhtml(text: str, title: str = "") -> str:
    html = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Restore EPUB image placeholders (not escaped)
    html = html.replace("&lt;img", "<img").replace("/&gt;", "/>").replace("&gt;", ">")
    body = []
    for line in html.split("\n"):
        s = line.strip()
        if not s:
            continue
        if s.startswith("# "):      body.append(f"<h1>{s[2:]}</h1>")
        elif s.startswith("## "):   body.append(f"<h2>{s[3:]}</h2>")
        elif s.startswith("### "): body.append(f"<h3>{s[4:]}</h3>")
        elif s.startswith("- "):   body.append(f"<p>• {s[2:]}</p>")
        else:                       body.append(f"<p>{s}</p>")
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml">'
        f'<head><title>{title}</title></head>'
        '<body>\n' + '\n'.join(body) + '\n</body></html>'
    )


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    doc = fitz.open(PDF)
    total_pdf = len(doc)
    print(f"📄 PDF: {total_pdf} stron")
    print(f"🤖 Model: {MODEL} | {DPI}dpi | {WORKERS} workerów | {PAGES_PER_REQ} str/req")

    # Load progress (resume support)
    progress = {}
    if os.path.exists(PROGRESS):
        progress = json.load(open(PROGRESS))
        print(f"▶️  Wznawianie od poprzedniej sesji ({len(progress)} batch gotowych)")

    # Build batch list: [(batch_id, [page0, page1]), ...]
    batches = []
    for i in range(0, total_pdf, PAGES_PER_REQ):
        pages = list(range(i, min(i + PAGES_PER_REQ, total_pdf)))
        batch_id = f"batch_{i:04d}"
        batches.append((batch_id, pages))

    total_batches = len(batches)
    pending = [(bid, pages) for bid, pages in batches if bid not in progress]
    print(f"📦 Batchy: {total_batches} total, {len(pending)} do zrobienia\n")

    # Render images for pending batches
    print("🖼️  Renderowanie obrazów...")
    batch_imgs = {}
    for bid, pages in pending:
        batch_imgs[bid] = render_pages(doc, pages)
    doc.close()
    print(f"   ✅ {len(batch_imgs)} batchy wyrenderowanych\n")

    # Process in parallel
    done = skipped = errors = 0
    start_time = time.time()

    def process_batch(args):
        bid, pages = args
        imgs = batch_imgs.get(bid, [])
        if not imgs:
            return bid, pages, "", f"brak obrazu"
        raw, cleaned = call_gemma(pages, imgs)
        return bid, pages, cleaned, raw

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(process_batch, (bid, pages)): (bid, pages)
                   for bid, pages in pending}

        for future in as_completed(futures):
            bid, pages, cleaned, raw = future.result()
            if cleaned and len(cleaned) > 10:
                progress[bid] = {"pages": pages, "text": cleaned}
                done += 1
            else:
                progress[bid] = {"pages": pages, "text": ""}
                errors += 1

            # Save progress every 20 batches
            if (done + errors) % 20 == 0:
                json.dump(progress, open(PROGRESS, "w"), ensure_ascii=False)
                elapsed = time.time() - start_time
                rate = (done+errors) / elapsed * 60
                eta = (len(pending) - done - errors) / max(rate, 0.01)
                print(f"  [{done+errors}/{len(pending)}] ✅{done} ❌{errors} | "
                      f"{rate:.1f} batch/min | ETA ~{eta:.0f}min")

    json.dump(progress, open(PROGRESS, "w"), ensure_ascii=False)
    print(f"\n✅ Gotowe: {done} | ❌ Błędy: {errors}")

    # ── Build new EPUB ────────────────────────────────────────────────────────
    print("\n📦 Budowanie nowego EPUB...")
    z_in   = zipfile.ZipFile(EPUB_IN)
    z_orig = zipfile.ZipFile(ORIG_EP)

    # Map batch_id → text
    batch_by_start = {progress[bid]["pages"][0]: progress[bid]["text"]
                      for bid in progress if progress[bid].get("text")}

    xhtml_files = sorted(
        [n for n in z_in.namelist() if n.endswith(".xhtml") and "nav" not in n],
        key=lambda x: int(re.search(r"ch_(\d+)", x).group(1))
        if re.search(r"ch_(\d+)", x) else 0
    )
    total_ch = len(xhtml_files)
    total_pdf_pages = sum(len(v["pages"]) for v in progress.values())
    ratio = total_pdf_pages / max(total_ch, 1)

    fd, tmp = tempfile.mkstemp(suffix=".epub")
    os.close(fd)
    z_out = zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED)

    replaced = kept = 0
    for i, xhtml_name in enumerate(xhtml_files):
        data = z_in.read(xhtml_name)
        ch_num = int(re.search(r"ch_(\d+)", xhtml_name).group(1)) if re.search(r"ch_(\d+)", xhtml_name) else i

        # Find which batch covers this chapter (linear mapping)
        pdf_page_est = int(i * ratio)
        pdf_page_est = (pdf_page_est // PAGES_PER_REQ) * PAGES_PER_REQ  # align to batch
        text = batch_by_start.get(pdf_page_est, "")

        if text and len(text) > 20:
            xhtml = text_to_xhtml(text, title=f"Część {ch_num}")
            # Restore original images
            try:
                orig_c = z_orig.read(xhtml_name).decode("utf-8", "ignore")
                imgs = re.findall(r'(?:<p[^>]*>\s*)?<img\b[^>]*/?>(?:\s*</p>)?',
                                  orig_c, re.DOTALL|re.I)
                if imgs:
                    xhtml = re.sub(r'(<body[^>]*>)',
                                   r'\1\n' + '\n'.join(imgs), xhtml, count=1)
            except:
                pass
            data = xhtml.encode("utf-8")
            replaced += 1
        else:
            kept += 1

        z_out.writestr(z_in.getinfo(xhtml_name), data)

    # Copy all non-xhtml files
    for item in z_in.infolist():
        if not item.filename.endswith(".xhtml") or "nav" in item.filename:
            z_out.writestr(item, z_in.read(item.filename))

    z_in.close(); z_orig.close(); z_out.close()
    shutil.move(tmp, OUTPUT)

    size = os.path.getsize(OUTPUT) // 1024 // 1024
    print(f"✅ Podmieniono: {replaced} rozdziałów")
    print(f"   Zachowano:   {kept} rozdziałów (brak tłumaczenia)")
    print(f"   Plik: {OUTPUT} ({size} MB)")


if __name__ == "__main__":
    main()
