import json
import os
import sys
import time
from pathlib import Path
from typing import Callable, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# KRYTYCZNE: Wymuszenie dłuższego timeoutu HTTP dla biblioteki openai.
# GLM-5.1 (reasoning) potrzebuje 2+ minuty na blok 3000 znaków.
# Domyślny timeout openai to 120s, co powoduje ciche ReadTimeout + retry w nieskończoność.
os.environ['OPENAI_TIMEOUT'] = '600'

if sys.platform == "win32":
    WORKSPACE_DIR = Path.home() / ".rebook"
else:
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
        # Dynamic examples based on target language
        if to.lower().startswith("pol"):
            ex1 = '"Chapter 1—My Life" → "# Rozdział 1 — Moje życie"'
            ex2 = '"Introduction" → "# Wprowadzenie"'
            ex3 = '"Foreword" → "# Przedmowa"'
        elif to.lower().startswith("ang") or to.lower().startswith("eng"):
            ex1 = '"Rozdział 1 — Moje życie" → "# Chapter 1 — My Life"'
            ex2 = '"Wprowadzenie" → "# Introduction"'
            ex3 = '"Przedmowa" → "# Foreword"'
        elif to.lower().startswith("niem") or to.lower().startswith("deu") or to.lower().startswith("ger"):
            ex1 = '"Chapter 1—My Life" → "# Kapitel 1 — Mein Leben"'
            ex2 = '"Introduction" → "# Einleitung"'
            ex3 = '"Foreword" → "# Vorwort"'
        elif to.lower().startswith("fra") or to.lower().startswith("fran"):
            ex1 = '"Chapter 1—My Life" → "# Chapitre 1 — Ma vie"'
            ex2 = '"Introduction" → "# Introduction"'
            ex3 = '"Foreword" → "# Avant-propos"'
        elif to.lower().startswith("hisz") or to.lower().startswith("esp") or to.lower().startswith("spa"):
            ex1 = '"Chapter 1—My Life" → "# Capítulo 1 — Mi vida"'
            ex2 = '"Introduction" → "# Introducción"'
            ex3 = '"Foreword" → "# Prólogo"'
        else:
            ex1 = f'"Chapter 1—My Life" → "# [Chapter 1 — My Life in {to}]"'
            ex2 = f'"Introduction" → "# [Introduction in {to}]"'
            ex3 = f'"Foreword" → "# [Foreword in {to}]"'
        return f"""Jesteś profesjonalnym tłumaczem książek. Twoim zadaniem jest przetłumaczenie poniższego tekstu {frm} na język {to}.

Zasady:
1. Tekst ma być przetłumaczony w sposób naturalny dla czytelnika z zachowaniem najwyższej poprawności oraz oryginalnego kontekstu wyjściowego autora.
2. Przetłumacz ABSOLUTNIE WSZYSTKO na język {to} — w tym nagłówki, cytaty, podpisy, dialogi i wszelkie fragmenty w języku obcym. NIE zostawiaj niczego w oryginalnym języku. Jedyny wyjątek: tytuły książek w cudzysłowach i nazwy własne organizacji.
3. ZACHOWAJ FORMATOWANIE Markdown (nagłówki #, pogrubienia **, listy -, cytaty >). Nie zmieniaj ich składni.
4. NAGŁÓWKI ROZDZIAŁÓW: Jeśli tekst zawiera nagłówki typu "Chapter X — Title", "Introduction", "Foreword", "Preface", "Appendix" — przetłumacz je na język {to} i oznacz jako nagłówki Markdown. Przykłady:
   - {ex1}
   - {ex2}
   - {ex3}
5. NIE ŁĄCZ i NIE POMIJAJ akapitów. Każdy akapit z oryginału MUSI pojawić się w tłumaczeniu. Nie skracaj tekstu.
6. NAGŁÓWKI (linie zaczynające się od #): Nagłówek to TYLKO krótki tytuł rozdziału lub sekcji (max 1-2 zdania). Jeśli widzisz że po znaku # znajduje się długi akapit (ponad 2 zdania), zamień go na zwykły tekst pogrubiony (**tekst**) — to ewidentny błąd formatowania z OCR.
7. WYCZYŚĆ ARTEFAKTY: Jeśli w tekście występują śmieci techniczne takie jak: deklaracje XML (<?xml ...?>), znaczniki HTML (<div>, <span>, itp.), kody DOCTYPE, encje HTML (&amp; &nbsp;) — USUŃ JE i zostaw tylko czysty tekst.
8. NIE NUMERUJ akapitów — nie dodawaj cyfr (1., 2., 3.) ani liczb przed fragmentami tekstu jeśli ich nie było w oryginale.
9. Zwróć TYLKO wynik tłumaczenia. Nie dodawaj notatek ani komentarzy.
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
7. NIE NUMERUJ akapitów — nie dodawaj cyfr (1., 2., 3.) przed linią jeśli jej nie było w oryginale.
8. Zwróć TYLKO poprawiony tekst, bez komentarzy ani przemyśleń"""


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
    # SKIP this gate when translating TO English — the detector is English-hardcoded
    # and would flag correct English output as "untranslated source"
    _target_is_english = lang_to.lower().strip() in (
        "angielski", "english", "eng", "anglais", "englisch", "inglés",
        "inglese", "английский", "англійська", "英语", "英語",
    )
    if use_translate and not _target_is_english:
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

        MAX_VERIFY_RETRIES = 3
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
                    "timeout": 120,
                }
                if api_base:
                    kwargs["api_base"] = api_base

                response = litellm.completion(**kwargs)
                result = response.choices[0].message.content
                if result and result.strip():
                    # If AI returned substantial text → use as verified version
                    # If AI returned short response (e.g. 'translation is correct')
                    # → original translation was fine, keep it
                    verified = result.strip()
                    if len(verified) < len(trans_chunk) * 0.3:
                        # Response too short vs input = AI said "it's fine", keep original
                        verified = trans_chunk
                    with lock:
                        done_count[0] += 1
                        if progress_callback:
                            progress_callback(done_count[0], total_chunks,
                                f"✅ Segment {idx+1}/{total_chunks} zweryfikowany "
                                f"({done_count[0]}/{total_chunks})")
                    return verified
                else:
                    time.sleep(2)
            except Exception as e:
                if progress_callback:
                    with lock:
                        progress_callback(done_count[0], total_chunks,
                            f"⚠️ Segment {idx+1} próba {attempt+1}/{MAX_VERIFY_RETRIES}: {e}")
                time.sleep(3)

        # Exhausted retries — use original translation instead of crashing
        with lock:
            done_count[0] += 1
            if progress_callback:
                progress_callback(done_count[0], total_chunks,
                    f"⚠️ Segment {idx+1}: weryfikacja nie powiodła się, zachowano oryginalne tłumaczenie")
        return trans_chunk

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

    # Use a proper translation prompt (NOT the verify_prompt) for retranslation
    retranslate_prompt = f"""Jesteś profesjonalnym tłumaczem. Przetłumacz poniższy tekst na język {lang_to}.
Zachowaj formatowanie Markdown. NIE zostawiaj niczego w języku {lang_from or 'źródłowym'}.
Zwróć TYLKO przetłumaczony tekst."""

    final_text = _deep_translate_clusters(final_text, retranslate_prompt, model_name, api_key, api_base, progress_callback)

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
    done_clusters = [0]
    total_clusters = len(real_clusters)
    
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
            with lock:
                done_clusters[0] += 1
                if progress_callback:
                    progress_callback(done_clusters[0], total_clusters,
                        f"🔬 Retłumaczenie klastra {done_clusters[0]}/{total_clusters}...")

    for (start, end), translated in sorted(results.items(), reverse=True):
        lines[start:end] = translated.split('\n')

    return '\n'.join(lines)


# ─── Dual-Provider OCR Layer ──────────────────────────────────────────────────

_MISTRAL_OCR_MODEL = "mistral-ocr-latest"
_GEMINI_OCR_MODEL  = "gemini-2.5-flash-lite"
_GEMINI_OCR_SIZE_MB = 50

_OCR_PROMPT = (
    "Wyciagnij caly tekst z tego dokumentu PDF jako czysty Markdown.\n\n"
    "Zasady:\n"
    "1. Uzywaj # dla tytulów rozdzialów i ## dla podrozdzialów.\n"
    "2. Kazdy akapit oddziel pusta linia.\n"
    "3. Zachowaj listy punktowane jako - item.\n"
    "4. Zachowaj listy numerowane jako 1. item.\n"
    "5. NIE dodawaj wlasnych komentarzy, podsumowań ani wstepow.\n"
    "6. Zwroc TYLKO tekst dokumentu w formacie Markdown."
)

_GEMINI_OCR_TRANSLATE_MODEL = "gemini-3.0-flash"

def _ocr_translate_prompt(lang_to: str, lang_from: str = "") -> str:
    """Prompt for combined OCR + translation in a single Gemini request."""
    src = f" z języka {lang_from}" if lang_from else ""
    return (
        f"Wyciągnij cały tekst z tego dokumentu PDF i PRZETŁUMACZ go{src} "
        f"na język {lang_to}. Zwróć wynik jako czysty Markdown.\n\n"
        "Zasady:\n"
        "1. Używaj # dla tytułów rozdziałów i ## dla podrozdziałów.\n"
        "2. Każdy akapit oddziel pustą linią.\n"
        "3. Zachowaj listy punktowane jako - item.\n"
        "4. Zachowaj listy numerowane jako 1. item.\n"
        "5. Przetłumacz ABSOLUTNIE WSZYSTKO — nagłówki, cytaty, podpisy, dialogi.\n"
        "6. NIE zostawiaj niczego w oryginalnym języku (wyjątek: nazwy własne).\n"
        "7. NIE dodawaj własnych komentarzy, podsumowań ani wstępów.\n"
        "8. Zwróć TYLKO przetłumaczony tekst dokumentu w formacie Markdown."
    )




def _strip_page_numbers(text: str) -> str:
    """Remove lone page numbers that OCR transcribes from headers/footers.

    Scanned books have page numbers printed at top/bottom of each page.
    OCR copies them as isolated lines like: 123, — 45 —, - 6 -, [7], (8)
    These appear as stray numbers between paragraphs in the assembled text.
    """
    import re
    lines = text.split('\n')
    cleaned = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Lone number: digits optionally wrapped in dash/bracket/paren
        is_lone_number = bool(re.fullmatch(
            r'[\-\—\–\·\[\(]?\s*\d{1,4}\s*[\-\—\–\·\]\)]?',
            stripped
        ))
        if is_lone_number and stripped:
            prev_blank = (i == 0) or (lines[i - 1].strip() == '')
            next_blank = (i == len(lines) - 1) or (lines[i + 1].strip() == '')
            if prev_blank and next_blank:
                cleaned.append('')
                continue
        cleaned.append(line)
    result = re.sub(r'\n{3,}', '\n\n', '\n'.join(cleaned))
    return result

def get_ocr_config(config: dict = None) -> dict:
    """Return effective OCR config (merging main config defaults)."""
    if config is None:
        config = get_config()
    ocr_key = config.get("ocr_api_key", "").strip() or config.get("api_key", "").strip()
    ocr_model = config.get("ocr_model", "").strip()
    ocr_provider = config.get("ocr_provider", "auto").strip().lower()
    return {
        "provider": ocr_provider,
        "api_key": ocr_key,
        "model": ocr_model,
        "llm_provider": config.get("llm_provider", "").strip().lower(),
        "llm_api_key": config.get("api_key", "").strip(),
    }


def is_cloud_ocr_available(config: dict = None) -> bool:
    """True when a cloud OCR provider is configured with a valid key."""
    c = get_ocr_config(config)
    prov = c["provider"]
    if prov == "marker":
        return False
    if prov in ("mistral", "gemini"):
        return bool(c["api_key"])
    # auto: available if any cloud key exists
    if c["api_key"] and c["llm_provider"] in ("gemini", "mistral"):
        return True
    return bool(c.get("api_key") and config and config.get("ocr_api_key"))


def get_ocr_provider_display(config: dict = None) -> str:
    """Human-readable name of the active OCR provider."""
    c = get_ocr_config(config)
    prov = c["provider"]
    names = {
        "mistral": "Mistral OCR",
        "gemini": "Gemini Cloud OCR",
        "marker": "Marker OCR (lokalny)",
        "auto": "Auto (najlepszy dostepny)",
    }
    return names.get(prov, prov)


def _mistral_ocr(
    pdf_path: str,
    config: dict = None,
    progress_callback: Optional[Callable[[str, int, str], None]] = None,
) -> str:
    """OCR via Mistral OCR API. Returns markdown text."""
    import base64
    import urllib.request
    import urllib.error
    import json as _json

    def _report(pct: int, msg: str):
        if progress_callback:
            progress_callback("ocr", pct, msg)

    c = get_ocr_config(config)
    key = c["api_key"]
    if not key:
        raise RuntimeError(
            "Brak klucza Mistral OCR!\n"
            "Wejdz w Ustawienia (OCR) i wklej klucz Mistral API."
        )
    model = c["model"] or _MISTRAL_OCR_MODEL

    pdf_bytes = Path(pdf_path).read_bytes()
    size_mb = len(pdf_bytes) / (1024 * 1024)
    _report(10, f"Mistral OCR — {size_mb:.1f} MB...")

    b64 = base64.b64encode(pdf_bytes).decode("ascii")
    payload = {
        "model": model,
        "document": {
            "type": "document_url",
            "document_url": f"data:application/pdf;base64,{b64}",
        },
        "include_image_base64": False,
    }

    req = urllib.request.Request(
        "https://api.mistral.ai/v1/ocr",
        _json.dumps(payload).encode("utf-8"),
        {"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )

    _report(30, "Mistral OCR przetwarza dokument...")
    retries = 3
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                result = _json.loads(resp.read())
            break
        except urllib.error.HTTPError as e:
            err = e.read().decode(errors="replace")
            if attempt < retries - 1 and e.code in (429, 500, 503):
                time.sleep(10 * (attempt + 1))
                _report(30, f"Ponawiam ({attempt+2}/{retries})...")
                continue
            raise RuntimeError(f"Mistral OCR error {e.code}: {err[:300]}")
        except Exception as exc:
            if attempt < retries - 1:
                time.sleep(5)
                continue
            raise RuntimeError(f"Mistral OCR network error: {exc}")

    pages = result.get("pages", [])
    if not pages:
        raise RuntimeError("Mistral OCR: brak stron w odpowiedzi")

    text = "\n\n".join(p.get("markdown", "") for p in pages).strip()
    text = _strip_page_numbers(text)
    _report(100, f"Mistral OCR zakonczone ({len(pages)} stron, {len(text):,} znakow)")
    return text


def _gemini_ocr(
    pdf_path: str,
    config: dict = None,
    progress_callback: Optional[Callable[[str, int, str], None]] = None,
    translate_lang: str = "",
    translate_from: str = "",
) -> str:
    """OCR via Gemini native PDF API. Optionally translates in the same request.
    
    If translate_lang is set, uses gemini-3.0-flash with combined OCR+translate prompt.
    Otherwise uses configured model (default: gemini-2.5-flash-lite) for OCR only.
    Returns markdown text (translated if translate_lang was set).
    """
    import base64
    import urllib.request
    import urllib.error
    import json as _json

    def _report(pct: int, msg: str):
        if progress_callback:
            progress_callback("ocr", pct, msg)

    c = get_ocr_config(config)
    key = c["llm_api_key"] or c["api_key"]
    if not key:
        raise RuntimeError("Brak klucza Gemini API dla Cloud OCR.")

    # Choose model + prompt based on whether we're also translating
    if translate_lang:
        model = _GEMINI_OCR_TRANSLATE_MODEL
        prompt = _ocr_translate_prompt(translate_lang, translate_from)
        mode_label = f"OCR + tłumaczenie → {translate_lang}"
    else:
        configured_model = c["model"]
        model = (configured_model if configured_model.startswith("gemini")
                 else _GEMINI_OCR_MODEL)
        prompt = _OCR_PROMPT
        mode_label = "OCR"

    pdf_bytes = Path(pdf_path).read_bytes()
    size_mb = len(pdf_bytes) / (1024 * 1024)
    base_url = "https://generativelanguage.googleapis.com/v1beta"

    _report(10, f"Gemini {mode_label} — {size_mb:.1f} MB...")

    if size_mb <= _GEMINI_OCR_SIZE_MB:
        b64 = base64.b64encode(pdf_bytes).decode("ascii")
        payload = {
            "contents": [{"parts": [
                {"inline_data": {"mime_type": "application/pdf", "data": b64}},
                {"text": prompt},
            ]}],
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 65536},
        }
    else:
        # Files API for large PDFs
        _report(15, f"Duzy plik — Files API upload ({size_mb:.0f} MB)...")
        num_bytes = len(pdf_bytes)
        init_url = f"{base_url}/files?key={key}"
        init_headers = {
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(num_bytes),
            "X-Goog-Upload-Header-Content-Type": "application/pdf",
            "Content-Type": "application/json",
        }
        init_body = _json.dumps({"file": {"display_name": Path(pdf_path).name}}).encode()
        req0 = urllib.request.Request(init_url, data=init_body, headers=init_headers, method="POST")
        with urllib.request.urlopen(req0, timeout=60) as r:
            upload_url = r.headers.get("X-Goog-Upload-URL")
        if not upload_url:
            raise RuntimeError("Gemini Files API: brak upload URL")
        _report(25, "Wgrywanie PDF do Gemini Files API...")
        ureq = urllib.request.Request(upload_url, data=pdf_bytes, headers={
            "Content-Length": str(num_bytes),
            "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize",
        }, method="PUT")
        with urllib.request.urlopen(ureq, timeout=600) as r:
            finfo = _json.loads(r.read())
        file_uri = finfo.get("file", {}).get("uri") or finfo.get("uri")
        if not file_uri:
            raise RuntimeError("Gemini Files API: brak URI po uploadzie")
        payload = {
            "contents": [{"parts": [
                {"file_data": {"mime_type": "application/pdf", "file_uri": file_uri}},
                {"text": _OCR_PROMPT},
            ]}],
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 65536},
        }

    gen_url = f"{base_url}/models/{model}:generateContent?key={key}"
    req = urllib.request.Request(
        gen_url, _json.dumps(payload).encode(),
        {"Content-Type": "application/json"}, method="POST"
    )

    _report(50, f"Gemini {mode_label}...")
    retries = 3
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                result = _json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            err = e.read().decode(errors="replace")
            if attempt < retries - 1 and e.code in (429, 500, 503):
                time.sleep(10 * (attempt + 1))
                _report(50, f"Ponawiam ({attempt + 2}/{retries})...")
                continue
            raise RuntimeError(f"Gemini OCR error {e.code}: {err[:300]}")
        except Exception as exc:
            if attempt < retries - 1:
                time.sleep(5)
                continue
            raise RuntimeError(f"Gemini OCR network error: {exc}")

    parts = result.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    text = "\n".join(p.get("text", "") for p in parts if "text" in p).strip()
    if not text:
        raise RuntimeError("Gemini OCR: pusta odpowiedz modelu")
    text = _strip_page_numbers(text)
    _report(100, f"Gemini {mode_label} zakończone ({len(text):,} znakow)")
    return text


def ocr_pdf(
    pdf_path: str,
    config: dict = None,
    progress_callback: Optional[Callable[[str, int, str], None]] = None,
    translate_lang: str = "",
    translate_from: str = "",
) -> Optional[str]:
    """Unified OCR dispatcher for all desktop platforms.

    Returns:
        str  — extracted markdown text (cloud OCR succeeded)
        None — caller should fall back to local Marker OCR
    """
    if config is None:
        config = get_config()
    c = get_ocr_config(config)
    prov = c["provider"]

    def _report(pct, msg):
        if progress_callback:
            progress_callback("ocr", pct, msg)

    if prov == "mistral":
        return _mistral_ocr(pdf_path, config, progress_callback)

    if prov == "gemini":
        return _gemini_ocr(pdf_path, config, progress_callback,
                           translate_lang=translate_lang, translate_from=translate_from)

    if prov == "marker":
        return None  # explicit local mode

    # "auto" — try best available, fall back silently
    # 1. Mistral OCR (if the user has a Mistral key — either as OCR key or main key)
    mistral_key = config.get("ocr_api_key", "").strip() or (
        c["llm_api_key"] if c["llm_provider"] == "mistral" else ""
    )
    if mistral_key:
        try:
            # Temporarily set ocr key for _mistral_ocr
            patched = dict(config)
            if not patched.get("ocr_api_key"):
                patched["ocr_api_key"] = mistral_key
            return _mistral_ocr(pdf_path, patched, progress_callback)
        except Exception as e:
            _report(0, f"Mistral OCR niedostępny ({e}) — próbuję Gemini...")

    # 2. Gemini (if llm_provider is gemini)
    if c["llm_provider"] == "gemini" and c["llm_api_key"]:
        try:
            return _gemini_ocr(pdf_path, config, progress_callback,
                               translate_lang=translate_lang, translate_from=translate_from)
        except Exception:
            _report(0, "Gemini OCR niedostępny — używam Marker...")

    return None  # fall back to Marker

