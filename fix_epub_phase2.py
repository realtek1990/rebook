#!/usr/bin/env python3
import json, os, sys, time, base64, re, zipfile
import urllib.request
import fitz
from concurrent.futures import ThreadPoolExecutor, as_completed

# Make sure we load the updated corrector module
sys.path.insert(0, '/Users/mac/.gemini/antigravity/scratch/ReBook.app/Contents/Resources/app')
import importlib
import corrector as c
importlib.reload(c)

EPUB_PATH = "/Users/mac/.pdf2epub-app/jobs/8b7c7f31/DaVinci_Resolve_20_Reference_Manual_pol_fixed.epub"
PDF_PATH = "/Users/mac/Downloads/DaVinci_Resolve_20_Reference_Manual.pdf"
OUTPUT_EPUB = "/Users/mac/.pdf2epub-app/jobs/8b7c7f31/DaVinci_Resolve_20_Reference_Manual_pol_final.epub"

config = json.load(open(os.path.expanduser("~/.pdf2epub-app/config.json")))
API_KEY = config.get("api_key", "")
MODEL = "gemma-4-31b-it"
WORKERS = 5
DPI = 200

print("🔍 Odczyt wersji fixed i poszukiwanie schowanych problematycznych rozdziałów (thinking artifacts)...")
z = zipfile.ZipFile(EPUB_PATH, "r")
bad_chapters = []
for file in z.namelist():
    if not file.endswith('.xhtml') or 'nav' in file: continue
    content = z.read(file).decode('utf-8', errors='ignore')
    text = re.sub(r'<[^>]+>', '', content)
    
    # Nasza NOWA logika weryfikacji ze stripem "thinking"
    is_valid = c._verify_page_local(text, "polski")
    has_error_marker = '[BŁĄD' in text
    has_prompt = 'OCR engine' in text or 'translation engine' in text
    
    if not is_valid or has_error_marker or has_prompt:
        m = re.search(r'ch_(\d+)', file)
        if m:
            ch_num = int(m.group(1))
            bad_chapters.append(ch_num)
z.close()

print(f"🔧 Zidentyfikowano {len(bad_chapters)} rozdziałów do powtórki.")
if not bad_chapters:
    print("✅ Czysto. Wychodzę.")
    import shutil
    shutil.copy2(EPUB_PATH, OUTPUT_EPUB)
    sys.exit(0)

print(f"📄 Renderowanie {len(bad_chapters)} stron z PDF...")
doc = fitz.open(PDF_PATH)
mat = fitz.Matrix(DPI / 72, DPI / 72)
page_images = {}
for ch in bad_chapters:
    if ch < len(doc):
        pix = doc[ch].get_pixmap(matrix=mat)
        page_images[ch] = base64.standard_b64encode(pix.tobytes("png")).decode()
doc.close()

print(f"\n🚀 Wysyłanie {len(page_images)} stron do Gemmy ({WORKERS} workers na 4_s scheduler)...")
results = {}
errors = []
done = [0]

import threading
lock = threading.Lock()
rate_lock = threading.Lock()
last_call = [0.0]

def process(ch_num):
    for attempt in range(3):
        with rate_lock:
            now = time.time()
            elapsed = now - last_call[0]
            if elapsed < 4.0:
                time.sleep(4.0 - elapsed)
            last_call[0] = time.time()
            
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"
            prompt = """You are an OCR + translation engine. Extract ALL text from this scanned book page and translate it to polski.

RULES:
- Output ONLY the translated text in polski. No commentary, no explanations.
- Keep Markdown formatting: # headings, - lists, > quotes
- If the page is only an illustration with no text, output exactly: {{IMAGE:strona}}
- If illustration has captions/labels, extract and translate them: {{IMAGE_TEXT:strona}}\n[translated text]
- Do NOT describe the image. Start directly with the extracted/translated text"""

            payload = {
                "systemInstruction": {"parts": [{"text": prompt}]},
                "contents": [{"parts": [
                    {"text": "OCR this page."},
                    {"inline_data": {"mime_type": "image/png", "data": page_images[ch_num]}},
                ]}],
                "generationConfig": {"temperature": 0.0, "maxOutputTokens": 8192},
            }
            req = urllib.request.Request(url, json.dumps(payload).encode(), {"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=180) as resp:
                result = json.loads(resp.read())
            
            text = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            
            # Post-processed przez nową obostrzoną funkcję:
            text = c._strip_gemma_thinking(text)
            
            with lock:
                done[0] += 1
                tlen = len(text) if text else 0
                print(f"  ✅ ch_{ch_num} ({tlen} znaków) [{done[0]}/{len(page_images)}]")
            return ch_num, text.strip()
        except Exception as e:
            msg = str(e).lower()
            if "429" in msg or "timed out" in msg:
                wait = (2 ** attempt) * 5
                time.sleep(wait)
                continue
            with lock:
                done[0] += 1
                print(f"  ❌ ch_{ch_num}: {e} [{done[0]}/{len(page_images)}]")
            return ch_num, None
    with lock:
        done[0] += 1
        print(f"  ❌ ch_{ch_num}: Timeout/Limit po 3 próbach [{done[0]}/{len(page_images)}]")
    return ch_num, None

with ThreadPoolExecutor(max_workers=WORKERS) as pool:
    futures = {pool.submit(process, ch): ch for ch in page_images}
    for f in as_completed(futures):
        ch_num, text = f.result()
        if text and len(text.strip()) > 5:
            results[ch_num] = text

def text_to_xhtml(text, title=""):
    html = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
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
            
    body_str = "\n".join(body_lines)
    return f'''<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>{title}</title></head>
<body>
{body_str}
</body>
</html>'''

print(f"\n📦 Podmieniam dane i generuję nowy EPUB {OUTPUT_EPUB}...")
z_in = zipfile.ZipFile(EPUB_PATH, "r")
z_out = zipfile.ZipFile(OUTPUT_EPUB, "w", zipfile.ZIP_DEFLATED)
replaced = 0
for item in z_in.infolist():
    data = z_in.read(item.filename)
    m = re.search(r'ch_(\d+)\.xhtml', item.filename)
    if m:
        ch_num = int(m.group(1))
        if ch_num in results:
            new_xhtml = text_to_xhtml(results[ch_num])
            z_out.writestr(item, new_xhtml.encode("utf-8"))
            replaced += 1
            continue
    z_out.writestr(item, data)
z_in.close()
z_out.close()
print(f"🎉 Zakończono! Wymieniono rozdziałów: {replaced}.")
