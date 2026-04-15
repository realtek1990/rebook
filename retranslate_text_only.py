#!/usr/bin/env python3
"""
Retranslacja DaVinci Resolve Manual:
- OCR: fitz (lokalnie, za darmo, ~1 minuta)
- Tłumaczenie: Gemma 4 26B (tekst only, ~5-10s/req zamiast ~70s)
- 8 workerów równolegle
- 2 strony PDF na request
"""
import json, os, time, re, zipfile, tempfile, shutil
import urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
import fitz

PDF     = "/Users/mac/Downloads/DaVinci_Resolve_20_Reference_Manual.pdf"
EPUB_IN = "/Users/mac/.pdf2epub-app/jobs/8b7c7f31/DaVinci_Resolve_20_Reference_Manual_pol_final.epub"
ORIG_EP = "/Users/mac/.pdf2epub-app/jobs/8b7c7f31/DaVinci_Resolve_20_Reference_Manual_pol.epub"
OUTPUT  = "/Users/mac/.pdf2epub-app/jobs/8b7c7f31/DaVinci_Resolve_20_Reference_Manual_pol_v2.epub"
PROGRESS= "/Users/mac/.pdf2epub-app/jobs/8b7c7f31/retranslate_text_progress.json"

MODEL        = "gemma-4-26b-a4b-it"
WORKERS      = 8
PAGES_PER_REQ= 2
TIMEOUT      = 60

API_KEY = json.load(open(os.path.expanduser("~/.pdf2epub-app/config.json"))).get("api_key","")
BASE    = "https://generativelanguage.googleapis.com/v1beta"

SYSTEM = "You are a professional EN→PL translator of technical software manuals. Translate accurately, preserving structure. Output only translated Polish text."

def extract_pdf_text(pdf_path: str) -> dict:
    """Extract text from every PDF page using fitz. Returns {page_idx: text}."""
    doc = fitz.open(pdf_path)
    texts = {}
    for i in range(len(doc)):
        t = doc[i].get_text().strip()
        if t:
            texts[i] = t
    doc.close()
    return texts

def strip_cot(text: str) -> str:
    """Strip Gemma chain-of-thought from output."""
    # Remove thought tags
    text = re.sub(r'<thought>.*?</thought>', '', text, flags=re.DOTALL)
    # Find first line with Polish chars that isn't a CoT meta-line
    COT = re.compile(r'^\s*[\*\-]\s*\*?(Input|Task|Constraint|Source|Target|Heading|Paragraph|Note|Tip|Box|Translation|Polish|Step|Format|Rule|Check|Verify)\b', re.I)
    lines = text.split('\n')
    start = 0
    for i, l in enumerate(lines):
        if re.search(r'[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]', l) and not COT.match(l):
            start = i
            break
    result = '\n'.join(l for l in lines[start:] if not COT.match(l))
    return result.strip()

def call_translate(pages_text: dict, page_indices: list) -> str:
    """Send English text of pages to Gemma for translation."""
    combined = ""
    for p in page_indices:
        t = pages_text.get(p, "")
        if t:
            combined += f"\n\n--- Strona {p+1} ---\n{t}"
    if not combined.strip():
        return ""

    prompt = f"Translate the following pages of the DaVinci Resolve manual from English to Polish:\n{combined}\n\nOutput only the Polish translation."
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 8192},
    }
    url = f"{BASE}/models/{MODEL}:generateContent?key={API_KEY}"

    for attempt in range(4):
        try:
            req = urllib.request.Request(url, json.dumps(payload).encode(), {"Content-Type":"application/json"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                res = json.loads(r.read())
            raw = res["candidates"][0]["content"]["parts"][0]["text"]
            return strip_cot(raw)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep((2**attempt)*4)
                continue
            print(f"  ❌ HTTP {e.code} p{page_indices}")
            return ""
        except Exception as ex:
            if attempt < 3:
                time.sleep(3)
                continue
            print(f"  ❌ Error p{page_indices}: {ex}")
            return ""
    return ""

def text_to_xhtml(text: str) -> str:
    html = text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
    body = []
    for line in html.split("\n"):
        s = line.strip()
        if not s: continue
        if s.startswith("# "):     body.append(f"<h1>{s[2:]}</h1>")
        elif s.startswith("## "): body.append(f"<h2>{s[3:]}</h2>")
        elif s.startswith("- "):  body.append(f"<p>• {s[2:]}</p>")
        else:                      body.append(f"<p>{s}</p>")
    return ('<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml">'
            '<head><title></title></head><body>\n' + '\n'.join(body) + '\n</body></html>')

def main():
    # Step 1: Extract PDF text (free, ~30s)
    print("📄 Extracting PDF text via fitz (bezpłatnie)...")
    t0 = time.time()
    pages_text = extract_pdf_text(PDF)
    print(f"   ✅ {len(pages_text)} stron z tekstem ({time.time()-t0:.1f}s)")

    # Load progress
    progress = {}
    if os.path.exists(PROGRESS):
        progress = json.load(open(PROGRESS))
        print(f"▶️  Resuming: {len(progress)} batchy już gotowych")

    # Build batches
    total_pages = max(pages_text.keys()) + 1
    batches = []
    for i in range(0, total_pages, PAGES_PER_REQ):
        pages = list(range(i, min(i+PAGES_PER_REQ, total_pages)))
        bid = f"b{i:04d}"
        batches.append((bid, pages))

    pending = [(bid, pages) for bid, pages in batches if bid not in progress]
    print(f"📦 {len(batches)} batchy total, {len(pending)} do przetłumaczenia")
    print(f"🤖 Model: {MODEL} | {WORKERS} workerów | tekst only (bez obrazów)\n")

    # Step 2: Translate in parallel
    done = errors = 0
    t_start = time.time()

    def do_batch(args):
        bid, pages = args
        text = call_translate(pages_text, pages)
        return bid, pages, text

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(do_batch, x): x for x in pending}
        for future in as_completed(futures):
            bid, pages, text = future.result()
            if text and len(text) > 10:
                progress[bid] = {"pages": pages, "text": text}
                done += 1
            else:
                progress[bid] = {"pages": pages, "text": ""}
                errors += 1

            total_done = done + errors
            if total_done % 50 == 0:
                elapsed = time.time() - t_start
                rate = total_done / elapsed * 60
                eta = (len(pending) - total_done) / max(rate/60, 0.001)
                print(f"  [{total_done}/{len(pending)}] ✅{done} ❌{errors} | "
                      f"{rate:.1f}/min | ETA ~{eta/60:.1f}h")
                json.dump(progress, open(PROGRESS,"w"), ensure_ascii=False)

    json.dump(progress, open(PROGRESS,"w"), ensure_ascii=False)
    print(f"\n✅ Done: {done} | ❌ Errors: {errors}")

    # Step 3: Build EPUB
    print("\n📖 Budowanie EPUB...")
    z_in   = zipfile.ZipFile(EPUB_IN)
    z_orig = zipfile.ZipFile(ORIG_EP)

    xhtml_files = sorted(
        [n for n in z_in.namelist() if n.endswith(".xhtml") and "nav" not in n],
        key=lambda x: int(re.search(r"ch_(\d+)",x).group(1)) if re.search(r"ch_(\d+)",x) else 0
    )
    total_ch = len(xhtml_files)
    ratio = total_pages / max(total_ch, 1)

    # batch lookup by start page
    batch_text = {progress[bid]["pages"][0]: progress[bid]["text"]
                  for bid in progress if progress[bid].get("text")}

    fd, tmp = tempfile.mkstemp(suffix=".epub")
    os.close(fd)
    z_out = zipfile.ZipFile(tmp,"w",zipfile.ZIP_DEFLATED)

    replaced = kept = 0
    for i, xhtml_name in enumerate(xhtml_files):
        data = z_in.read(xhtml_name)
        pdf_est = int(i * ratio)
        pdf_aligned = (pdf_est // PAGES_PER_REQ) * PAGES_PER_REQ
        text = batch_text.get(pdf_aligned, "")
        if text and len(text) > 20:
            xhtml = text_to_xhtml(text)
            try:
                orig_c = z_orig.read(xhtml_name).decode("utf-8","ignore")
                imgs = re.findall(r'(?:<p[^>]*>\s*)?<img\b[^>]*/?>(?:\s*</p>)?', orig_c, re.DOTALL|re.I)
                if imgs:
                    xhtml = re.sub(r'(<body[^>]*>)', r'\1\n'+'\n'.join(imgs), xhtml, count=1)
            except: pass
            data = xhtml.encode("utf-8")
            replaced += 1
        else:
            kept += 1
        z_out.writestr(z_in.getinfo(xhtml_name), data)

    for item in z_in.infolist():
        if not item.filename.endswith(".xhtml") or "nav" in item.filename:
            z_out.writestr(item, z_in.read(item.filename))

    z_in.close(); z_orig.close(); z_out.close()
    shutil.move(tmp, OUTPUT)
    print(f"✅ Podmieniono {replaced} | Zachowano {kept}")
    print(f"📁 {OUTPUT} ({os.path.getsize(OUTPUT)//1024//1024} MB)")

if __name__ == "__main__":
    main()
