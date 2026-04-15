"""
pdf_translator.py — PDF→PDF translation with layout preservation.

Pipeline:
  1. PyMuPDF renders each page as a PNG image (150 DPI)
  2. Gemini Flash Lite receives the image + extracted text block bboxes
  3. Gemini returns translated text for each block (with visual context)
  4. White rectangles cover original text, translated text inserted via Arial Unicode

Public API:
    translate_pdf(pdf_path, output_path, lang_to, api_key, model,
                  workers, progress_callback) -> str
"""

from __future__ import annotations

import base64
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Optional

import fitz  # PyMuPDF

# ── Rate limiter ───────────────────────────────────────────────────────────────
# Gemini Flash Lite free: 15 RPM → 4s gap; paid: 1500 RPM → no real limit
_api_lock      = threading.Lock()
_last_api_call = 0.0
MIN_API_INTERVAL = 0.5  # seconds; increase to 4.0 if on free tier

def _throttle():
    global _last_api_call
    with _api_lock:
        wait = _last_api_call + MIN_API_INTERVAL - time.time()
        if wait > 0:
            time.sleep(wait)
        _last_api_call = time.time()


# ── Font discovery ─────────────────────────────────────────────────────────────

def _find_unicode_font(bold: bool = False) -> Optional[str]:
    candidates_regular = [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/noto/NotoSans-Regular.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
    ]
    candidates_bold = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
    ]
    pool = candidates_bold if bold else candidates_regular
    for path in pool:
        if os.path.isfile(path):
            return path
    if bold:
        return _find_unicode_font(bold=False)
    return None


FONT_REGULAR = _find_unicode_font(bold=False)
FONT_BOLD    = _find_unicode_font(bold=True)


# ── Text block extraction (for bboxes only) ────────────────────────────────────

def _extract_blocks(page: fitz.Page) -> list[dict]:
    """Extract text blocks with bounding boxes and style info."""
    blocks = []
    for blk in page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]:
        if blk.get("type") != 0:
            continue
        text = "".join(
            span["text"]
            for line in blk.get("lines", [])
            for span in line.get("spans", [])
        ).strip()
        if len(text) < 3:
            continue

        fsize, bold, color = 11.0, False, 0
        for line in blk.get("lines", []):
            for span in line.get("spans", []):
                fsize = float(span.get("size", 11))
                bold  = bool(span.get("flags", 0) & (1 << 4))
                color = span.get("color", 0)
                break
            break

        blocks.append({
            "bbox":  tuple(blk["bbox"]),
            "text":  text,
            "size":  fsize,
            "bold":  bold,
            "color": color,
        })
    return blocks


def _color_to_rgb(color_int: int) -> tuple[float, float, float]:
    r = ((color_int >> 16) & 0xFF) / 255
    g = ((color_int >>  8) & 0xFF) / 255
    b = ( color_int        & 0xFF) / 255
    return (r, g, b)


# ── Gemini translation (image + text blocks → translated texts) ────────────────

GEMINI_PROMPT = """You are a technical translator for a DaVinci Resolve software manual. 
You are given a screenshot of one manual page and a numbered list of text blocks extracted from it.

Translate each numbered block from English to {lang_to}.
Rules:
- Keep all DaVinci Resolve UI element names, menu names, keyboard shortcuts as-is
- Keep formatting markers like ◆ • — at the start of lines
- Return ONLY a JSON array of strings, one per block, in the same order
- No explanations, no markdown fences, just the JSON array

Text blocks to translate:
{blocks_json}"""


def _translate_page_gemini(
    page_png_b64: str,
    blocks: list[dict],
    lang_to: str,
    api_key: str,
    model: str,
) -> list[Optional[str]]:
    """Send page image + block texts to Gemini, get back translations."""
    if not blocks:
        return []

    blocks_json = json.dumps(
        [{"id": i, "text": b["text"]} for i, b in enumerate(blocks)],
        ensure_ascii=False, indent=None
    )
    prompt = GEMINI_PROMPT.format(lang_to=lang_to, blocks_json=blocks_json)

    payload = {
        "contents": [{
            "role": "user",
            "parts": [
                {
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": page_png_b64,
                    }
                },
                {"text": prompt},
            ]
        }],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 4096,
            "responseMimeType": "application/json",
        },
    }

    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={api_key}")

    for attempt in range(5):
        _throttle()
        try:
            req = urllib.request.Request(
                url, json.dumps(payload).encode(),
                {"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=180) as r:
                resp = json.loads(r.read())

            raw = resp["candidates"][0]["content"]["parts"][0]["text"].strip()

            # Parse JSON array
            # Strip markdown fences if model added them despite instructions
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)

            translations = json.loads(raw)
            if isinstance(translations, list) and len(translations) == len(blocks):
                return [str(t) if t is not None else None for t in translations]

            # Handle {"id": N, "text": "..."} format as fallback
            if isinstance(translations, list) and translations and isinstance(translations[0], dict):
                out = [None] * len(blocks)
                for item in translations:
                    idx = item.get("id", -1)
                    if 0 <= idx < len(blocks):
                        out[idx] = str(item.get("text") or item.get("translated") or "")
                return out

            return [None] * len(blocks)

        except urllib.error.HTTPError as e:
            if e.code == 429:
                retry = int(e.headers.get("Retry-After", (2 ** attempt) * 5))
                time.sleep(retry)
                continue
            if e.code in (500, 503):
                time.sleep(3 * (attempt + 1))
                continue
            return [None] * len(blocks)
        except (json.JSONDecodeError, KeyError, IndexError):
            # Model returned unexpected format — retry once then give up
            if attempt < 2:
                time.sleep(2)
                continue
            return [None] * len(blocks)
        except Exception:
            if attempt < 4:
                time.sleep(3 * (attempt + 1))
            continue

    return [None] * len(blocks)


# ── Page rendering ─────────────────────────────────────────────────────────────

def _page_to_png_b64(page: fitz.Page, dpi: int = 150) -> str:
    """Render PDF page to PNG and return base64-encoded string."""
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    return base64.b64encode(pix.tobytes("png")).decode()


def _apply_translations(page: fitz.Page, blocks: list[dict],
                         translations: list[Optional[str]]) -> None:
    """Draw white rects over original text, insert Polish translations."""
    ffile_r = FONT_REGULAR
    ffile_b = FONT_BOLD if FONT_BOLD else FONT_REGULAR

    for blk, pl_text in zip(blocks, translations):
        if pl_text is None or not pl_text.strip():
            continue  # translation failed — leave original untouched

        rect = fitz.Rect(blk["bbox"])

        # Cover original text (append to content stream → renders on top)
        page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)

        # Insert translation
        ffile = ffile_b if blk["bold"] else ffile_r
        fname = "arialb" if blk["bold"] else "arialu"
        rgb   = _color_to_rgb(blk["color"])

        for scale in [1.0, 0.93, 0.86, 0.79, 0.72, 0.65]:
            size = max(5.5, blk["size"] * scale)
            try:
                rc = page.insert_textbox(
                    rect, pl_text,
                    fontsize=size, fontfile=ffile, fontname=fname,
                    color=rgb, align=0, overlay=True,
                )
                if rc >= 0:
                    break
            except Exception:
                break


# ── Public API ─────────────────────────────────────────────────────────────────

def translate_pdf(
    pdf_path: str,
    output_path: str,
    lang_to: str = "polski",
    provider: str = "gemini",
    api_key: str = "",
    model: str = "gemini-3.1-flash-lite-preview",
    workers: int = 6,
    dpi: int = 100,
    progress_callback: Optional[Callable[[str, int, str], None]] = None,
) -> str:
    """Translate a PDF preserving its layout using Gemini multimodal.

    Each page is rendered as an image and sent to Gemini together with
    the extracted text block list. Gemini translates all blocks with full
    visual context in a single API call per page.

    Args:
        pdf_path:  Input PDF.
        output_path: Output translated PDF.
        lang_to:   Target language.
        provider:  'gemini' (recommended) or 'mistral' (text-only fallback).
        api_key:   Gemini API key.
        model:     Gemini model name.
        workers:   Parallel page workers.
        dpi:       Render DPI for page images sent to Gemini (150 default).
        progress_callback: fn(stage, pct, message).

    Returns:
        Absolute path to the output PDF.
    """
    if not FONT_REGULAR:
        raise RuntimeError(
            "No Unicode font found. Install Liberation Fonts or Arial Unicode."
        )
    if not api_key:
        raise RuntimeError("API key required for pdf_translator.")

    def _cb(pct: int, msg: str) -> None:
        if progress_callback:
            progress_callback("translate_pdf", pct, msg)

    src = fitz.open(pdf_path)
    total = len(src)
    _cb(0, f"PDF→PDF: {total} stron | Gemini {model} | {dpi} DPI")

    # Step 1: Extract text blocks (local, fast)
    _cb(2, "Analiza bloków tekstowych...")
    all_blocks = [_extract_blocks(src[i]) for i in range(total)]
    text_pages = sum(1 for b in all_blocks if b)
    _cb(5, f"Znaleziono {text_pages}/{total} stron z tekstem")

    # Step 2: Translate pages in parallel (image → Gemini → translations)
    translations: list[list] = [[] for _ in range(total)]
    completed = [0]

    def translate_one(page_idx: int):
        blocks = all_blocks[page_idx]
        if not blocks:
            return page_idx, []

        # Render page image
        png_b64 = _page_to_png_b64(src[page_idx], dpi=dpi)

        result = _translate_page_gemini(
            png_b64, blocks, lang_to, api_key, model
        )
        return page_idx, result

    _cb(5, f"Tłumaczenie ({workers} workerów)...")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(translate_one, i): i for i in range(total)}
        for future in as_completed(futures):
            idx, result = future.result()
            translations[idx] = result
            completed[0] += 1
            pct = 5 + int(completed[0] / total * 80)
            ok  = sum(1 for t in result if t is not None)
            _cb(pct, f"Strona {idx+1}: {ok}/{len(all_blocks[idx])} bloków | "
                     f"postęp {completed[0]}/{total}")

    src.close()

    # Step 3: Build output PDF
    _cb(85, "Składanie PDF z tłumaczeniem...")
    src2 = fitz.open(pdf_path)
    out_doc = fitz.open()
    out_doc.insert_pdf(src2)

    applied = skipped = 0
    for i in range(total):
        page   = out_doc[i]
        blocks = all_blocks[i]
        transl = translations[i]
        if blocks and transl:
            _apply_translations(page, blocks, transl)
            applied += sum(1 for t in transl if t)
            skipped += sum(1 for t in transl if not t)

    out_doc.save(output_path, garbage=4, deflate=True, clean=True)
    out_doc.close()
    src2.close()

    _cb(100, f"Gotowe → {Path(output_path).name} "
             f"({applied} bloków przetłumaczonych, {skipped} pominięto)")
    return output_path
