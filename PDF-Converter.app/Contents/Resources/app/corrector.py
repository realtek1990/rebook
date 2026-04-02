import json
import os
import time
from pathlib import Path
from typing import Callable, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# KRYTYCZNE: Wymuszenie dłuższego timeoutu HTTP dla biblioteki openai.
# GLM-5.1 (reasoning) potrzebuje 2+ minuty na blok 3000 znaków.
# Domyślny timeout openai to 120s, co powoduje ciche ReadTimeout + retry w nieskończoność.
os.environ['OPENAI_TIMEOUT'] = '600'

WORKSPACE_DIR = Path.home() / ".pdf2epub-app"
CONFIG_FILE = WORKSPACE_DIR / "config.json"

def get_config() -> dict:
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def get_system_prompt(use_translate: bool, lang_to: str, lang_from: str) -> str:
    if use_translate:
        frm = f"z języka: {lang_from}" if lang_from else "z języka źródłowego"
        to = lang_to if lang_to else "polski"
        return f"""Jesteś profesjonalnym tłumaczem książek. Twoim zadaniem jest przetłumaczenie poniższego tekstu {frm} na język {to}.

Zasady:
1. Tekst ma być przetłumaczony w sposób naturalny dla czytelnika z zachowaniem najwyższej poprawności oraz oryginalnego kontekstu wyjściowego autora.
2. Przetłumacz ABSOLUTNIE WSZYSTKO na język {to} — w tym tytuły, nagłówki, cytaty, podpisy i wszelkie fragmenty w języku obcym. Nie zostawiaj niczego po angielsku.
3. ZACHOWAJ FORMATOWANIE Markdown (nagłówki #, pogrubienia **, listy -, cytaty >). Nie zmieniaj ich składni.
4. NAGŁÓWKI (linie zaczynające się od #): Nagłówek to TYLKO krótki tytuł rozdziału lub sekcji (max 1-2 zdania). Jeśli widzisz że po znaku # znajduje się długi akapit (ponad 2 zdania), zamień go na zwykły tekst pogrubiony (**tekst**) — to ewidentny błąd formatowania z OCR.
5. WYCZYŚĆ ARTEFAKTY: Jeśli w tekście występują śmieci techniczne takie jak: deklaracje XML (<?xml ...?>), znaczniki HTML (<div>, <span>, itp.), kody DOCTYPE, encje HTML (&amp; &nbsp;) — USUŃ JE i zostaw tylko czysty tekst.
6. Zwróć TYLKO wynik tłumaczenia. Nie dołączaj swoich notatek, wstępów ani komentarzy typu „Oto tłumaczenie:" czy „Zachowałem formatowanie".
"""
    else:
        return """Jesteś ekspertem od korekty tekstu polskiego z OCR. Twoim jedynym zadaniem jest poprawienie błędów powstałych podczas skanowania i rozpoznawania tekstu (OCR).

Zasady:
1. Połącz rozdzielone wyrazy (np. "roz dzielony" -> "rozdzielony")
2. Usuń losowe pogrubienia (znaczniki ** wewnątrz słów lub zdań, które nie mają sensu)
3. Popraw błędy interpunkcji
4. Popraw oczywiste literówki OCR (np. "rn" zamiast "m", "1" zamiast "l")
5. NIE zmieniaj treści, NIE dodawaj niczego, NIE parafrazuj
6. Zachowaj formatowanie markdown (nagłówki #, listy -, cytaty >) jeśli istnieją
7. Zwróć TYLKO poprawiony tekst, bez komentarzy ani przemyśleń"""


def process_mega_block(text: str, system_prompt: str, retries: int = 3) -> str:
    """Send a mega-block of text to AI via LiteLLM."""
    if not text.strip():
        return text
        
    config = get_config()
    if config.get("llm_provider", "Opcjonalne API") == "Brak" or not config.get("api_key"):
        return text

    import litellm
    
    # Przezornie usuwamy stdout littering od litellm
    litellm.suppress_debug_info = True

    model_name = config.get("model_name", "gpt-4o-mini").strip().lower()
    provider = config.get("llm_provider", "").strip().lower()
    
    api_base = None
    if provider == "zhipuai":
        model_name = f"openai/{model_name}"
        api_base = "https://open.bigmodel.cn/api/coding/paas/v4/"
    elif provider == "mistral":
        model_name = f"mistral/{model_name}"
    elif provider and provider != "brak" and "/" not in model_name:
        model_name = f"{provider}/{model_name}"
        
    api_key = config.get("api_key", "").strip()
    
    for attempt in range(retries):
        try:
            kwargs = {
                "model": model_name,
                "api_key": api_key,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                "temperature": 0.1,
                "max_tokens": 16384,
                "timeout": 600
            }
            if api_base:
                kwargs["api_base"] = api_base
                
            response = litellm.completion(**kwargs)
            return response.choices[0].message.content.strip()
            
        except litellm.RateLimitError as e:
            if attempt < retries - 1:
                time.sleep(10 * (attempt + 1))
                continue
            return f"\n\n[BŁĄD Z.AI - RATE LIMIT (Zbyt dużo zapytań!)]: {e}\n\n" + text
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(5)
                continue
            return f"\n\n[BŁĄD Z.AI - INNY]: {e}\n\n" + text
            
    return text


def split_into_blocks(markdown: str) -> list[dict]:
    """Split markdown into typed blocks. Images get their own 'image' type
    so they are NEVER sent to the AI and always preserved in-place."""
    lines = markdown.split('\n')
    blocks = []
    current_text = []
    
    for line in lines:
        stripped = line.strip()
        # Images — MUST be preserved verbatim (never sent to AI)
        if stripped.startswith('!['):
            if current_text:
                blocks.append({"type": "text", "content": '\n'.join(current_text)})
                current_text = []
            blocks.append({"type": "image", "content": line})
        elif (stripped.startswith('#') or 
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

MEGA_BLOCK_CHARS = 5000

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
    if m: return [m]
    return []

def correct_markdown(
    markdown: str,
    use_translate: bool = False,
    lang_to: str = "polski",
    lang_from: str = "",
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> str:
    blocks = split_into_blocks(markdown)
    mega_blocks = group_into_mega_blocks(blocks, MEGA_BLOCK_CHARS)
    
    total = len(mega_blocks)
    result_parts = [None] * total
    system_prompt = get_system_prompt(use_translate, lang_to, lang_from)

    done_count = 0
    mode_str = "Tłumaczenie" if use_translate else "Korekcja"
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {}
        for i, mega_group in enumerate(mega_blocks):
            group_text = []
            for block in mega_group:
                group_text.append(block["content"])
            combined_text = '\n'.join(group_text)
            
            # Only send text-heavy blocks to AI; images/structural pass through
            text_only = "".join(b["content"] for b in mega_group if b["type"] == "text")
            has_only_images = all(b["type"] in ("image", "structural") for b in mega_group)
            
            if has_only_images or len(text_only.strip()) <= 50:
                # Pass-through: images, structural elements, tiny text
                result_parts[i] = combined_text
                done_count += 1
                if progress_callback:
                    progress_callback(done_count, total, f"{mode_str} bloku {done_count}/{total} (Pass-through)...")
            else:
                future = executor.submit(process_mega_block, combined_text, system_prompt)
                futures[future] = (i, combined_text)
                if progress_callback:
                    progress_callback(done_count, total, f"Zlecono do API paczkę numer {i+1}/{total}...")
                
        for future in as_completed(futures):
            i, original = futures[future]
            try:
                result = future.result()
                # INTEGRITY CHECK: if AI returned empty/garbage, keep original
                if result and len(result.strip()) > 20:
                    result_parts[i] = result
                else:
                    result_parts[i] = original
            except Exception as e:
                result_parts[i] = original
                
            done_count += 1
            if progress_callback:
                progress_callback(done_count, total, f"{mode_str} bloku {done_count}/{total} (~{len(original)//1000}K znaków)...")

    # ═══ FINAL INTEGRITY CHECK ═══
    # Ensure EVERY segment has content — no gaps allowed
    missing = [i for i, p in enumerate(result_parts) if p is None]
    if missing:
        # Recover missing segments from original mega-blocks
        for i in missing:
            original_text = '\n'.join(b["content"] for b in mega_blocks[i])
            result_parts[i] = original_text
        if progress_callback:
            progress_callback(total, total,
                f"⚠️ UWAGA: {len(missing)} brakujących segmentów odzyskano z oryginału")

    return '\n'.join(result_parts)
