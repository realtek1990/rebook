#!/usr/bin/env python3
import json, os, sys, time, base64, re, zipfile
import urllib.request
import fitz
from concurrent.futures import ThreadPoolExecutor, as_completed

EPUB_PATH = "/Users/mac/.pdf2epub-app/jobs/8b7c7f31/DaVinci_Resolve_20_Reference_Manual_pol_final.epub"
PDF_PATH = "/Users/mac/Downloads/DaVinci_Resolve_20_Reference_Manual.pdf"

config = json.load(open(os.path.expanduser("~/.pdf2epub-app/config.json")))
API_KEY = config.get("api_key", "")
# Switching to Gemini 1.5 Flash for the fix (bypassing Gemma's CoT issues)
MODEL = "gemini-1.5-flash"
WORKERS = 15  # Flash is fast and allows higher concurrency
DPI = 200

print("🔍 Inicjowanie analizy EPUB pod kątem brudnych plików z modelem Gemma...")
z = zipfile.ZipFile(EPUB_PATH, "r")
bad_patterns = [
    r'->',
    r'UI Text',
    r'Revised structure',
    r'menu items:\*',
    r'Check .* menu items',
    r'Self-correction',
    r'I will',
    r'Footer:',
    r'Formatting check'
]

dirty_chapters = []
for file in z.namelist():
    if not file.endswith('.xhtml') or 'nav' in file: continue
    content = z.read(file).decode('utf-8', errors='ignore')
    text = re.sub(r'<[^>]+>', '', content)
    
    for pat in bad_patterns:
        if re.search(pat, text, re.IGNORECASE):
            # Extract chapter number
            m = re.search(r'ch_(\d+)', file)
            if m:
                dirty_chapters.append(int(m.group(1)))
            break
z.close()

print(f"🔧 Zidentyfikowano {len(dirty_chapters)} rozwalonych strukturalnie rozdziałów.")
if not dirty_chapters:
    print("✅ EPUB jest czysty. Wychodzę.")
    sys.exit(0)

print(f"📄 Pobieranie i rzutowanie {len(dirty_chapters)} stron na pliki graficzne z oryginalnego PDF-a...")
doc = fitz.open(PDF_PATH)
mat = fitz.Matrix(DPI / 72, DPI / 72)
page_images = {}
for ch in dirty_chapters:
    if ch < len(doc):
        pix = doc[ch].get_pixmap(matrix=mat)
        page_images[ch] = base64.standard_b64encode(pix.tobytes("png")).decode()
doc.close()

print(f"\n🚀 Wysyłanie stron do API Gemini 1.5 Flash ({WORKERS} concurrent)...")
results = {}
errors = []
done = [0]
import threading
lock = threading.Lock()

def process(ch_num):
    for attempt in range(5):  # 5 retries with backoff just in case
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"
            prompt = """You are a highly precise OCR and text extraction engine translating to POLISH.
Extract ALL text from this scanned manual page and output only the translated text in Polish.

CRITICAL RULES:
1. OUTPUT ABSOLUTELY NO META-THINKING, REASONING, OR CHATBOT CONVERSATIONS. Output nothing but the extracted and translated content.
2. Keep the exact layout where possible using Markdown (#, -, >).
3. Translate UI components carefully, but do not create mapping dictionaries. Just layout the text exactly as it appears in the image, but translated.
4. If an image illustration is present without readable text, output EXACTLY `{{IMAGE:strona}}`.
5. If the image has text or captions that you can extract, output `{{IMAGE_TEXT:strona}}` followed by the extracted/translated descriptions.
6. Do not include your own thoughts or "Revised Structure".
"""

            payload = {
                "systemInstruction": {"parts": [{"text": prompt}]},
                "contents": [{"parts": [
                    {"text": "Wyodrębnij i przetłumacz."},
                    {"inline_data": {"mime_type": "image/png", "data": page_images[ch_num]}},
                ]}],
                "generationConfig": {"temperature": 0.0},
            }
            req = urllib.request.Request(url, json.dumps(payload).encode(), {"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=180) as resp:
                result = json.loads(resp.read())
            
            text = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            
            with lock:
                done[0] += 1
                tlen = len(text) if text else 0
                print(f"  ✅ [Flash] ch_{ch_num:03d} ({tlen} chars) [{done[0]}/{len(page_images)}]")
            return ch_num, text.strip()
            
        except Exception as e:
            if "429" in str(e) or "timed out" in str(e).lower() or "500" in str(e):
                wait = (2 ** attempt) * 2
                time.sleep(wait)
                continue
            with lock:
                done[0] += 1
                print(f"  ❌ [Error] ch_{ch_num:03d}: {e} [{done[0]}/{len(page_images)}]")
            return ch_num, None
            
    with lock:
        done[0] += 1
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
    return f'<?xml version="1.0" encoding="utf-8"?>\n<html xmlns="http://www.w3.org/1999/xhtml">\n<head><title>{title}</title></head>\n<body>\n' + "\n".join(body_lines) + '\n</body>\n</html>'

print(f"\n📦 Podmieniam dane i zapisuję plik docelowy: {EPUB_PATH} ...")
# To overwrite EPUB safely
import tempfile
fd, temp_path = tempfile.mkstemp()
os.close(fd)

z_in = zipfile.ZipFile(EPUB_PATH, "r")
z_out = zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED)
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

import shutil
shutil.move(temp_path, EPUB_PATH)
print(f"🎉 Misja uzdrawiająca z Gemini Flash zakończona! Wymieniono {replaced} uszkodzonych rozdziałów.")
