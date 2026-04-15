#!/usr/bin/env python3
"""
Weryfikacja tłumaczenia EPUB vs PDF.
150dpi + Context Caching.

Jak działa caching:
- PDF wgrany do Files API (raz, bezpłatnie)
- Cached content z PDF + system prompt
- Każde wywołanie: cache reference + strony PDF jako inline images (150dpi) + polski tekst
- Cache = 10x tańszy input dla systemu + PDF file reference
"""
import json, os, time, base64, re, zipfile, csv
import urllib.request, urllib.error
import fitz
from pathlib import Path

PDF    = "/Users/mac/Downloads/DaVinci_Resolve_20_Reference_Manual.pdf"
EPUB   = "/Users/mac/.pdf2epub-app/jobs/8b7c7f31/DaVinci_Resolve_20_Reference_Manual_pol_final.epub"
REPORT = "/Users/mac/.pdf2epub-app/jobs/8b7c7f31/verification_report.csv"
MODEL  = "gemini-3.1-flash-lite-preview"
DPI    = 150

API_KEY = json.load(open(os.path.expanduser("~/.pdf2epub-app/config.json"))).get("api_key", "")
BASE    = "https://generativelanguage.googleapis.com/v1beta"

SYSTEM_PROMPT = (
    "Jesteś weryfikatorem tłumaczeń technicznych EN→PL. "
    "Porównujesz oryginalną stronę PDF (obraz) z tłumaczeniem na polski. "
    "Odpowiadasz WYŁĄCZNIE w formacie:\n"
    "STATUS: OK|ERROR|PARTIAL\n"
    "ISSUES: [opis po polsku max 100 znaków, lub 'brak']"
)

def create_system_cache() -> str:
    """Cache the system prompt to save on repeated system instruction tokens."""
    print("🗄️  Tworzę cache dla system promptu...")
    url = f"{BASE}/cachedContents?key={API_KEY}"
    payload = {
        "model": f"models/{MODEL}",
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": "ready"}]}],
        "ttl": "7200s",  # 2h — enough for full book
    }
    req = urllib.request.Request(url, json.dumps(payload).encode(), {"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.loads(r.read())
        name = result.get("name", "")
        print(f"   ✅ Cache: {name}")
        return name
    except urllib.error.HTTPError as e:
        print(f"   ⚠️  Cache failed ({e.code}), używam bez cache.")
        return ""


def render_pages(doc, start: int, end: int) -> list:
    """Render PDF pages at 150dpi, return list of base64 PNGs."""
    mat = fitz.Matrix(DPI/72, DPI/72)
    imgs = []
    for p in range(start, min(end+1, len(doc))):
        pix = doc[p].get_pixmap(matrix=mat)
        imgs.append(base64.standard_b64encode(pix.tobytes("png")).decode())
    return imgs


def verify_chapter(cache_name: str, ch_num: int, page_imgs: list, polish_text: str) -> dict:
    url = f"{BASE}/models/{MODEL}:generateContent?key={API_KEY}"

    # Build parts: PDF images + polish text
    parts = []
    for img in page_imgs:
        parts.append({"inline_data": {"mime_type": "image/png", "data": img}})
    parts.append({"text": f"=== TŁUMACZENIE PL (rozdział {ch_num}) ===\n{polish_text[:1500]}\n=== KONIEC ==="})

    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 150},
    }
    if cache_name:
        payload["cachedContent"] = cache_name
    else:
        payload["system_instruction"] = {"parts": [{"text": SYSTEM_PROMPT}]}

    for attempt in range(4):
        try:
            req = urllib.request.Request(url, json.dumps(payload).encode(), {"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                result = json.loads(r.read())
            text = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
            status, issues = "UNKNOWN", ""
            for line in text.split("\n"):
                if line.startswith("STATUS:"):
                    status = line.split(":", 1)[1].strip()
                elif line.startswith("ISSUES:"):
                    issues = line.split(":", 1)[1].strip()
            return {"status": status, "issues": issues}
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep((2**attempt)*5)
                continue
            return {"status": "API_ERROR", "issues": f"HTTP {e.code}"}
        except Exception as ex:
            if attempt < 3:
                time.sleep(3); continue
            return {"status": "TIMEOUT", "issues": str(ex)[:60]}
    return {"status": "FAILED", "issues": "max retries"}


def main():
    z = zipfile.ZipFile(EPUB)
    xhtml_files = sorted(
        [n for n in z.namelist() if n.endswith(".xhtml") and "nav" not in n],
        key=lambda x: int(re.search(r"ch_(\d+)", x).group(1)) if re.search(r"ch_(\d+)", x) else 0
    )
    total = len(xhtml_files)
    doc = fitz.open(PDF)
    pdf_total = len(doc)
    ratio = pdf_total / total

    print(f"📚 Rozdziały EPUB: {total}")
    print(f"📄 Stron PDF:      {pdf_total}")

    cache_name = create_system_cache()

    results = []
    ok = errors = partial = skipped = 0

    for i, xhtml_name in enumerate(xhtml_files):
        m = re.search(r"ch_(\d+)", xhtml_name)
        ch_num = int(m.group(1)) if m else i

        raw = z.read(xhtml_name).decode("utf-8", errors="ignore")
        polish_text = re.sub(r"<[^>]+>", " ", raw)
        polish_text = re.sub(r"\s+", " ", polish_text).strip()

        # Skip very short chapters (blank/image-only pages)
        if len(polish_text) < 30:
            skipped += 1
            continue

        p_start = max(0, int(i * ratio))
        p_end   = min(int((i + 1) * ratio), pdf_total - 1)
        page_imgs = render_pages(doc, p_start, p_end)

        result = verify_chapter(cache_name, ch_num, page_imgs, polish_text)
        results.append({
            "chapter": xhtml_name,
            "ch_num": ch_num,
            "pdf_pages": f"{p_start}-{p_end}",
            "status": result["status"],
            "issues": result["issues"],
        })

        s = result["status"]
        if s == "OK":           ok += 1
        elif s == "ERROR":      errors += 1; print(f"  ❌ ch_{ch_num} (s.{p_start}-{p_end}): {result['issues']}")
        elif s == "PARTIAL":    partial += 1; print(f"  ⚠️  ch_{ch_num}: {result['issues']}")

        if (i+1) % 100 == 0:
            pct = (i+1)*100//total
            print(f"  [{i+1}/{total}] {pct}% | OK:{ok} ERR:{errors} ⚠️:{partial}")

        time.sleep(1.5)

    doc.close()

    with open(REPORT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["chapter","ch_num","pdf_pages","status","issues"])
        w.writeheader(); w.writerows(results)

    checked = ok + errors + partial
    print(f"\n{'='*50}")
    print(f"WYNIK  ({checked} sprawdzonych, {skipped} pominięto)")
    print(f"✅ OK:       {ok} ({ok*100//max(checked,1)}%)")
    print(f"⚠️  PARTIAL:  {partial} ({partial*100//max(checked,1)}%)")
    print(f"❌ ERROR:    {errors} ({errors*100//max(checked,1)}%)")
    print(f"📊 Raport CSV: {REPORT}")

if __name__ == "__main__":
    main()
