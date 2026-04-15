#!/usr/bin/env python3
"""
repair_davinci.py  v3
Wykrywa nieprzełumaczone bloki przez porównanie bbox:
- blok oryginalny (nie ArialUnicodeMS) bez nakładki ArialUnicodeMS w tym samym miejscu
  = nie przetłumaczony -> do naprawy.
Re-tlumaczy je z NVIDIA NIM Mistral Small i zapisuje poprawiony PDF.
"""

import fitz, json, os, re, sys, time, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Tuple

PDF_TRANS  = "/Users/mac/Downloads/DaVinci_Resolve_20_Reference_Manual_PL.pdf"
PDF_OUT    = "/Users/mac/Downloads/DaVinci_Resolve_20_Reference_Manual_PL2.pdf"
API_KEY    = "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"
MODEL      = "mistralai/mistral-small-4-119b-2603"
WORKERS    = 12
MAX_CHARS  = 6000
NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MIN_LEN    = 50

SYSTEM_PROMPT = """Jestes profesjonalnym tlumaczem technicznym dokumentacji DaVinci Resolve.
Otrzymujesz liste blokow tekstowych z instrukcji obslugi (JSON). Przetlumacz kazdy na polski.
Zasady bezwzgledne:
- Zachowaj nazwy menu i elementow UI DaVinci Resolve w oryginale: Inspector, Timeline, Fusion, Color, Cut, Edit, Deliver, Fairlight, Media Pool, Node itp.
- Zachowaj skroty klawiaturowe bez zmian: Ctrl+Z, Cmd+S itp.
- Zachowaj nazwy formatow plikow: .mov, .mxf, .r3d, .braw itp.
- NIE tlumacz nazw wlasnych: DaVinci Resolve, Blackmagic Design, Fusion, Fairlight.
- Zachowaj formatowanie: myslniki, numery, symbole.
- Zwroc WYLACZNIE tablice JSON z przetlumaczonymi stringami w tej samej kolejnosci.
- Zero komentarzy, zero blokow markdown."""

PL_CHARS = set("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ")

def _font():
    for p in [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]:
        if os.path.isfile(p): return p
    return None

FONT = _font()
if not FONT:
    print("Brak czcionki Unicode"); sys.exit(1)

def bbox_overlap(a, b, thresh=0.4):
    ax0,ay0,ax1,ay1 = a; bx0,by0,bx1,by1 = b
    ix0=max(ax0,bx0); iy0=max(ay0,by0); ix1=min(ax1,bx1); iy1=min(ay1,by1)
    if ix1<=ix0 or iy1<=iy0: return False
    inter=(ix1-ix0)*(iy1-iy0)
    area_a=(ax1-ax0)*(ay1-ay0)
    return (inter/area_a)>thresh if area_a>0 else False

def find_untranslated(page):
    arial_bboxes = []
    orig_blocks  = []
    for blk in page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]:
        if blk.get("type") != 0: continue
        fonts, text = set(), ""
        fsize, color = 11.0, 0
        for line in blk.get("lines", []):
            for span in line.get("spans", []):
                fonts.add(span.get("font", ""))
                text += span.get("text", "")
                fsize = float(span.get("size", fsize))
                color = span.get("color", color)
        text = text.strip()
        bbox = tuple(blk["bbox"])
        if "ArialUnicodeMS" in fonts:
            arial_bboxes.append(bbox)
        elif len(text) >= MIN_LEN and not any(c in PL_CHARS for c in text):
            orig_blocks.append({"bbox": bbox, "text": text,
                                 "size": fsize, "color": color, "bold": False})
    return [b for b in orig_blocks
            if not any(bbox_overlap(b["bbox"], ab) for ab in arial_bboxes)]

import urllib.request, urllib.error

def translate_blocks(texts: List[str]) -> List[Optional[str]]:
    if not texts: return []
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role":"system","content":SYSTEM_PROMPT},
                     {"role":"user",  "content":json.dumps(texts,ensure_ascii=False)}],
        "temperature": 0.05, "max_tokens": 16384, "stream": False,
    }).encode()
    headers = {"Authorization": f"Bearer {API_KEY}",
               "Content-Type": "application/json", "Accept": "application/json"}
    for attempt in range(6):
        try:
            req = urllib.request.Request(NVIDIA_URL, payload, headers)
            with urllib.request.urlopen(req, timeout=120) as r:
                resp = json.loads(r.read())
            raw = resp["choices"][0]["message"]["content"].strip()
            raw = re.sub(r"^```(?:json)?\s*","",raw)
            raw = re.sub(r"\s*```$","",raw)
            result = json.loads(raw)
            if isinstance(result,list) and len(result)==len(texts):
                return [str(t) if t else None for t in result]
            return [None]*len(texts)
        except urllib.error.HTTPError as e:
            if e.code==429:
                wait=int(e.headers.get("Retry-After",2**(attempt+2)))
                print(f"\n  Rate limit {wait}s...",flush=True); time.sleep(wait); continue
            if e.code in(500,503): time.sleep(3*(attempt+1)); continue
            return [None]*len(texts)
        except(json.JSONDecodeError,KeyError):
            if attempt<3: time.sleep(2+attempt); continue
            return [None]*len(texts)
        except Exception: time.sleep(3*(attempt+1))
    return [None]*len(texts)

def color_to_rgb(c):
    return ((c>>16)&0xFF)/255,((c>>8)&0xFF)/255,(c&0xFF)/255

def apply_translations(page, blocks, translations):
    for blk, pl in zip(blocks, translations):
        if not pl or not pl.strip(): continue
        rect = fitz.Rect(blk["bbox"])
        page.draw_rect(rect, color=(1,1,1), fill=(1,1,1), overlay=True)
        rgb = color_to_rgb(blk["color"])
        for scale in [1.0,0.93,0.86,0.79,0.72,0.65,0.58]:
            size = max(5.0, blk["size"]*scale)
            try:
                rc = page.insert_textbox(rect, pl, fontsize=size, fontfile=FONT,
                                         fontname="f0", color=rgb, align=0, overlay=True)
                if rc >= 0: break
            except Exception: break

def repair_page(page_idx: int) -> Tuple[int, list, list]:
    doc  = fitz.open(PDF_TRANS)
    blks = find_untranslated(doc[page_idx])
    doc.close()
    if not blks: return page_idx, [], []
    groups, cur, cur_len = [], [], 0
    for b in blks:
        t = b["text"]
        if cur_len+len(t)>MAX_CHARS and cur:
            groups.append(cur); cur=[b]; cur_len=len(t)
        else:
            cur.append(b); cur_len+=len(t)
    if cur: groups.append(cur)
    all_b, all_t = [], []
    for grp in groups:
        tr = translate_blocks([b["text"] for b in grp])
        all_b.extend(grp); all_t.extend(tr)
    return page_idx, all_b, all_t

def main():
    t0 = time.time()
    total = len(fitz.open(PDF_TRANS))
    print(f"Repair v3 — detekcja przez bbox ArialUnicodeMS")
    print(f"Wejscie: {PDF_TRANS}")
    print(f"Wyjscie: {PDF_OUT}")
    print(f"Stron: {total} | Workerzy: {WORKERS}")
    print("="*60)

    all_results = {}
    done = fix_p = fix_b = 0
    lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(repair_page, i): i for i in range(total)}
        for future in as_completed(futures):
            idx, blocks, translations = future.result()
            all_results[idx] = (blocks, translations)
            with lock:
                done += 1
                if blocks: fix_p+=1; fix_b+=sum(1 for t in translations if t)
            elapsed = time.time()-t0
            eta = (elapsed/done)*(total-done) if done>0 else 0
            print(f"\r  [{done:4d}/{total}] {done/total*100:5.1f}%"
                  f" | stron: {fix_p} | blokow: {fix_b} | ETA: {eta/60:.1f} min   ",
                  end="", flush=True)

    print(f"\n\nSkan ukonczony ({(time.time()-t0)/60:.1f} min)")
    print(f"Stron do naprawy: {fix_p}/{total}  Blokow: {fix_b}")
    if fix_b == 0:
        print("Nic do naprawy!"); return

    print(f"\nNakladam tlumaczenia...")
    src = fitz.open(PDF_TRANS)
    applied = skipped = 0
    for i in range(total):
        blocks, translations = all_results.get(i, ([], []))
        if blocks:
            apply_translations(src[i], blocks, translations)
            applied += sum(1 for t in translations if t)
            skipped += sum(1 for t in translations if not t)
        if (i+1)%200==0: print(f"  Strona {i+1}/{total}...", flush=True)

    print(f"  Zapisuje PDF...")
    src.save(PDF_OUT, garbage=4, deflate=True, clean=True)
    src.close()

    print(f"\n{'='*60}")
    print(f"GOTOWE!")
    print(f"  Plik:       {PDF_OUT}")
    print(f"  Naprawiono: {applied} blokow")
    print(f"  Blad API:   {skipped} blokow")
    print(f"  Czas:       {(time.time()-t0)/60:.1f} minut")

if __name__ == "__main__":
    main()
