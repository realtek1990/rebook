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
                "timeout": 120
            }
            if api_base:
                kwargs["api_base"] = api_base
                
            response = litellm.completion(**kwargs)
            msg = response.choices[0].message
            # Gemini 3+ uses thinking_blocks — content may be None
            text_out = msg.content
            if not text_out and hasattr(msg, 'thinking_blocks') and msg.thinking_blocks:
                # Extract text from last thinking block
                for tb in reversed(msg.thinking_blocks):
                    raw = tb.get('thinking', '') if isinstance(tb, dict) else str(tb)
                    # thinking field may be JSON like {"text": "..."}
                    if raw.startswith('{'):
                        try:
                            import json as _json
                            text_out = _json.loads(raw).get('text', raw)
                        except Exception:
                            text_out = raw
                    else:
                        text_out = raw
                    if text_out:
                        break
            if not text_out:
                raise RuntimeError("AI returned empty response")
            return text_out.strip()
            
        except litellm.RateLimitError as e:
            if attempt < retries - 1:
                time.sleep(10 * (attempt + 1))
                continue
            raise  # propagate — caller must retry
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(5)
                continue
            raise  # propagate — caller must retry
            
    raise RuntimeError("All retries exhausted in process_mega_block")


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
    
    with ThreadPoolExecutor(max_workers=30) as executor:
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
                
        # Track which segments failed so we can retry them
        failed_indices = []
        for future in as_completed(futures):
            i, original = futures[future]
            try:
                result = future.result()
                # INTEGRITY CHECK: if AI returned empty/garbage, mark as failed
                if result and len(result.strip()) > 20 and not result.strip().startswith('[BŁĄD'):
                    result_parts[i] = result
                else:
                    failed_indices.append(i)
            except Exception as e:
                failed_indices.append(i)
                
            done_count += 1
            if progress_callback:
                progress_callback(done_count, total, f"{mode_str} bloku {done_count}/{total} (~{len(original)//1000}K znaków)...")

    # ═══ RETRY FAILED SEGMENTS (AGGRESSIVE — 10 ROUNDS) ═══
    # ZERO TOLERANCE: every segment MUST be translated. No silent fallbacks.
    MAX_RETRY_ROUNDS = 10
    if failed_indices:
        if progress_callback:
            progress_callback(total, total, f"🔄 Ponawiam {len(failed_indices)} nieudanych segmentów...")
        
        for retry_round in range(MAX_RETRY_ROUNDS):
            if not failed_indices:
                break
            still_failing = []
            # Exponential backoff between rounds
            if retry_round > 0:
                wait = min(30, 3 * (2 ** retry_round))
                if progress_callback:
                    progress_callback(total, total, f"⏳ Czekam {wait}s przed rundą {retry_round+1}...")
                time.sleep(wait)

            for i in failed_indices:
                original_text = '\n'.join(b["content"] for b in mega_blocks[i])
                if progress_callback:
                    progress_callback(total, total, f"🔄 Ponowna próba {retry_round+1}/{MAX_RETRY_ROUNDS} segmentu {i+1}...")
                try:
                    result = process_mega_block(original_text, system_prompt)
                    if result and len(result.strip()) > 20:
                        result_parts[i] = result
                        if progress_callback:
                            progress_callback(total, total, f"✅ Segment {i+1} odzyskany w próbie {retry_round+1}!")
                    else:
                        still_failing.append(i)
                except Exception as e:
                    still_failing.append(i)
                    if progress_callback:
                        progress_callback(total, total, f"❌ Segment {i+1} — błąd: {e}")
            failed_indices = still_failing

    # ═══ FINAL INTEGRITY CHECK — HARD FAIL ═══
    # ZERO TOLERANCE: if ANY segment is missing, ABORT the entire conversion.
    # We NEVER silently insert untranslated text into the output.
    missing = [i for i, p in enumerate(result_parts) if p is None]
    if missing:
        seg_list = ', '.join(str(i+1) for i in missing[:10])
        more = f' (i {len(missing)-10} więcej)' if len(missing) > 10 else ''
        raise RuntimeError(
            f"❌ BŁĄD KRYTYCZNY: {len(missing)} segmentów nie udało się przetłumaczyć "
            f"mimo {MAX_RETRY_ROUNDS} prób!\n"
            f"Segmenty: {seg_list}{more}\n\n"
            f"Możliwe przyczyny:\n"
            f"• Problem z API (limit zapytań, timeout)\n"
            f"• Zbyt duże bloki tekstu dla wybranego modelu\n"
            f"• Niestabilne połączenie internetowe\n\n"
            f"Spróbuj ponownie lub zmień model AI w Ustawieniach."
        )

    return '\n'.join(result_parts)


# ─────────────────────────────────────────────────────────────────────────────
#  POST-TRANSLATION VERIFICATION PASS
# ─────────────────────────────────────────────────────────────────────────────

def _chunk_for_context(original: str, translated: str, max_chars: int = 800_000):
    """Split original+translated into chunks that fit in the LLM context window.
    Yields (original_chunk, translated_chunk) pairs.
    Each pair is small enough that both fit within max_chars together.
    """
    orig_lines = original.split('\n')
    trans_lines = translated.split('\n')

    # If both fit, return as single chunk
    if len(original) + len(translated) < max_chars:
        yield original, translated
        return

    # Otherwise split by approximate paragraph boundaries
    chunk_size = max_chars // 3  # leave room for prompt + response
    orig_chunks, trans_chunks = [], []

    def _split_text(text, size):
        parts = []
        current = []
        current_len = 0
        for line in text.split('\n'):
            if current_len + len(line) > size and current:
                parts.append('\n'.join(current))
                current = [line]
                current_len = len(line)
            else:
                current.append(line)
                current_len += len(line) + 1
        if current:
            parts.append('\n'.join(current))
        return parts

    o_parts = _split_text(original, chunk_size)
    t_parts = _split_text(translated, chunk_size)

    # Zip chunks; if counts differ, pair by index
    count = max(len(o_parts), len(t_parts))
    for i in range(count):
        o = o_parts[i] if i < len(o_parts) else ""
        t = t_parts[i] if i < len(t_parts) else ""
        yield o, t


def verify_translation(
    original_markdown: str,
    translated_markdown: str,
    lang_from: str = "angielski",
    lang_to: str = "polski",
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> str:
    """Post-translation verification pass.

    Sends the original and translated texts side-by-side to a large-context LLM
    (ideally Gemini Flash with 1M context) to:
    1. Detect missing segments (present in original but absent in translation)
    2. Detect untranslated passages (still in source language)
    3. Detect nonsensical content (random numbers, garbled text from OCR)
    4. Auto-fix all issues found

    Returns the verified (and if needed, repaired) translated text.
    """
    config = get_config()
    if not config.get("api_key"):
        return translated_markdown

    import litellm
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

    verify_prompt = f"""Jesteś ekspertem od kontroli jakości tłumaczeń książek.

Otrzymujesz TEKST ORYGINALNY (w języku {lang_from or 'źródłowym'}) oraz TŁUMACZENIE (w języku {lang_to}).

Twoim zadaniem jest:

1. **ZNAJDŹ BRAKUJĄCE SEGMENTY**: Porównaj oryginał z tłumaczeniem — jeśli jakikolwiek akapit, zdanie lub fragment z oryginału CAŁKOWICIE BRAKUJE w tłumaczeniu, wstaw go przetłumaczony w odpowiednie miejsce.

2. **ZNAJDŹ NIEPRZETŁUMACZONE FRAGMENTY**: Jeśli w tłumaczeniu nadal znajdują się zdania lub fragmenty w języku {lang_from or 'źródłowym'} (nieprzetłumaczone), PRZETŁUMACZ je na {lang_to}.

3. **ZNAJDŹ BŁĘDY I ARTEFAKTY**: Jeśli w tekście tłumaczenia występują:
   - Losowe cyfry lub ciągi znaków bez sensu
   - Śmieci z OCR (np. "1 2 3", "###", dziwne symbole)
   - Powtórzenia zdań
   - Niedokończone zdania
   → NAPRAW je lub USUŃ jeśli są śmieciami.

4. **ZACHOWAJ STRUKTURĘ**: Zachowaj formatowanie Markdown (nagłówki #, pogrubienia **, listy -, cytaty >, obrazy ![...](...)).

WAŻNE:
- Zwróć KOMPLETNY, POPRAWIONY tekst tłumaczenia.
- NIE dodawaj swoich komentarzy, notatek ani wyjaśnień.
- NIE usuwaj poprawnych fragmentów.
- Popraw TYLKO to co jest błędne lub brakujące.
- Jeśli tłumaczenie jest idealne, zwróć je bez zmian.

ZWRÓĆ TYLKO POPRAWIONY TEKST TŁUMACZENIA."""

    chunks = list(_chunk_for_context(original_markdown, translated_markdown))
    total_chunks = len(chunks)
    verified_parts = []

    for idx, (orig_chunk, trans_chunk) in enumerate(chunks):
        if progress_callback:
            progress_callback(idx, total_chunks,
                f"🔍 Weryfikacja segmentu {idx+1}/{total_chunks}...")

        user_message = f"""═══ TEKST ORYGINALNY ({lang_from or 'źródłowy'}) ═══

{orig_chunk}

═══ TŁUMACZENIE ({lang_to}) ═══

{trans_chunk}

═══ KONIEC ═══

Przeanalizuj i zwróć POPRAWIONĄ wersję tłumaczenia (sekcja TŁUMACZENIE). Pamiętaj o punktach 1-4 z instrukcji."""

        MAX_VERIFY_RETRIES = 10
        success = False
        for attempt in range(MAX_VERIFY_RETRIES):
            try:
                kwargs = {
                    "model": model_name,
                    "api_key": api_key,
                    "messages": [
                        {"role": "system", "content": verify_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 65536,
                    "timeout": 300,
                }
                if api_base:
                    kwargs["api_base"] = api_base

                response = litellm.completion(**kwargs)
                result = response.choices[0].message.content
                if result and len(result.strip()) > 50:
                    verified_parts.append(result.strip())
                    success = True
                    break
                else:
                    if progress_callback:
                        progress_callback(idx, total_chunks,
                            f"⚠️ Pusta odpowiedź, próba {attempt+1}/{MAX_VERIFY_RETRIES}...")
                    time.sleep(3 * (attempt + 1))
            except Exception as e:
                if progress_callback:
                    progress_callback(idx, total_chunks,
                        f"❌ Błąd weryfikacji (próba {attempt+1}/{MAX_VERIFY_RETRIES}): {e}")
                time.sleep(5 * (attempt + 1))

        if not success:
            raise RuntimeError(
                f"❌ BŁĄD KRYTYCZNY: Weryfikacja segmentu {idx+1}/{total_chunks} "
                f"nie powiodła się mimo {MAX_VERIFY_RETRIES} prób!\n\n"
                f"Spróbuj ponownie lub zmień model AI w Ustawieniach."
            )

        if progress_callback:
            progress_callback(idx + 1, total_chunks,
                f"✅ Segment {idx+1}/{total_chunks} zweryfikowany")

    return '\n\n'.join(verified_parts)

