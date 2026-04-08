"""ReBook — Image Translation Module (Nano Banana 2 / Gemini Image API).

Translates text embedded in book illustrations, covers, and diagrams
using Google's native image generation/editing model.

Requires: google-genai, Pillow
Uses the same Gemini API key as the text translation pipeline.
"""
import base64
import io
import json
import os
import time
from pathlib import Path
from typing import Callable, Optional

import sys as _sys
if _sys.platform == "win32":
    WORKSPACE_DIR = Path.home() / ".rebook"
else:
    WORKSPACE_DIR = Path.home() / ".pdf2epub-app"
CONFIG_FILE = WORKSPACE_DIR / "config.json"

# Nano Banana 2 — best for high-fidelity text rendering + editing
IMAGE_MODEL = "gemini-3.1-flash-image-preview"


def _get_config() -> dict:
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _has_text_in_image(image_bytes: bytes, api_key: str) -> tuple[bool, str]:
    """Use Gemini vision to detect if an image contains readable text.
    Returns (has_text, extracted_text).
    """
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    b64 = base64.b64encode(image_bytes).decode("utf-8")
    mime = "image/png" if image_bytes[:4] == b'\x89PNG' else "image/jpeg"

    response = client.models.generate_content(
        model="gemini-2.5-flash",  # use standard vision model for OCR
        contents=[
            {"text": "Does this image contain any readable text (words, titles, labels, captions)? "
                     "If YES, extract ALL text you can read. "
                     "Respond in JSON: {\"has_text\": true/false, \"text\": \"extracted text here\"}"},
            {"inline_data": {"mime_type": mime, "data": b64}},
        ],
    )

    try:
        raw = response.text.strip()
        # Clean potential markdown code fences
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        data = json.loads(raw)
        return data.get("has_text", False), data.get("text", "")
    except Exception:
        # Fallback: if response mentions text, assume there is some
        return "true" in response.text.lower(), response.text


def translate_image(
    image_bytes: bytes,
    lang_from: str = "angielski",
    lang_to: str = "polski",
    api_key: str = "",
    context: str = "",
) -> Optional[bytes]:
    """Translate text in an image to the target language using Nano Banana 2.

    Args:
        image_bytes: Raw bytes of the source image.
        lang_from: Source language name.
        lang_to: Target language name.
        api_key: Gemini API key.
        context: Optional context about the image (e.g. book title, chapter).

    Returns:
        Translated image bytes (PNG), or None if no text found / translation failed.
    """
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    mime = "image/png" if image_bytes[:4] == b'\x89PNG' else "image/jpeg"

    context_hint = f"\nKontekst: ten obraz pochodzi z książki. {context}" if context else ""

    prompt = (
        f"Ten obraz zawiera tekst w języku {lang_from}. "
        f"Przetłumacz ABSOLUTNIE CAŁY tekst widoczny na obrazie na język {lang_to} — "
        f"w tym tytuły, nagłówki, podpisy, etykiety diagramów, tekst na okładce. "
        f"NIE zostawiaj ŻADNEGO tekstu w języku {lang_from}. "
        f"Zachowaj identyczny układ graficzny, kolory, czcionki i styl — "
        f"zmień TYLKO tekst na przetłumaczony."
        f"{context_hint}"
    )

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=IMAGE_MODEL,
                contents=[
                    prompt,
                    types.Part.from_bytes(data=image_bytes, mime_type=mime),
                ],
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                ),
            )

            # Extract image from response
            for part in response.candidates[0].content.parts:
                if part.inline_data is not None:
                    return part.inline_data.data

            # No image returned
            return None

        except Exception as e:
            if attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            raise


def process_book_images(
    images: dict[str, bytes],
    lang_from: str = "angielski",
    lang_to: str = "polski",
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> dict[str, bytes]:
    """Process all images from a book, translating those containing text.

    Args:
        images: Dict of {filename: image_bytes}.
        lang_from: Source language.
        lang_to: Target language.
        progress_callback: fn(current, total, message).

    Returns:
        Dict of {filename: translated_image_bytes} for images that were translated.
        Original images without text are NOT included in the result.
    """
    config = _get_config()
    api_key = config.get("api_key", "").strip()
    provider = config.get("llm_provider", "").strip().lower()

    # Image translation only works with Gemini API
    if not api_key or provider not in ("gemini", "google", ""):
        if progress_callback:
            progress_callback(0, 0, "⚠️ Tłumaczenie obrazów wymaga klucza Gemini API")
        return {}

    translated = {}
    total = len(images)

    for idx, (filename, img_bytes) in enumerate(images.items()):
        if progress_callback:
            progress_callback(idx, total, f"🔍 Analiza obrazu {idx+1}/{total}: {filename}")

        # Skip tiny images (icons, decorations)
        if len(img_bytes) < 5000:
            continue

        try:
            # Step 1: Check if image has text
            has_text, extracted = _has_text_in_image(img_bytes, api_key)

            if not has_text or len(extracted.strip()) < 5:
                if progress_callback:
                    progress_callback(idx + 1, total,
                        f"⏭️ {filename} — brak tekstu, pomijam")
                continue

            if progress_callback:
                progress_callback(idx, total,
                    f"🎨 Tłumaczenie obrazu {idx+1}/{total}: {filename} "
                    f"(znaleziono tekst: {extracted[:50]}...)")

            # Step 2: Translate
            result = translate_image(
                img_bytes,
                lang_from=lang_from,
                lang_to=lang_to,
                api_key=api_key,
                context=f"Tekst znaleziony: {extracted[:200]}",
            )

            if result and len(result) > 1000:
                translated[filename] = result
                if progress_callback:
                    progress_callback(idx + 1, total,
                        f"✅ {filename} przetłumaczony ({len(result)//1024} KB)")
            else:
                if progress_callback:
                    progress_callback(idx + 1, total,
                        f"⚠️ {filename} — nie udało się przetłumaczyć")

        except Exception as e:
            if progress_callback:
                progress_callback(idx + 1, total,
                    f"❌ {filename} — błąd: {e}")

        # Rate limiting
        time.sleep(1)

    return translated
