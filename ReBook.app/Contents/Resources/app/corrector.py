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
    
    # Detect Gemma models — lower parallelism due to 15 RPM limit
    _model_name = (get_config().get("model_name", "") or "").lower()
    _llm_workers = 8 if "gemma" in _model_name else 30
    with ThreadPoolExecutor(max_workers=_llm_workers) as executor:
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
        _first_error = [None]
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
                if _first_error[0] is None:
                    _first_error[0] = str(e)
                    if progress_callback:
                        err_msg = str(e)[:150]
                        if any(k in err_msg.lower() for k in ("401", "403", "invalid", "api_key", "unauthorized")):
                            progress_callback(done_count, total, f"🔑 Błąd klucza API: {err_msg}")
                        else:
                            progress_callback(done_count, total, f"❌ Błąd API: {err_msg}")
                
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
_GEMINI_OCR_MODEL  = "gemini-3.1-flash-lite-preview"
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

_GEMINI_OCR_TRANSLATE_MODEL = "gemini-3.1-flash-lite-preview"


def _get_pdf_page_count(pdf_path: str) -> int:
    """Get total page count of a PDF using fitz or pypdf."""
    try:
        import fitz
        doc = fitz.open(pdf_path)
        count = len(doc)
        doc.close()
        return count
    except ImportError:
        pass
    try:
        from pypdf import PdfReader
        return len(PdfReader(pdf_path).pages)
    except ImportError:
        return 0  # unknown


def _split_pdf_pages(pdf_path: str, page_start: int, page_end: int) -> bytes:
    """Extract pages [page_start, page_end] (1-indexed, inclusive) from a PDF.
    Returns the extracted pages as PDF bytes."""
    import tempfile
    # Convert to 0-indexed
    p0 = page_start - 1
    p1 = page_end  # exclusive for range

    try:
        import fitz
        src = fitz.open(pdf_path)
        dst = fitz.open()  # new empty PDF
        dst.insert_pdf(src, from_page=p0, to_page=page_end - 1)  # inclusive
        pdf_bytes = dst.tobytes()
        dst.close()
        src.close()
        return pdf_bytes
    except ImportError:
        pass

    from pypdf import PdfReader, PdfWriter
    reader = PdfReader(pdf_path)
    writer = PdfWriter()
    for i in range(p0, min(p1, len(reader.pages))):
        writer.add_page(reader.pages[i])
    import io
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def get_pdf_page_count(pdf_path: str) -> int:
    """Public wrapper for GUI to show page count."""
    return _get_pdf_page_count(pdf_path)


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
        "auto": "Auto (najlepszy dostepny)",
    }
    return names.get(prov, prov)


def _mistral_ocr_single(key: str, model: str, pdf_bytes: bytes, timeout: int = 600) -> list:
    """Send a single PDF chunk to Mistral OCR. Returns list of page dicts."""
    import base64
    import urllib.request
    import urllib.error
    import json as _json

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

    retries = 3
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = _json.loads(resp.read())
            return result.get("pages", [])
        except urllib.error.HTTPError as e:
            err = e.read().decode(errors="replace")
            if attempt < retries - 1 and e.code in (429, 500, 503):
                time.sleep(10 * (attempt + 1))
                continue
            raise RuntimeError(f"Mistral OCR error {e.code}: {err[:300]}")
        except Exception as exc:
            if attempt < retries - 1:
                time.sleep(5)
                continue
            raise RuntimeError(f"Mistral OCR network error: {exc}")
    return []


def _mistral_ocr(
    pdf_path: str,
    config: dict = None,
    progress_callback: Optional[Callable[[str, int, str], None]] = None,
    page_start: int = 0,
    page_end: int = 0,
) -> str:
    """OCR via Mistral OCR API. Supports page ranges for large PDFs.
    
    Args:
        page_start: First page (1-indexed, 0 = from beginning)
        page_end: Last page (1-indexed, 0 = to end)
    """
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

    total_pages = _get_pdf_page_count(pdf_path)
    ps = max(page_start, 1) if page_start else 1
    pe = min(page_end, total_pages) if page_end else total_pages

    if ps > 1 or pe < total_pages:
        _report(5, f"Mistral OCR — strony {ps}–{pe} z {total_pages}...")
        pdf_bytes = _split_pdf_pages(pdf_path, ps, pe)
    else:
        pdf_bytes = Path(pdf_path).read_bytes()

    size_mb = len(pdf_bytes) / (1024 * 1024)
    page_count = pe - ps + 1
    _report(10, f"Mistral OCR — {page_count} stron, {size_mb:.1f} MB...")

    # For large PDFs (>100 pages), process in segments to avoid timeouts
    SEGMENT_SIZE = 100  # pages per API call
    if page_count > SEGMENT_SIZE:
        all_pages_md = []
        num_segments = (page_count + SEGMENT_SIZE - 1) // SEGMENT_SIZE
        for seg_idx in range(num_segments):
            seg_start = ps + seg_idx * SEGMENT_SIZE
            seg_end = min(ps + (seg_idx + 1) * SEGMENT_SIZE - 1, pe)
            seg_pct = int(10 + 80 * seg_idx / num_segments)
            _report(seg_pct, f"Mistral OCR — segment {seg_idx+1}/{num_segments} "
                             f"(strony {seg_start}–{seg_end})...")
            seg_bytes = _split_pdf_pages(pdf_path, seg_start, seg_end)
            pages = _mistral_ocr_single(key, model, seg_bytes)
            for p in pages:
                md = p.get("markdown", "")
                if md.strip():
                    all_pages_md.append(md)
            # Rate limit courtesy
            if seg_idx < num_segments - 1:
                time.sleep(2)
        text = "\n\n".join(all_pages_md).strip()
    else:
        _report(30, "Mistral OCR przetwarza dokument...")
        pages = _mistral_ocr_single(key, model, pdf_bytes)
        if not pages:
            raise RuntimeError("Mistral OCR: brak stron w odpowiedzi")
        text = "\n\n".join(p.get("markdown", "") for p in pages).strip()

    text = _strip_page_numbers(text)
    _report(100, f"Mistral OCR zakończone ({page_count} stron, {len(text):,} znaków)")
    return text


def _gemini_ocr(
    pdf_path: str,
    config: dict = None,
    progress_callback: Optional[Callable[[str, int, str], None]] = None,
    translate_lang: str = "",
    translate_from: str = "",
    page_start: int = 0,
    page_end: int = 0,
) -> str:
    """OCR via Gemini native PDF API. Optionally translates in the same request.
    Supports page ranges for large PDFs.
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

    # Extract page range if specified
    total_pages = _get_pdf_page_count(pdf_path)
    ps = max(page_start, 1) if page_start else 1
    pe = min(page_end, total_pages) if page_end else total_pages

    if ps > 1 or pe < total_pages:
        _report(5, f"Gemini {mode_label} — strony {ps}–{pe} z {total_pages}...")
        pdf_bytes = _split_pdf_pages(pdf_path, ps, pe)
    else:
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
                {"text": prompt},
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
    page_count = pe - ps + 1
    _report(100, f"Gemini {mode_label} zakończone ({page_count} stron, {len(text):,} znaków)")
    return text


# ─── langdetect-based local verification ──────────────────────────────────────

# Map of language names → ISO 639-1 codes for langdetect
_LANG_CODES = {
    "polski": "pl", "angielski": "en", "english": "en",
    "niemiecki": "de", "francuski": "fr", "hiszpański": "es",
    "włoski": "it", "portugalski": "pt", "rosyjski": "ru",
    "ukraiński": "uk", "czeski": "cs", "słowacki": "sk",
    "chiński": "zh-cn", "japoński": "ja", "koreański": "ko",
    "turecki": "tr", "arabski": "ar", "holenderski": "nl",
    "szwedzki": "sv", "norweski": "no", "duński": "da",
    "fiński": "fi", "węgierski": "hu", "rumuński": "ro",
}


def _verify_page_local(text: str, target_lang: str = "") -> bool:
    """Verify that text is in the expected language using langdetect.
    Returns True if verification passes.

    Smart handling:
    - Pages with < 100 chars: accept if non-empty (dedications, short pages)
    - Back-matter pages (bib, index, addresses): accept
    - Uses probability threshold instead of binary detection
    """
    stripped = text.strip()
    if not stripped:
        return False
    if len(stripped) < 100:
        return True  # Too short for reliable detection — accept if non-empty

    # Detect back-matter pages (bibliography, index, addresses, resources)
    # These legitimately contain foreign-language names, titles, URLs, addresses
    backmatter_indicators = [
        # Bibliography
        'ISBN', '(ed.)', '(eds.)', 'University Press', 'Vol.', 'pp.',
        'Journal of', 'New York:', 'London:', 'Cambridge:', '(red.)',
        'Press,', 'Books,', 'Publishing',
        # Addresses & contacts
        'PO Box', 'Tel:', 'Fax:', 'www.', 'http', '.org', '.com', '.edu',
        '@', 'Foundation', 'Association', 'Institute',
        # Index patterns
        '...', ', s.', 'zob.', 'por.',
    ]
    backmatter_count = sum(1 for ind in backmatter_indicators if ind in text)
    if backmatter_count >= 3:
        return True  # Back-matter page — foreign names and titles expected

    # Bibliography detection by year pattern: "1986." "1997." "2001." etc.
    import re
    year_refs = re.findall(r'(?:19|20)\d{2}\.', text)
    if len(year_refs) >= 3:
        return True  # Multiple publication years = bibliography page

    if not target_lang:
        return True  # No target = OCR-only, just check non-empty

    try:
        from langdetect import detect_langs
        target_code = _LANG_CODES.get(target_lang.strip().lower(), target_lang[:2].lower())
        langs = detect_langs(text)
        # Accept if target language is in top-2 detections with >15% probability
        for lang_prob in langs[:2]:
            if lang_prob.lang == target_code and lang_prob.prob > 0.15:
                return True
        return False
    except Exception:
        # langdetect not available or detection failed — pass through
        return True



# ─── Per-Page OCR Engine (v4.0) ───────────────────────────────────────────────

_DEFAULT_OCR_WORKERS = 50
_GEMMA_OCR_WORKERS = 10  # Gemma 4 has 15 RPM limit
_ESCALATION_MODEL = "gemini-3-flash-preview"
_PAGE_DPI = 200

def _is_gemma(model: str) -> bool:
    """Check if model is a Gemma model (has stricter rate limits)."""
    return "gemma" in model.lower()


def _build_glossary(
    pdf_path: str,
    api_key: str,
    lang_to: str,
    lang_from: str = "",
    sample_pages: list[int] = None,
) -> str:
    """Build a terminology glossary from sample pages of the PDF.
    Returns a formatted glossary string to include in prompts.
    """
    import base64
    import fitz
    import urllib.request
    import json as _json

    if not sample_pages:
        total = _get_pdf_page_count(pdf_path)
        # Sample 3 pages: near start, middle, late
        sample_pages = [min(5, total - 1), total // 2, min(total - 5, total - 1)]
        sample_pages = [max(0, p) for p in sample_pages]

    doc = fitz.open(pdf_path)
    images_b64 = []
    for p in sample_pages[:3]:
        if p < len(doc):
            mat = fitz.Matrix(_PAGE_DPI / 72, _PAGE_DPI / 72)
            pix = doc[p].get_pixmap(matrix=mat)
            images_b64.append(base64.standard_b64encode(pix.tobytes("png")).decode())
    doc.close()

    if not images_b64:
        return ""

    src = f" z {lang_from}" if lang_from else ""
    prompt = (
        f"Przeczytaj te strony książki. Wylistuj 20 kluczowych terminów specjalistycznych "
        f"i ich najlepsze tłumaczenie{src} na język {lang_to}.\n"
        f"Format: TERM_ORIGINAL → TERM_TRANSLATED\n"
        f"Jeśli termin nie wymaga tłumaczenia (nazwa własna), napisz: TERM → TERM\n"
        f"Odpowiedz TYLKO listą terminów, bez komentarzy."
    )

    parts = [{"text": prompt}]
    for img in images_b64:
        parts.append({"inline_data": {"mime_type": "image/png", "data": img}})

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{_GEMINI_OCR_MODEL}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2048},
    }
    try:
        req = urllib.request.Request(url, _json.dumps(payload).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            result = _json.loads(r.read())
        glossary_text = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        if glossary_text and len(glossary_text.strip()) > 20:
            return glossary_text.strip()
    except Exception:
        pass
    return ""


def _build_mega_prompt(
    translate_lang: str = "",
    translate_from: str = "",
    glossary: str = "",
) -> str:
    """Build the mega-prompt for per-page OCR (+optional translation + QC)."""
    if translate_lang:
        src = f" z języka {translate_from}" if translate_from else ""
        translate_section = (
            f"2. TŁUMACZENIE: Przetłumacz wyodrębniony tekst{src} na język {translate_lang}.\n"
            f"3. AUTOKOREKTA: Sprawdź porównując z obrazem czy:\n"
            f"   - Żadne zdanie nie zostało pominięte\n"
            f"   - Nie ma nieprzetłumaczonych fragmentów\n"
            f"   - Nie ma śmieci z OCR (losowe cyfry, symbole bez kontekstu)\n"
            f"   - Tekst jest płynny i naturalny po {translate_lang.lower()}\n"
        )
        rules = (
            f"- NIE zostawiaj niczego w języku oryginalnym (wyjątek: nazwy własne, tytuły książek)\n"
            f"- Zwróć WYŁĄCZNIE gotowy, przetłumaczony, zweryfikowany tekst w języku {translate_lang}"
        )
    else:
        translate_section = ""
        rules = "- Zwróć WYŁĄCZNIE wyodrębniony tekst ze skanu"

    glossary_section = ""
    if glossary:
        glossary_section = f"\nGLOSARIUSZ TERMINÓW (użyj tych tłumaczeń):\n{glossary}\n"

    return (
        f"Wykonaj następujące kroki na tym skanie strony książki:\n\n"
        f"1. EKSTRAKCJA (OCR): Wyodrębnij CAŁY tekst ze skanu strony.\n"
        f"{translate_section}"
        f"\nILUSTRACJA: Jeśli strona zawiera głównie ilustrację/rysunek/wykres:\n"
        f"- Bez tekstu do tłumaczenia: zwróć dokładnie: {{{{IMAGE:strona}}}}\n"
        f"- Z tekstem (podpisy, etykiety, tytuł): wyodrębnij tekst{',' + ' przetłumacz' if translate_lang else ''}"
        f" i zwróć jako: {{{{IMAGE_TEXT:strona}}}}\\n[tekst z ilustracji]\n"
        f"\nZASADY:\n"
        f"- Zachowaj formatowanie Markdown (# nagłówki, - listy, > cytaty)\n"
        f"- [nieczytelne] dla fragmentów niemożliwych do odczytania\n"
        f"- NIE dodawaj żadnych komentarzy — TYLKO tekst\n"
        f"{rules}"
        f"{glossary_section}"
    )


def _call_gemini_page(
    api_key: str,
    model: str,
    image_b64: str,
    prompt: str,
    timeout: int = 60,
) -> tuple[str, dict]:
    """Send a single page image to Gemini for OCR.
    Returns (text, usage_metadata).
    """
    import urllib.request
    import urllib.error
    import json as _json

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [
            {"text": prompt},
            {"inline_data": {"mime_type": "image/png", "data": image_b64}},
        ]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 8192},
    }
    data = _json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        result = _json.loads(resp.read().decode("utf-8"))

    usage = result.get("usageMetadata", {})
    text = ""
    if "candidates" in result:
        parts = result["candidates"][0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts)
    return text.strip(), usage


def _extract_pdf_page_image(pdf_path: str, page_num: int) -> bytes:
    """Extract the dominant image from a PDF page (for illustration pages).
    Returns image bytes (PNG) or empty bytes if no dominant image found.
    """
    import fitz

    doc = fitz.open(pdf_path)
    page = doc[page_num]
    images = page.get_images(full=True)

    if not images:
        doc.close()
        return b""

    # Find the largest image on the page
    page_area = page.rect.width * page.rect.height
    best_img = None
    best_size = 0

    for img_info in images:
        xref = img_info[0]
        try:
            pix = fitz.Pixmap(doc, xref)
            img_area = pix.width * pix.height
            if img_area > best_size:
                best_size = img_area
                # Convert to PNG bytes
                if pix.n > 4:  # CMYK → RGB
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                best_img = pix.tobytes("png")
            pix = None  # Free
        except Exception:
            continue

    doc.close()

    # Only return if the image covers >40% of the page
    if best_img and best_size > page_area * 0.10:
        return best_img
    return b""


def _postprocess_text(text: str) -> str:
    """Local postprocessing — zero cost, instant.
    Cleans up common OCR/AI artifacts.
    """
    import re

    # 1. Deduplicate consecutive identical paragraphs
    paragraphs = text.split('\n\n')
    deduped = []
    for p in paragraphs:
        if not deduped or p.strip() != deduped[-1].strip():
            deduped.append(p)
    text = '\n\n'.join(deduped)

    # 2. Strip orphaned page numbers (standalone numbers between blank lines)
    text = _strip_page_numbers(text)

    # 3. Normalize whitespace (max 2 consecutive newlines)
    text = re.sub(r'\n{3,}', '\n\n', text)

    # 4. Polish typography
    # „ " instead of " " for Polish
    text = re.sub(r'"([^"]+)"', r'„\1"', text)
    # — instead of -- for em-dash
    text = re.sub(r'(?<!\-)--(?!\-)', '—', text)

    # 5. Fix unclosed markdown emphasis (** without closing **)
    # Count ** occurrences — if odd, the last one is orphaned
    bold_count = text.count('**')
    if bold_count % 2 != 0:
        # Find last ** and remove it
        idx = text.rfind('**')
        if idx >= 0:
            text = text[:idx] + text[idx+2:]

    return text.strip()


def _gemini_ocr_pages(
    pdf_path: str,
    config: dict = None,
    progress_callback: Optional[Callable[[str, int, str], None]] = None,
    translate_lang: str = "",
    translate_from: str = "",
    page_start: int = 0,
    page_end: int = 0,
) -> tuple[str, dict[str, bytes]]:
    """Per-page OCR engine (v4.0).

    Renders each PDF page as image, sends mega-prompt in parallel.
    Verifies with langdetect, retries failures, extracts illustrations.

    Returns:
        (markdown_text, {image_filename: image_bytes})
    """
    import base64
    import fitz

    def _report(pct: int, msg: str):
        if progress_callback:
            progress_callback("ocr", pct, msg)

    c = get_ocr_config(config)
    key = c["llm_api_key"] or c["api_key"]
    # Per-page engine always uses Gemini — if the main provider isn't Gemini,
    # try GEMINI_API_KEY from environment or .env file
    if not key or (c.get("llm_provider") not in ("gemini", "google", "")):
        key = os.environ.get("GEMINI_API_KEY", "")
        if not key:
            # Try loading from .env file
            env_path = WORKSPACE_DIR / ".env"
            if not env_path.exists():
                env_path = Path(__file__).parent.parent.parent.parent / ".env"
            if env_path.exists():
                try:
                    for line in env_path.read_text().splitlines():
                        if line.startswith("GEMINI_API_KEY="):
                            key = line.split("=", 1)[1].strip()
                            break
                except Exception:
                    pass
    if not key:
        raise RuntimeError("Brak klucza Gemini API dla Cloud OCR.")

    model = _GEMINI_OCR_MODEL
    default_workers = _GEMMA_OCR_WORKERS if _is_gemma(model) else _DEFAULT_OCR_WORKERS
    workers = int((config or {}).get("ocr_workers", default_workers))
    if _is_gemma(model):
        workers = min(workers, _GEMMA_OCR_WORKERS)  # cap at 10 for Gemma
    workers = max(2, min(workers, 100))

    # Page range
    total_pages = _get_pdf_page_count(pdf_path)
    ps = max(page_start, 1) if page_start else 1
    pe = min(page_end, total_pages) if page_end else total_pages
    page_count = pe - ps + 1
    page_indices = list(range(ps - 1, pe))  # 0-indexed

    mode = f"OCR + tłumaczenie → {translate_lang}" if translate_lang else "OCR"
    model_label = "Gemma" if _is_gemma(model) else "Gemini"
    _report(2, f"{model_label} {mode} — {model}, {page_count} stron, {workers} workerów…")

    # ── Step 1: Build glossary (1 quick request) ─────────────────────────
    glossary = ""
    if translate_lang:
        _report(3, "📖 Budowanie glosariusza terminów…")
        try:
            glossary = _build_glossary(pdf_path, key, translate_lang, translate_from)
            if glossary:
                _report(5, f"📖 Glosariusz: {len(glossary.splitlines())} terminów")
        except Exception:
            _report(5, "⚠️ Glosariusz niedostępny — kontynuuję bez niego")

    # ── Step 2: Build prompt ─────────────────────────────────────────────
    prompt = _build_mega_prompt(translate_lang, translate_from, glossary)

    # ── Step 3: Render pages as images ───────────────────────────────────
    _report(6, f"📄 Renderowanie {page_count} stron…")
    doc = fitz.open(pdf_path)
    page_images = {}
    mat = fitz.Matrix(_PAGE_DPI / 72, _PAGE_DPI / 72)
    for i, page_idx in enumerate(page_indices):
        pix = doc[page_idx].get_pixmap(matrix=mat)
        page_images[page_idx] = base64.standard_b64encode(pix.tobytes("png")).decode()
        if i % 50 == 0:
            _report(6 + int(i / page_count * 4), f"📄 Renderowanie strony {i+1}/{page_count}…")
    doc.close()

    # ── Step 4: Send all pages in parallel ───────────────────────────────
    _report(10, f"🚀 Wysyłanie {page_count} stron ({workers} ∥)…")
    results = {}  # page_idx → text
    collected_images = {}  # filename → bytes
    failed = []
    failed_errors = {}  # page_idx → error message
    done_count = [0]
    _abort_flag = [False]  # early abort on auth errors
    _first_error_msg = [None]  # capture first error for UI

    import threading
    lock = threading.Lock()

    def _classify_error(e):
        """Classify error: 'auth', 'safety', 'rate', or 'other'."""
        msg = str(e).lower()
        if any(k in msg for k in ("401", "403", "invalid", "api_key", "unauthorized", "permission")):
            return "auth", f"🔑 Nieprawidłowy klucz API: {str(e)[:120]}"
        if any(k in msg for k in ("429", "rate", "quota", "resource_exhausted")):
            return "rate", f"⏱ Limit API wyczerpany: {str(e)[:120]}"
        if any(k in msg for k in ("safety", "prohibited", "blocked")):
            return "safety", f"🛡 Zablokowane przez filtr bezpieczeństwa"
        if any(k in msg for k in ("timeout", "timed out")):
            return "timeout", f"⏳ Timeout: {str(e)[:80]}"
        return "other", f"❌ Błąd: {str(e)[:120]}"

    def _process_page(page_idx):
        if _abort_flag[0]:
            return page_idx, "", Exception("aborted")
        try:
            text, usage = _call_gemini_page(key, model, page_images[page_idx], prompt)
            return page_idx, text, None
        except Exception as e:
            return page_idx, "", e

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_process_page, p): p for p in page_indices}
        for f in as_completed(futures):
            page_idx, text, err = f.result()

            if err:
                err_class, err_msg = _classify_error(err)
                failed.append(page_idx)
                failed_errors[page_idx] = err_msg

                with lock:
                    if _first_error_msg[0] is None:
                        _first_error_msg[0] = err_msg
                        _report(10, err_msg)
                    # Auth/key errors → abort all remaining pages
                    if err_class == "auth" and not _abort_flag[0]:
                        _abort_flag[0] = True
                        _report(10, "⛔ Przerwano — napraw klucz API w ustawieniach (⚙️)")

            elif not text or len(text.strip()) < 5:
                failed.append(page_idx)
                failed_errors[page_idx] = "📄 Pusta odpowiedź (< 5 znaków)"
            else:
                # Check for illustration markers
                stripped = text.strip()
                if stripped.startswith("{{IMAGE:"):
                    # Pure illustration — extract image from PDF
                    img_bytes = _extract_pdf_page_image(pdf_path, page_idx)
                    if img_bytes:
                        fname = f"page_{page_idx+1:04d}.png"
                        collected_images[fname] = img_bytes
                        results[page_idx] = f"\n![Ilustracja strona {page_idx+1}](images/{fname})\n"
                    else:
                        results[page_idx] = ""  # empty illustration page
                elif "{{IMAGE_TEXT:" in stripped:
                    # Illustration with text — extract image AND keep text
                    img_bytes = _extract_pdf_page_image(pdf_path, page_idx)
                    if img_bytes:
                        fname = f"page_{page_idx+1:04d}.png"
                        collected_images[fname] = img_bytes
                        # Remove the marker, keep the text
                        clean_text = stripped.replace("{{IMAGE_TEXT:strona}}", "").strip()
                        results[page_idx] = f"\n![Ilustracja strona {page_idx+1}](images/{fname})\n\n{clean_text}"
                    else:
                        results[page_idx] = stripped
                else:
                    # Verify translation with langdetect
                    if translate_lang and not _verify_page_local(text, translate_lang):
                        failed.append(page_idx)
                        failed_errors[page_idx] = "🌐 Weryfikacja języka nie przeszła"
                    else:
                        results[page_idx] = text

            with lock:
                done_count[0] += 1
                pct = 10 + int(done_count[0] / page_count * 70)
                if done_count[0] % 10 == 0 or done_count[0] == page_count:
                    _report(pct, f"🚀 {mode}: {done_count[0]}/{page_count} stron…")

    # ── Step 5: Retry failed pages (PARALLEL) ─────────────────────────────
    if failed and not _abort_flag[0]:
        # Show error summary before retrying
        error_types = {}
        for idx in failed:
            reason = failed_errors.get(idx, "nieznany")
            error_types[reason] = error_types.get(reason, 0) + 1
        for reason, count in error_types.items():
            _report(80, f"  {reason} ({count}x)")
        _report(80, f"🔄 Ponawiam {len(failed)} nieudanych stron (równolegle)…")
    elif failed and _abort_flag[0]:
        _report(80, f"⛔ Pominięto retry — {len(failed)}/{page_count} stron nie powiodło się z powodu błędu klucza API")
        _report(80, f"💡 Sprawdź klucz API w ustawieniach (⚙️) i spróbuj ponownie")
    if failed and not _abort_flag[0]:

        def _retry_page(page_idx):
            """Retry a single page up to 3 times, escalating model on last try."""
            for attempt in range(3):
                try:
                    retry_model = model if attempt < 2 else _ESCALATION_MODEL
                    text, _ = _call_gemini_page(key, retry_model, page_images[page_idx], prompt)
                    if text and len(text.strip()) > 5:
                        if translate_lang and not _verify_page_local(text, translate_lang):
                            if attempt == 2:
                                return page_idx, text, "escalated"
                            time.sleep(1)
                            continue
                        return page_idx, text, "recovered"
                except Exception:
                    time.sleep(2 * (attempt + 1))

            # ── Fallback: extract raw text from PDF via fitz (no API) ──
            # Handles PROHIBITED_CONTENT (safety filter) and persistent failures
            try:
                import fitz as _fitz
                _doc = _fitz.open(pdf_path)
                raw_text = _doc[page_idx].get_text().strip()
                _doc.close()
                if raw_text and len(raw_text) > 20:
                    if translate_lang:
                        # Strategy 1: Translate via litellm (user's configured provider)
                        try:
                            system = get_system_prompt(True, translate_lang, translate_from)
                            translated = process_mega_block(raw_text, system, retries=2)
                            if translated and len(translated.strip()) > 20:
                                return page_idx, translated, "fitz+translate"
                        except Exception:
                            pass

                        # Strategy 2: Direct Gemini text-only (minimal prompt, no image)
                        try:
                            import urllib.request
                            import json as _json
                            _url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
                            _prompt = f"Przetłumacz ten tekst na {translate_lang}. Zwróć TYLKO tłumaczenie:\n\n{raw_text}"
                            _payload = {
                                "contents": [{"parts": [{"text": _prompt}]}],
                                "generationConfig": {"temperature": 0.1, "maxOutputTokens": 8192},
                            }
                            _req = urllib.request.Request(_url, _json.dumps(_payload).encode(), {"Content-Type": "application/json"})
                            with urllib.request.urlopen(_req, timeout=30) as _r:
                                _result = _json.loads(_r.read())
                            _translated = _result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                            if _translated and len(_translated.strip()) > 20:
                                return page_idx, _translated.strip(), "fitz+gemini_text"
                        except Exception:
                            pass

                    # Last resort: return raw text (untranslated but present)
                    return page_idx, raw_text, "fitz_raw"
            except Exception:
                pass

            return page_idx, None, "failed"

        with ThreadPoolExecutor(max_workers=min(workers, len(failed))) as pool:
            retry_futures = {pool.submit(_retry_page, p): p for p in failed}
            for f in as_completed(retry_futures):
                page_idx, text, status = f.result()
                if text:
                    results[page_idx] = text
                    _report(85, f"{'✅' if status == 'recovered' else '⚠️'} Strona {page_idx+1}: {status}")
                else:
                    results[page_idx] = f"\n\n[NIEPRZETŁUMACZONE — strona {page_idx+1}]\n\n"
                    _report(85, f"❌ Strona {page_idx+1}: nie udało się")

    # ── Step 6: Assemble in order ────────────────────────────────────────
    _report(90, "📦 Składanie tekstu…")
    ordered_pages = sorted(results.keys())
    full_text = "\n\n".join(results[p] for p in ordered_pages)

    # ── Step 7: Postprocessing ───────────────────────────────────────────
    _report(95, "✨ Post-processing…")
    full_text = _postprocess_text(full_text)

    _report(100, f"✅ Gemini {mode} zakończone ({page_count} stron, {len(full_text):,} znaków)")
    return full_text, collected_images


def ocr_pdf(
    pdf_path: str,
    config: dict = None,
    progress_callback: Optional[Callable[[str, int, str], None]] = None,
    translate_lang: str = "",
    translate_from: str = "",
    page_start: int = 0,
    page_end: int = 0,
) -> Optional[str]:
    """Unified OCR dispatcher for all desktop platforms.

    Args:
        page_start: First page to OCR (1-indexed, 0 = from beginning)
        page_end: Last page to OCR (1-indexed, 0 = to end)

    Returns:
        str  — extracted markdown text (legacy mode)
        tuple(str, dict) — (text, collected_images) from per-page engine
        None — no cloud OCR available, caller should use local fitz extraction
    """
    if config is None:
        config = get_config()
    c = get_ocr_config(config)
    prov = c["provider"]

    def _report(pct, msg):
        if progress_callback:
            progress_callback("ocr", pct, msg)

    if prov == "mistral":
        return _mistral_ocr(pdf_path, config, progress_callback,
                            page_start=page_start, page_end=page_end)

    if prov == "gemini":
        return _gemini_ocr_pages(pdf_path, config, progress_callback,
                                translate_lang=translate_lang, translate_from=translate_from,
                                page_start=page_start, page_end=page_end)


    # "auto" — try best available, fall back silently
    # 1. Mistral OCR (if the user has a Mistral key — either as OCR key or main key)
    mistral_key = config.get("ocr_api_key", "").strip() or (
        c["llm_api_key"] if c["llm_provider"] == "mistral" else ""
    )
    if mistral_key:
        try:
            patched = dict(config)
            if not patched.get("ocr_api_key"):
                patched["ocr_api_key"] = mistral_key
            return _mistral_ocr(pdf_path, patched, progress_callback,
                                page_start=page_start, page_end=page_end)
        except Exception as e:
            _report(0, f"Mistral OCR niedostępny ({e}) — próbuję Gemini...")

    # 2. Gemini (if llm_provider is gemini) — use per-page engine
    if c["llm_provider"] == "gemini" and c["llm_api_key"]:
        try:
            return _gemini_ocr_pages(pdf_path, config, progress_callback,
                                    translate_lang=translate_lang, translate_from=translate_from,
                                    page_start=page_start, page_end=page_end)
        except Exception:
            _report(0, "Gemini OCR niedostępny — próbuję lokalna ekstrakcję…")

    return None  # no cloud OCR available — caller uses fitz extraction

