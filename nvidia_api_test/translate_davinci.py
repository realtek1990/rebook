#!/usr/bin/env python3
"""
translate_davinci.py
PDF → PDF tłumaczenie z zachowaniem layoutu i obrazków.

Podejście:
  - PyMuPDF wyciąga bloki tekstowe z natywnej warstwy (bezpłatnie, lokalnie)
  - NVIDIA NIM Mistral Small tłumaczy je grupami (12 równoległych workerów)
  - Białe prostokąty zakrywają oryginał, polskie tłumaczenie wstawiane w to samo miejsce
  - Obrazy (screenshots UI) zostawiane bez zmian

Szacowany czas: ~40-60 minut dla 4234 stron.
"""

import fitz, json, os, re, sys, time, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional, Tuple

# ── Config ────────────────────────────────────────────────────────────────────
PDF_IN   = "/Users/mac/Downloads/DaVinci_Resolve_20_Reference_Manual.pdf"
PDF_OUT  = "/Users/mac/Downloads/DaVinci_Resolve_20_Reference_Manual_PL.pdf"
API_KEY  = "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"
MODEL    = "mistralai/mistral-small-4-119b-2603"
WORKERS  = 12          # max bezpiecznych równoległych requestów dla NVIDIA NIM
MAX_CHARS_PER_CALL = 6000   # max znaków tekstu na jedno wywołanie API

NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

SYSTEM_PROMPT = """Jesteś profesjonalnym tłumaczem technicznym dokumentacji DaVinci Resolve.
Otrzymujesz listę bloków tekstowych z instrukcji obsługi (JSON). Przetłumacz każdy na polski.

Zasady bezwzględne:
- Zachowaj nazwy menu i elementów UI DaVinci Resolve w oryginale: Inspector, Timeline, Fusion, Color, Cut, Edit, Deliver, Fairlight, Media Pool, Node, Clip, Bin, Grade, Gallery, Viewer itp.
- Zachowaj skróty klawiaturowe bez zmian: Ctrl+Z, Cmd+S, Option+Click itp.
- Zachowaj nazwy formatów plików: .mov, .mxf, .r3d, .arri, .braw itp.
- Zachowaj numery wersji i kody modeli bez zmian.
- NIE tłumacz nazw własnych oprogramowania (DaVinci Resolve, Blackmagic Design, Fusion, Fairlight).
- Zachowaj formatowanie: myślniki, numery na początku linii, symbole ◆ • — ▸.
- Zwróć WYŁĄCZNIE tablicę JSON z przetłumaczonymi stringami, w tej samej kolejności co wejście.
- Żadnych komentarzy, żadnych bloków markdown."""

# ── Font ─────────────────────────────────────────────────────────────────────
def _font(bold=False):
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None

FONT = _font()
if not FONT:
    print("❌ Brak czcionki Unicode — zainstaluj Arial lub Liberation Fonts")
    sys.exit(1)

# ── Text block extraction ─────────────────────────────────────────────────────
def extract_blocks(page):
    """Zwraca listę bloków tekstowych z bbox, fontem, size i bold."""
    blocks = []
    for blk in page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]:
        if blk.get("type") != 0:   # type=1 to obrazy — pomijamy
            continue
        text = "".join(
            span["text"]
            for line in blk.get("lines", [])
            for span in line.get("spans", [])
        ).strip()
        if len(text) < 3:
            continue
        # Pobierz styl z pierwszego spanu
        fsize, bold, color = 11.0, False, 0
        for line in blk.get("lines", []):
            for span in line.get("spans", []):
                fsize = float(span.get("size", 11))
                bold  = bool(span.get("flags", 0) & (1 << 4))
                color = span.get("color", 0)
                break
            break
        blocks.append({
            "bbox": tuple(blk["bbox"]),
            "text": text,
            "size": fsize,
            "bold": bold,
            "color": color,
        })
    return blocks

# ── NVIDIA NIM translation ────────────────────────────────────────────────────
import urllib.request, urllib.error

def translate_blocks(blocks_text):  # List[str] -> List[Optional[str]]
    """Wyślij listę stringów do NVIDIA NIM, odbierz przetłumaczone stringi."""
    if not blocks_text:
        return []

    payload = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": json.dumps(blocks_text, ensure_ascii=False)},
        ],
        "temperature": 0.05,
        "max_tokens": 16384,
        "stream": False,
    }).encode()

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    for attempt in range(5):
        try:
            req = urllib.request.Request(NVIDIA_URL, payload, headers)
            with urllib.request.urlopen(req, timeout=120) as r:
                resp = json.loads(r.read())
            raw = resp["choices"][0]["message"]["content"].strip()
            # Usuń bloki markdown jeśli model je dodał mimo instrukcji
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            result = json.loads(raw)
            if isinstance(result, list) and len(result) == len(blocks_text):
                return [str(t) if t is not None else None for t in result]
            return [None] * len(blocks_text)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = int(e.headers.get("Retry-After", 2 ** (attempt + 2)))
                print(f"  ⏳ Rate limit — czekam {wait}s...", flush=True)
                time.sleep(wait)
                continue
            if e.code in (500, 503):
                time.sleep(3 * (attempt + 1))
                continue
            print(f"  ❌ HTTP {e.code}: {e.read()[:200]}")
            return [None] * len(blocks_text)
        except (json.JSONDecodeError, KeyError):
            if attempt < 2:
                time.sleep(2); continue
            return [None] * len(blocks_text)
        except Exception as ex:
            time.sleep(3 * (attempt + 1))
    return [None] * len(blocks_text)

# ── Apply translations back to page ──────────────────────────────────────────
def color_to_rgb(c):
    return ((c >> 16) & 0xFF) / 255, ((c >> 8) & 0xFF) / 255, (c & 0xFF) / 255

def apply_translations(page, blocks, translations):
    for blk, pl in zip(blocks, translations):
        if not pl or not pl.strip():
            continue
        rect = fitz.Rect(blk["bbox"])
        # Zakryj oryginał białym prostokątem
        page.draw_rect(rect, color=(1,1,1), fill=(1,1,1), overlay=True)
        # Wstaw tłumaczenie (zmniejszaj font aż się zmieści)
        rgb = color_to_rgb(blk["color"])
        for scale in [1.0, 0.93, 0.86, 0.79, 0.72, 0.65, 0.58]:
            size = max(5.0, blk["size"] * scale)
            try:
                rc = page.insert_textbox(
                    rect, pl,
                    fontsize=size, fontfile=FONT, fontname="f0",
                    color=rgb, align=0, overlay=True,
                )
                if rc >= 0:
                    break
            except Exception:
                break

# ── Process one page ──────────────────────────────────────────────────────────
def process_page(page_idx, doc_path):  # -> Tuple[int, list, list]
    """Otwiera PDF, tłumaczy stronę, zwraca (bloki, tłumaczenia)."""
    doc = fitz.open(doc_path)
    page = doc[page_idx]
    blocks = extract_blocks(page)
    doc.close()

    if not blocks:
        return page_idx, [], []

    # Chunking — żeby nie przekraczać MAX_CHARS_PER_CALL
    # Ale grupujemy bloki tej samej strony w jak najmniej callów
    all_texts = [b["text"] for b in blocks]
    
    # Podziel na grupy ≤ 4000 znaków (żeby odpowiedź miała dużo miejsca w 16384 tokenach)
    groups = []
    current_group = []
    current_len = 0
    for t in all_texts:
        if current_len + len(t) > MAX_CHARS_PER_CALL and current_group:
            groups.append(current_group)
            current_group = [t]
            current_len = len(t)
        else:
            current_group.append(t)
            current_len += len(t)
    if current_group:
        groups.append(current_group)

    # Przetłumacz każdą grupę (zwykle 1 call per strona)
    translations = []
    for grp in groups:
        tr = translate_blocks(grp)
        translations.extend(tr)

    return page_idx, blocks, translations

# ── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    t_start = time.time()
    src = fitz.open(PDF_IN)
    total = len(src)
    src.close()

    print(f"📚 DaVinci Resolve 20 Reference Manual → Polski")
    print(f"   Stron: {total} | Model: {MODEL} | Workerzy: {WORKERS}")
    print(f"   Wejście:  {PDF_IN}")
    print(f"   Wyjście:  {PDF_OUT}")
    print(f"{'='*60}\n")

    # Parallelny OCR + tłumaczenie
    all_results = {}  # page_idx → (blocks, translations)
    done = 0
    text_pages = 0
    total_blocks = 0
    lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(process_page, i, PDF_IN): i for i in range(total)}
        for future in as_completed(futures):
            page_idx, blocks, translations = future.result()
            all_results[page_idx] = (blocks, translations)
            with lock:
                done += 1
                if blocks:
                    text_pages += 1
                    total_blocks += len(blocks)
            elapsed = time.time() - t_start
            eta = (elapsed / done) * (total - done) if done > 0 else 0
            print(
                f"\r  [{done:4d}/{total}] "
                f"{done/total*100:5.1f}% | "
                f"tekst: {text_pages} | "
                f"bloki: {total_blocks} | "
                f"ETA: {eta/60:.1f} min   ",
                end="", flush=True
            )

    print(f"\n\n✅ Tłumaczenie zakończone w {(time.time()-t_start)/60:.1f} min")
    print(f"   Stron z tekstem: {text_pages}/{total}")
    print(f"   Przetłumaczonych bloków: {total_blocks}")

    # Składanie PDF wyjściowego
    print(f"\n📝 Składam PDF wyjściowy...")
    t2 = time.time()

    src2 = fitz.open(PDF_IN)
    out_doc = fitz.open()
    out_doc.insert_pdf(src2)

    applied = skipped = 0
    for i in range(total):
        blocks, translations = all_results.get(i, ([], []))
        if blocks and translations:
            page = out_doc[i]
            apply_translations(page, blocks, translations)
            applied += sum(1 for t in translations if t)
            skipped += sum(1 for t in translations if not t)
        if (i+1) % 100 == 0:
            print(f"  Strona {i+1}/{total}...", flush=True)

    print(f"  Zapisuję PDF (może chwilę zająć przy 200MB)...")
    out_doc.save(PDF_OUT, garbage=4, deflate=True, clean=True)
    out_doc.close()
    src2.close()

    total_time = time.time() - t_start
    print(f"\n{'='*60}")
    print(f"🎉 GOTOWE!")
    print(f"   Plik: {PDF_OUT}")
    print(f"   Przetłumaczono: {applied} bloków")
    print(f"   Pominięto:      {skipped} bloków (błąd API)")
    print(f"   Całkowity czas: {total_time/60:.1f} minut")

if __name__ == "__main__":
    main()
