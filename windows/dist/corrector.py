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
2. Przetłumacz ABSOLUTNIE WSZYSTKO na język {to} — w tym nagłówki, cytaty, podpisy, dialogi i wszelkie fragmenty w języku obcym. NIE zostawiaj niczego w oryginalnym języku. Jedyny wyjątek: tytuły książek w cudzysłowach i nazwy własne organizacji.
3. ZACHOWAJ FORMATOWANIE Markdown (nagłówki #, pogrubienia **, listy -, cytaty >). Nie zmieniaj ich składni.
4. NAGŁÓWKI ROZDZIAŁÓW: Jeśli tekst zawiera nagłówki typu "Chapter X — Title", "Introduction", "Foreword", "Preface", "Appendix" — przetłumacz je i oznacz jako nagłówki Markdown:
   - "Chapter 1—My Life" → "# Rozdział 1 — Moje życie"
   - "Introduction" → "# Wprowadzenie"
   - "Foreword" → "# Przedmowa"
5. NIE ŁĄCZ i NIE POMIJAJ akapitów. Każdy akapit z oryginału MUSI pojawić się w tłumaczeniu. Nie skracaj tekstu.
6. NAGŁÓWKI (linie zaczynające się od #): Nagłówek to TYLKO krótki tytuł rozdziału lub sekcji (max 1-2 zdania). Jeśli widzisz że po znaku # znajduje się długi akapit (ponad 2 zdania), zamień go na zwykły tekst pogrubiony (**tekst**) — to ewidentny błąd formatowania z OCR.
7. WYCZYŚĆ ARTEFAKTY: Jeśli w tekście występują śmieci techniczne takie jak: deklaracje XML (<?xml ...?>), znaczniki HTML (<div>, <span>, itp.), kody DOCTYPE, encje HTML (&amp; &nbsp;) — USUŃ JE i zostaw tylko czysty tekst.
8. Zwróć TYLKO wynik tłumaczenia. Nie dołączaj swoich notatek, wstępów ani komentarzy typu „Oto tłumaczenie:" czy „Zachowałem formatowanie".
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

    # ═══ RETRY FAILED SEGMENTS — WITH AUTO SUB-CHUNKING ═══
    # Strategy: after 3 failures at full size, split the chunk into smaller pieces
    MAX_RETRY_ROUNDS = 10
    SUB_CHUNK_THRESHOLD = 3  # switch to sub-chunking after this many failures

    if failed_indices:
        if progress_callback:
            progress_callback(total, total, f"🔄 Ponawiam {len(failed_indices)} nieudanych segmentów...")
        
        failure_counts = {i: 0 for i in failed_indices}

        for retry_round in range(MAX_RETRY_ROUNDS):
            if not failed_indices:
                break
            still_failing = []
            if retry_round > 0:
                wait = min(30, 3 * (2 ** retry_round))
                if progress_callback:
                    progress_callback(total, total, f"⏳ Czekam {wait}s przed rundą {retry_round+1}...")
                time.sleep(wait)

            # Adaptive timeout: longer for later retries
            adaptive_timeout = min(600, 120 + retry_round * 60)

            for i in failed_indices:
                original_text = '\n'.join(b["content"] for b in mega_blocks[i])
                failure_counts[i] = failure_counts.get(i, 0) + 1

                # After SUB_CHUNK_THRESHOLD failures → split into sub-chunks
                if failure_counts[i] >= SUB_CHUNK_THRESHOLD:
                    if progress_callback:
                        progress_callback(total, total,
                            f"✂️ Segment {i+1}: dzielę na mniejsze części (próba {retry_round+1})...")
                    try:
                        sub_result = _translate_with_sub_chunks(
                            original_text, system_prompt, adaptive_timeout)
                        if sub_result and len(sub_result.strip()) > 20:
                            result_parts[i] = sub_result
                            if progress_callback:
                                progress_callback(total, total,
                                    f"✅ Segment {i+1} odzyskany przez sub-chunking!")
                            continue
                    except Exception as e:
                        still_failing.append(i)
                        if progress_callback:
                            progress_callback(total, total,
                                f"❌ Segment {i+1} sub-chunking: {e}")
                        continue

                # Normal retry
                if progress_callback:
                    progress_callback(total, total,
                        f"🔄 Próba {retry_round+1}/{MAX_RETRY_ROUNDS} segmentu {i+1} (timeout={adaptive_timeout}s)...")
                try:
                    result = process_mega_block(original_text, system_prompt, retries=1)
                    if result and len(result.strip()) > 20:
                        result_parts[i] = result
                        if progress_callback:
                            progress_callback(total, total,
                                f"✅ Segment {i+1} odzyskany w próbie {retry_round+1}!")
                    else:
                        still_failing.append(i)
                except Exception as e:
                    still_failing.append(i)
                    if progress_callback:
                        progress_callback(total, total, f"❌ Segment {i+1} — błąd: {e}")
            failed_indices = still_failing

    # ═══ FINAL INTEGRITY CHECK — HARD FAIL ═══
    missing = [i for i, p in enumerate(result_parts) if p is None]
    if missing:
        seg_list = ', '.join(str(i+1) for i in missing[:10])
        more = f' (i {len(missing)-10} więcej)' if len(missing) > 10 else ''
        raise RuntimeError(
            f"❌ BŁĄD KRYTYCZNY: {len(missing)} segmentów nie udało się przetłumaczyć "
            f"mimo {MAX_RETRY_ROUNDS} prób!\n"
            f"Segmenty: {seg_list}{more}\n\n"
            f"Spróbuj ponownie lub zmień model AI w Ustawieniach."
        )

    # ═══ POST-TRANSLATION QUALITY GATE ═══
    # Check each chunk: if >30% lines look like source language, re-translate
    # FIX: Gate runs whenever translating — lang_from may be empty (auto-detect)
    if use_translate:
        if progress_callback:
            progress_callback(total, total, "🔬 Kontrola jakości tłumaczenia...")
        
        retranslate_indices = []
        for i, part in enumerate(result_parts):
            if part is None:
                continue
            eng_ratio = _source_language_ratio(part)
            if eng_ratio > 0.30:
                retranslate_indices.append((i, eng_ratio))
        
        if retranslate_indices and progress_callback:
            progress_callback(total, total,
                f"⚠️ {len(retranslate_indices)} segmentów ma >30% tekstu źródłowego — ponawiam tłumaczenie...")

        for i, ratio in retranslate_indices:
            original_text = '\n'.join(b["content"] for b in mega_blocks[i])
            if progress_callback:
                progress_callback(total, total,
                    f"🔄 Re-tłumaczenie segmentu {i+1} ({ratio:.0%} źródłowego)...")
            try:
                result = _translate_with_sub_chunks(original_text, system_prompt, 300)
                if result and len(result.strip()) > 20:
                    new_ratio = _source_language_ratio(result)
                    if new_ratio < ratio:  # only replace if actually better
                        result_parts[i] = result
                        if progress_callback:
                            progress_callback(total, total,
                                f"✅ Segment {i+1}: {ratio:.0%} → {new_ratio:.0%} źródłowego")
            except Exception as e:
                if progress_callback:
                    progress_callback(total, total,
                        f"⚠️ Re-tłumaczenie segmentu {i+1} nie powiodło się: {e}")

    return '\n'.join(p for p in result_parts if p is not None)


def _source_language_ratio(text: str) -> float:
    """Estimate what fraction of lines appear to be in English (source language)."""
    lines = [l.strip() for l in text.split('\n') if len(l.strip()) > 20]
    if not lines:
        return 0.0
    english_indicators = [' the ', ' and ', ' for ', ' that ', ' with ', ' from ',
                          ' this ', ' have ', ' are ', ' was ', ' were ', ' been ']
    eng_count = 0
    for line in lines:
        ascii_ratio = sum(1 for c in line if ord(c) < 128) / len(line)
        if ascii_ratio > 0.85 and any(w in line.lower() for w in english_indicators):
            eng_count += 1
    return eng_count / len(lines)


def _translate_with_sub_chunks(
    text: str,
    system_prompt: str,
    timeout: int = 300,
    max_sub_chunks: int = 4,
) -> str:
    """Split a large text into sub-chunks and translate each in parallel.
    Used as fallback when a full chunk repeatedly times out.
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed

    paragraphs = text.split('\n\n')
    n = max(1, len(paragraphs) // max_sub_chunks)
    sub_chunks = []
    for i in range(0, len(paragraphs), n):
        chunk = '\n\n'.join(paragraphs[i:i+n])
        if chunk.strip():
            sub_chunks.append(chunk)

    if not sub_chunks:
        return text

    results = {}
    lock = threading.Lock()

    def _translate_sub(idx, sub_text):
        # FIX Luka 4: pass adaptive timeout into litellm kwargs via env / monkey-patch
        import litellm
        litellm.suppress_debug_info = True
        config = get_config()
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
        for attempt in range(5):
            try:
                kwargs = {
                    "model": model_name,
                    "api_key": api_key,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": sub_text},
                    ],
                    "temperature": 0.1,
                    "timeout": timeout,  # ← adaptive timeout properly applied
                }
                if api_base:
                    kwargs["api_base"] = api_base
                response = litellm.completion(**kwargs)
                result = response.choices[0].message.content
                if result and len(result.strip()) > 10:
                    return result.strip()
            except Exception:
                time.sleep(3 * (attempt + 1))
        return sub_text  # fallback to original if all retries fail

    with ThreadPoolExecutor(max_workers=max_sub_chunks) as pool:
        futures = {pool.submit(_translate_sub, i, sc): i
                   for i, sc in enumerate(sub_chunks)}
        for f in as_completed(futures):
            results[futures[f]] = f.result()

    return '\n\n'.join(results[i] for i in range(len(sub_chunks)))


# ─────────────────────────────────────────────────────────────────────────────
#  POST-TRANSLATION VERIFICATION PASS
# ─────────────────────────────────────────────────────────────────────────────

def _chunk_for_context(original: str, translated: str, max_chars: int = 150_000):
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

1. **ZNAJDŹ BRAKUJĄCE SEGMENTY**: Porównaj oryginał z tłumaczeniem akapit po akapicie — jeśli jakikolwiek akapit, zdanie lub fragment z oryginału CAŁKOWICIE BRAKUJE w tłumaczeniu, wstaw go przetłumaczony w odpowiednie miejsce. Szczególnie sprawdź:
   - Nagłówki rozdziałów (np. "Chapter 1", "Introduction", "Foreword", "Appendix") — MUSZĄ być przetłumaczone (np. "Rozdział 1", "Wprowadzenie", "Przedmowa", "Aneks") i sformatowane jako nagłówki Markdown (#).
   - Cytaty i podpisy — nie mogą być pominięte.
   - Pierwsze i ostatnie zdania każdego rozdziału — najczęściej giną.

2. **ZNAJDŹ NIEPRZETŁUMACZONE FRAGMENTY**: Jeśli w tłumaczeniu nadal znajdują się zdania lub fragmenty w języku {lang_from or 'źródłowym'} (nieprzetłumaczone), PRZETŁUMACZ je na {lang_to}. Wyjątek: tytuły książek w cudzysłowach i nazwy organizacji mogą pozostać w oryginale.

3. **ZNAJDŹ BŁĘDY I ARTEFAKTY**: Jeśli w tekście tłumaczenia występują:
   - Losowe cyfry lub ciągi znaków bez sensu (nie będące datami, ISBN, numerami stron)
   - Śmieci z OCR (np. "1 2 3", "###", dziwne symbole)
   - Powtórzenia zdań lub całych akapitów
   - Niedokończone zdania (ucięte w połowie)
   - Zdania które tracą sens lub są bezsensowne
   → NAPRAW je lub USUŃ jeśli są śmieciami.

4. **ZACHOWAJ I WZMOCNIJ STRUKTURĘ**:
   - Zachowaj formatowanie Markdown (nagłówki #, pogrubienia **, listy -, cytaty >, obrazy ![...](...)).
   - Każdy nagłówek rozdziału z oryginału MUSI pojawić się w tłumaczeniu jako linia z # (np. "# Rozdział 1 — Moja praca jako ekspert od sekt").
   - Każda sekcja "Foreword", "Preface", "Introduction", "Appendix" MUSI mieć swój nagłówek #.

5. **SPRAWDŹ CIĄGŁOŚĆ**: Upewnij się, że tekst płynie naturalnie — brak nagłych przeskoków tematycznych, brak powtórzeń, brak "dziur" w narracji.

WAŻNE:
- Zwróć KOMPLETNY, POPRAWIONY tekst tłumaczenia.
- NIE dodawaj swoich komentarzy, notatek ani wyjaśnień.
- NIE usuwaj poprawnych fragmentów.
- Popraw TYLKO to co jest błędne lub brakujące.
- Jeśli tłumaczenie jest idealne, zwróć je bez zmian.

ZWRÓĆ TYLKO POPRAWIONY TEKST TŁUMACZENIA."""

    chunks = list(_chunk_for_context(original_markdown, translated_markdown))
    total_chunks = len(chunks)
    verified_parts = {}

    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed

    lock = threading.Lock()
    done_count = [0]

    def _verify_one(idx, orig_chunk, trans_chunk):
        user_message = f"""═══ TEKST ORYGINALNY ({lang_from or 'źródłowy'}) ═══

{orig_chunk}

═══ TŁUMACZENIE ({lang_to}) ═══

{trans_chunk}

═══ KONIEC ═══

Przeanalizuj i zwróć POPRAWIONĄ wersję tłumaczenia (sekcja TŁUMACZENIE). Pamiętaj o punktach 1-4 z instrukcji."""

        MAX_VERIFY_RETRIES = 10
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
                    with lock:
                        done_count[0] += 1
                        if progress_callback:
                            progress_callback(done_count[0], total_chunks,
                                f"✅ Segment {idx+1}/{total_chunks} zweryfikowany "
                                f"({done_count[0]}/{total_chunks})")
                    return result.strip()
                else:
                    time.sleep(3 * (attempt + 1))
            except Exception as e:
                if progress_callback:
                    with lock:
                        progress_callback(done_count[0], total_chunks,
                            f"❌ Segment {idx+1} próba {attempt+1}/{MAX_VERIFY_RETRIES}: {e}")
                time.sleep(5 * (attempt + 1))

        raise RuntimeError(
            f"❌ BŁĄD KRYTYCZNY: Weryfikacja segmentu {idx+1}/{total_chunks} "
            f"nie powiodła się mimo {MAX_VERIFY_RETRIES} prób!\n\n"
            f"Spróbuj ponownie lub zmień model AI w Ustawieniach."
        )

    if progress_callback:
        progress_callback(0, total_chunks,
            f"🔍 Weryfikacja {total_chunks} segmentów równolegle...")

    # Run ALL chunks in parallel (Gemini Flash: 2000 RPM, so 30 is safe)
    with ThreadPoolExecutor(max_workers=min(30, total_chunks)) as pool:
        futures = {
            pool.submit(_verify_one, i, o, t): i
            for i, (o, t) in enumerate(chunks)
        }
        for f in as_completed(futures):
            idx = futures[f]
            verified_parts[idx] = f.result()  # raises if _verify_one raised

    final_text = '\n\n'.join(verified_parts[i] for i in range(total_chunks))

    # --- POST-VERIFICATION RESILIENCE ---
    if progress_callback:
        progress_callback(total_chunks, total_chunks, "🧹 Deduplikacja i czyszczenie końcowe...")
    
    final_text = _deduplicate_markdown(final_text)
    final_text = _deep_translate_clusters(final_text, verify_prompt, model_name, api_key, api_base, progress_callback)

    return final_text


def _deduplicate_markdown(text: str) -> str:
    """Detects and removes long sequences of duplicated text or repeated overlapping
    H1 blocks that LLMs sometimes hallucinate when processing chunked documents."""
    import re
    # Usuwamy dokładnie zduplikowane sąsiedzkie bloki powtarzające ten sam # Nagłówek i to samo wnętrze.
    # Używamy heurestyki: powtarzające się H1 w relatywnie niedużym odstępie z niemal identycznym tekstem wewnątrz.
    
    # 1. Brutalne zdeduplikowanie "Przyszłość" -> "Myśli końcowe" -> "Aneks" (bolączka końcówek)
    p_end = re.compile(r'(# Przyszłość.*?)(?=# Przyszłość)', re.DOTALL)
    m_end = p_end.search(text)
    if m_end and "# Aneks" in m_end.group(1) and "# Podziękowania" in m_end.group(1):
        text = text.replace(m_end.group(1), '', 1)
        
    # 2. General H1 duplication (if between two identical H1s there is less than e.g. 5000 chars, drop it)
    lines = text.split('\n')
    headers = [i for i, l in enumerate(lines) if re.match(r'^#\s+', l)]
    
    to_delete = []
    for i in range(len(headers)-1):
        h1 = lines[headers[i]].strip()
        h2 = lines[headers[i+1]].strip()
        if h1 == h2:
            # Drop the block from headers[i] up to headers[i+1]
            to_delete.append((headers[i], headers[i+1]))
            
    if to_delete:
        final_lines = []
        skip_to = -1
        for i, l in enumerate(lines):
            if i < skip_to:
                continue
            for start, end in to_delete:
                if i == start:
                    skip_to = end
                    break
            if i >= skip_to:
                final_lines.append(l)
        text = '\n'.join(final_lines)

    return text


def _deep_translate_clusters(
    text: str,
    system_prompt: str,
    model_name: str,
    api_key: str,
    api_base: str,
    progress_callback=None
) -> str:
    """Scans for multi-line clusters of remaining source language text (e.g. English)
    that bypassed the chunk-level >30% quality gate, and translates them in parallel."""
    import litellm
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading
    import time
    import re

    lines = text.split('\n')
    eng_indicators = [' the ', ' and ', ' for ', ' that ', ' with ', ' from ', ' this ', ' have ']
    
    clusters = []
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if len(s) > 20:
            # FIX Luka 5: skip markdown image lines — never translate them
            if s.startswith('![') or s.startswith('](') or 'images/' in s:
                i += 1; continue
            ascii_ratio = sum(1 for c in s if ord(c) < 128) / len(s)
            if ascii_ratio > 0.80 and any(w in s.lower() for w in eng_indicators):
                start = i
                while i < len(lines):
                    s2 = lines[i].strip()
                    if len(s2) < 10:
                        i += 1; continue
                    ascii_r2 = sum(1 for c in s2 if ord(c) < 128) / len(s2)
                    if ascii_r2 > 0.80 and any(w in s2.lower() for w in eng_indicators):
                        i += 1
                    else:
                        break
                if i - start >= 2:
                    clusters.append((max(0, start - 2), min(len(lines), i + 2)))
        i += 1
        
    merged = []
    for s, e in sorted(clusters):
        if merged and s <= merged[-1][1] + 10:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    real_clusters = []
    for s, e in merged:
        chunk = '\n'.join(lines[s:e])
        # Filter bibliography citations
        bib_indicators = ['print.', 'isbn', 'york:', 'london:', 'press,', 'university']
        bib_ratio = sum(1 for l in lines[s:e] if any(b in l.lower() for b in bib_indicators)) / max(e-s, 1)
        # FIX Luka 5: also skip clusters that are predominantly image/link lines
        img_ratio = sum(1 for l in lines[s:e] if l.strip().startswith('![') or 'images/' in l) / max(e-s, 1)
        if bib_ratio < 0.3 and img_ratio < 0.5 and (e-s) >= 2:
            real_clusters.append((s, e, chunk))

    if not real_clusters:
        return text

    if progress_callback:
        progress_callback(1, 1, f"🔬 Znaleziono {len(real_clusters)} klastrów surowego języka. Trwa głębokie retłumaczenie...")

    results = {}
    lock = threading.Lock()
    
    def _translate_cluster(idx, chunk_text):
        prompt = f"""Przetłumacz CAŁY poniższy tekst.
Zachowaj formatowanie Markdown. NIE zostawiaj niczego po angielsku (wyjątek: tytuły książek w cudzysłowach, nazwy własne).
Oto tekst:

{chunk_text}"""
        
        for attempt in range(3):
            try:
                kwargs = {
                    "model": model_name,
                    "api_key": api_key,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                    "timeout": 120,
                }
                if api_base:
                    kwargs["api_base"] = api_base
                    
                response = litellm.completion(**kwargs)
                result = response.choices[0].message.content
                if result and len(result.strip()) > 20:
                    return result.strip()
            except Exception:
                time.sleep(4 * (attempt + 1))
        return chunk_text

    with ThreadPoolExecutor(max_workers=min(20, len(real_clusters))) as pool:
        futures = {pool.submit(_translate_cluster, i, c): (s, e) for i, (s, e, c) in enumerate(real_clusters)}
        for f in as_completed(futures):
            s, e = futures[f]
            results[(s, e)] = f.result()

    for (start, end), translated in sorted(results.items(), reverse=True):
        lines[start:end] = translated.split('\n')

    return '\n'.join(lines)


