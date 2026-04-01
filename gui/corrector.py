"""
ReBook GUI — AI engine for book correction & translation.
Uses native API calls (no LiteLLM dependency).
Supports: Gemini (default), OpenAI, Mistral, Grok, any OpenAI-compatible API.
"""
import json
import os
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Callable, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

WORKSPACE_DIR = Path.home() / ".rebook"
CONFIG_FILE = WORKSPACE_DIR / "config.json"
MEGA_BLOCK_CHARS = 5000

# ─── Config ──────────────────────────────────────────────────────────────────

def get_config() -> dict:
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


# ─── Prompts ─────────────────────────────────────────────────────────────────

LANG_NAMES = {
    "pl": "Polish", "en": "English", "de": "German", "fr": "French",
    "es": "Spanish", "it": "Italian", "pt": "Portuguese", "nl": "Dutch",
    "cs": "Czech", "sk": "Slovak", "uk": "Ukrainian", "ru": "Russian",
    "ja": "Japanese", "ko": "Korean", "zh": "Chinese", "ar": "Arabic",
    "tr": "Turkish", "sv": "Swedish", "da": "Danish", "no": "Norwegian",
    "fi": "Finnish", "hu": "Hungarian", "ro": "Romanian", "bg": "Bulgarian",
    "hr": "Croatian", "el": "Greek", "he": "Hebrew", "th": "Thai",
    "vi": "Vietnamese", "id": "Indonesian", "ms": "Malay", "hi": "Hindi",
}

def get_system_prompt(use_translate: bool, lang_to: str, lang_from: str) -> str:
    if use_translate:
        to_name = LANG_NAMES.get(lang_to, lang_to)
        from_name = LANG_NAMES.get(lang_from, lang_from) if lang_from else "the source language"
        return f"""You are a professional book translator. Translate the following text from {from_name} into {to_name}.

Rules:
1. Translate in a natural, literary style — maintain the highest grammatical correctness and the author's original context.
2. Translate ABSOLUTELY EVERYTHING into {to_name} — including titles, headings, quotes, captions. Leave nothing in the source language.
3. PRESERVE Markdown formatting (headings #, bold **, lists -, blockquotes >). Do not alter their syntax.
4. HEADINGS (lines starting with #): A heading should be a SHORT title only (max 1-2 sentences). If a long paragraph follows #, convert it to bold text (**text**) instead.
5. CLEAN ARTIFACTS: Remove any technical junk — XML declarations, HTML tags, DOCTYPE, HTML entities — leave only clean text.
6. PRESERVE PARAGRAPH STRUCTURE: Keep the exact same paragraph breaks as in the source.
7. Return ONLY the translation result. Do NOT include introductions, comments, or notes."""
    else:
        return """You are an expert in correcting OCR-scanned text. Your only task is to fix errors from scanning and text recognition.

Rules:
1. Merge split words (e.g. "sep arated" -> "separated")
2. Remove random bold markers (** inside words that don't make sense)
3. Fix punctuation errors
4. Fix obvious OCR typos (e.g. "rn" instead of "m", "1" instead of "l")
5. CLEAN ARTIFACTS: Remove any XML/HTML tags, DOCTYPE, entities — leave only clean text.
6. Do NOT change content, do NOT add anything, do NOT paraphrase
7. Preserve Markdown formatting (headings #, lists -, blockquotes >) if present
8. Return ONLY the corrected text, without comments or notes"""


# ─── API Callers ─────────────────────────────────────────────────────────────

def _call_gemini(api_key: str, model: str, system_prompt: str, text: str) -> tuple[str, int]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": system_prompt + "\n\n" + text}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 8192}
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    if "candidates" in result and result["candidates"]:
        content = result["candidates"][0]["content"]["parts"][0]["text"]
        tokens = result.get("usageMetadata", {}).get("totalTokenCount", 0)
        return content.strip(), tokens
    raise RuntimeError(f"No candidates: {json.dumps(result)[:200]}")


def _call_openai_compat(api_key: str, model: str, system_prompt: str, text: str, base_url: str = "") -> tuple[str, int]:
    url = base_url or "https://api.openai.com/v1/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ],
        "temperature": 0.1,
        "max_tokens": 8192,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    })
    with urllib.request.urlopen(req, timeout=600) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    if "choices" in result:
        content = result["choices"][0]["message"]["content"]
        tokens = result.get("usage", {}).get("total_tokens", 0)
        return content.strip(), tokens
    raise RuntimeError(f"No choices: {json.dumps(result)[:200]}")


PROVIDER_URLS = {
    "gemini": None,
    "openai": "https://api.openai.com/v1/chat/completions",
    "mistral": "https://api.mistral.ai/v1/chat/completions",
    "grok": "https://api.x.ai/v1/chat/completions",
}


def process_mega_block(text: str, system_prompt: str, retries: int = 3) -> str:
    """Send a block of text to AI for processing."""
    if not text.strip():
        return text

    config = get_config()
    provider = config.get("llm_provider", "").strip().lower()
    api_key = config.get("api_key", "").strip()
    model = config.get("model_name", "").strip()

    if not api_key or not model:
        return text

    for attempt in range(retries):
        try:
            if provider == "gemini":
                content, _ = _call_gemini(api_key, model, system_prompt, text)
            else:
                base_url = config.get("base_url", "").strip() or PROVIDER_URLS.get(provider, "")
                content, _ = _call_openai_compat(api_key, model, system_prompt, text, base_url)
            return content

        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            if e.code == 429 and attempt < retries - 1:
                time.sleep(15 * (attempt + 1))
                continue
            if attempt >= retries - 1:
                return f"\n\n[API ERROR - HTTP {e.code}]: {body[:100]}\n\n" + text
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(5)
                continue
            return f"\n\n[API ERROR]: {e}\n\n" + text

    return text


# ─── Text Processing ────────────────────────────────────────────────────────

def split_into_blocks(markdown_text: str) -> list[dict]:
    lines = markdown_text.split('\n')
    blocks = []
    current_text = []

    for line in lines:
        stripped = line.strip()
        if (stripped.startswith('#') or
            stripped.startswith('![') or
            stripped == '---' or
            stripped == '***' or
            stripped == ''):
            if current_text:
                blocks.append({"type": "text", "content": '\n'.join(current_text)})
                current_text = []
            blocks.append({"type": "structural", "content": line})
        else:
            current_text.append(line)

    if current_text:
        blocks.append({"type": "text", "content": '\n'.join(current_text)})

    return blocks


def group_into_mega_blocks(blocks: list[dict], threshold: int = MEGA_BLOCK_CHARS) -> list[list[dict]]:
    mega_blocks = []
    current_mega = []
    current_size = 0

    for block in blocks:
        block_size = len(block["content"])
        if current_size + block_size > threshold and current_mega:
            mega_blocks.append(current_mega)
            current_mega = [block]
            current_size = block_size
        else:
            current_mega.append(block)
            current_size += block_size

    if current_mega:
        mega_blocks.append(current_mega)

    return mega_blocks


def is_api_available() -> bool:
    config = get_config()
    return bool(config.get("api_key") and config.get("model_name"))


def get_available_models() -> list[str]:
    config = get_config()
    m = config.get("model_name")
    if m:
        return [m]
    return []


def correct_markdown(
    markdown: str,
    use_translate: bool = False,
    lang_to: str = "pl",
    lang_from: str = "",
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> str:
    config = get_config()
    workers = int(config.get("workers", 30))

    blocks = split_into_blocks(markdown)
    mega_blocks = group_into_mega_blocks(blocks, MEGA_BLOCK_CHARS)

    total = len(mega_blocks)
    result_parts = [None] * total
    system_prompt = get_system_prompt(use_translate, lang_to, lang_from)

    done_count = 0
    mode_str = "Translation" if use_translate else "Correction"

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {}
        for i, mega_group in enumerate(mega_blocks):
            combined_text = '\n'.join(b["content"] for b in mega_group)
            text_only = "".join(b["content"] for b in mega_group if b["type"] == "text")

            if len(text_only.strip()) > 50:
                future = executor.submit(process_mega_block, combined_text, system_prompt)
                futures[future] = (i, combined_text)
                if progress_callback:
                    progress_callback(done_count, total, f"Queued block {i+1}...")
            else:
                result_parts[i] = combined_text
                done_count += 1
                if progress_callback:
                    progress_callback(done_count, total, f"{mode_str} block {done_count}/{total} (empty)")

        for future in as_completed(futures):
            i, original = futures[future]
            try:
                result_parts[i] = future.result()
            except Exception:
                result_parts[i] = original

            done_count += 1
            if progress_callback:
                progress_callback(done_count, total, f"{mode_str} block {done_count}/{total} (~{len(original)//1000}K chars)")

    return '\n'.join(r for r in result_parts if r)
