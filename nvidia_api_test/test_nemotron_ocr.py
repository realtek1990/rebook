#!/usr/bin/env python3
"""
Benchmark: nvidia/llama-3.1-nemotron-nano-vl-8b-v1 jako OCR
vs Mistral OCR API — jakość, szybkość, format wyjścia.

Uruchomienie:
  python3 test_nemotron_ocr.py /ścieżka/do/ksiazki.pdf
"""

import sys
import base64
import time
import json
import concurrent.futures
from pathlib import Path

API_KEY = "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"
NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MISTRAL_OCR_URL = "https://api.mistral.ai/v1/ocr"

# Strony do testu (0-indexed)
TEST_PAGES = [0, 1, 5, 10, 50, 100]
CONCURRENT_TESTS = [1, 4, 8, 12]

OCR_PROMPT = (
    "Extract ALL text from this book page. "
    "Preserve paragraph structure. Use markdown: # for chapter headings, "
    "** for bold, > for block quotes. "
    "Return ONLY the extracted text, no comments."
)

# ─── PDF → PNG pages ────────────────────────────────────────────────────────

def pdf_page_to_b64(pdf_path: str, page_idx: int, dpi: int = 150) -> str | None:
    """Render a single PDF page to PNG and return as base64 string."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        if page_idx >= len(doc):
            return None
        page = doc[page_idx]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        doc.close()
        return base64.b64encode(img_bytes).decode()
    except ImportError:
        print("❌ PyMuPDF nie zainstalowany. Uruchom: pip install pymupdf")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Błąd renderowania strony {page_idx}: {e}")
        return None

def get_page_count(pdf_path: str) -> int:
    import fitz
    doc = fitz.open(pdf_path)
    n = len(doc)
    doc.close()
    return n

# ─── Nemotron Nano VL OCR ───────────────────────────────────────────────────

def nemotron_ocr_page(b64_img: str, page_idx: int) -> dict:
    import requests
    t0 = time.time()
    payload = {
        "model": "nvidia/llama-3.1-nemotron-nano-vl-8b-v1",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_img}"}},
                {"type": "text", "text": OCR_PROMPT}
            ]
        }],
        "max_tokens": 4096,
        "temperature": 0.1,
        "stream": False
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    try:
        r = requests.post(NVIDIA_URL, headers=headers, json=payload, timeout=60)
        elapsed = time.time() - t0
        if r.status_code == 200:
            text = r.json()["choices"][0]["message"]["content"]
            return {"page": page_idx, "model": "nemotron-vl", "status": "ok",
                    "chars": len(text), "time": elapsed, "text": text}
        else:
            return {"page": page_idx, "model": "nemotron-vl", "status": f"err-{r.status_code}",
                    "chars": 0, "time": elapsed, "text": r.text[:200]}
    except Exception as e:
        return {"page": page_idx, "model": "nemotron-vl", "status": f"exc",
                "chars": 0, "time": time.time()-t0, "text": str(e)}

# ─── Porównanie jakości ────────────────────────────────────────────────────

def quality_score(text: str) -> dict:
    """Heuristic quality assessment of OCR output."""
    lines = [l for l in text.split('\n') if l.strip()]
    words = text.split()
    has_structure = any(l.startswith('#') for l in lines)
    avg_word_len = sum(len(w) for w in words) / max(1, len(words))
    # Garbage indicators: too many short "words", random chars
    short_ratio = sum(1 for w in words if len(w) <= 2) / max(1, len(words))
    return {
        "lines": len(lines),
        "words": len(words),
        "chars": len(text),
        "has_structure": has_structure,
        "avg_word_len": round(avg_word_len, 1),
        "short_word_ratio": round(short_ratio, 2),
        "garbage_risk": "HIGH" if short_ratio > 0.4 or avg_word_len < 3 else "LOW"
    }

# ─── Concurrency test ─────────────────────────────────────────────────────

def test_concurrency(b64_img: str, n_workers: int) -> dict:
    """Send n_workers parallel requests with the same page."""
    t0 = time.time()
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as ex:
        futures = [ex.submit(nemotron_ocr_page, b64_img, 0) for _ in range(n_workers)]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())
    elapsed = time.time() - t0
    ok = sum(1 for r in results if r["status"] == "ok")
    errors = [r["status"] for r in results if r["status"] != "ok"]
    return {
        "workers": n_workers,
        "total_time": round(elapsed, 2),
        "ok": ok,
        "failed": len(results) - ok,
        "errors": errors,
        "throughput_pps": round(ok / elapsed, 2)
    }

# ─── MAIN ─────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Użycie: python3 test_nemotron_ocr.py /ścieżka/do/ksiazki.pdf")
        sys.exit(1)

    pdf_path = sys.argv[1]
    if not Path(pdf_path).exists():
        print(f"❌ Plik nie istnieje: {pdf_path}")
        sys.exit(1)

    total_pages = get_page_count(pdf_path)
    print(f"\n{'='*60}")
    print(f"📚 Książka: {Path(pdf_path).name}")
    print(f"📄 Stron: {total_pages}")
    print(f"{'='*60}\n")

    # Wybierz dostępne strony
    test_pages = [p for p in TEST_PAGES if p < total_pages]
    if not test_pages:
        test_pages = [0]

    # ── TEST 1: Jakość OCR na kilku stronach ──────────────────────────────
    print("🧪 TEST 1: Jakość OCR (Nemotron Nano VL 8B)")
    print("-" * 50)
    results = []
    for page_idx in test_pages:
        print(f"  Renderuję stronę {page_idx+1}...", end="", flush=True)
        b64 = pdf_page_to_b64(pdf_path, page_idx)
        if b64 is None:
            continue
        print(f" wysyłam...", end="", flush=True)
        r = nemotron_ocr_page(b64, page_idx)
        q = quality_score(r["text"]) if r["status"] == "ok" else {}
        results.append((r, q, b64))
        status_icon = "✅" if r["status"] == "ok" else "❌"
        print(f" {status_icon} {r['time']:.2f}s | {r['chars']} znaków | {q.get('words',0)} słów | garbage: {q.get('garbage_risk','?')}")

    # ── TEST 2: Concurrency ───────────────────────────────────────────────
    print(f"\n🧪 TEST 2: Współbieżność (ta sama strona ×N)")
    print("-" * 50)
    if results:
        test_b64 = results[0][2]  # reuse first page b64
        for n in CONCURRENT_TESTS:
            print(f"  {n} równoczesnych requestów...", end="", flush=True)
            c = test_concurrency(test_b64, n)
            print(f" {c['ok']}/{n} OK | {c['total_time']}s | {c['throughput_pps']} pages/s | błędy: {c['errors'] if c['errors'] else 'brak'}")

    # ── Wyniki szczegółowe ────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("📊 WYNIKI SZCZEGÓŁOWE — próbki tekstu (pierwsze 400 znaków):")
    print(f"{'='*60}")
    for i, (r, q, _) in enumerate(results):
        if r["status"] == "ok":
            print(f"\n── Strona {r['page']+1} ({r['time']:.2f}s) ──")
            print(r["text"][:400])
            print(f"  [jakość: {q}]")

    # ── Szacunek dla całej książki ────────────────────────────────────────
    if results:
        ok_results = [(r, q) for r, q, _ in results if r["status"] == "ok"]
        if ok_results:
            avg_time = sum(r["time"] for r, _ in ok_results) / len(ok_results)
            avg_chars = sum(r["chars"] for r, _ in ok_results) / len(ok_results)
            # Z 12 workerami
            est_time_12 = (total_pages * avg_time) / 12
            est_time_1 = total_pages * avg_time
            print(f"\n{'='*60}")
            print(f"⏱  SZACUNEK DLA CAŁEJ KSIĄŻKI ({total_pages} stron):")
            print(f"   Średni czas/stronę: {avg_time:.2f}s")
            print(f"   Średnio znaków/stronę: {avg_chars:.0f}")
            print(f"   Całkowity tekst: ~{total_pages * avg_chars / 1000:.0f}K znaków")
            print(f"   Czas z 1 workerem:   {est_time_1/60:.1f} minut")
            print(f"   Czas z 12 workerami: {est_time_12/60:.1f} minut")
            print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
