#!/usr/bin/env python3
"""
NVIDIA API Test — deepseek-ai/deepseek-v3.2
via openai client, thinking=False
"""

import time
import concurrent.futures
from datetime import datetime
from openai import OpenAI

API_KEY = "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"
MODEL = "deepseek-ai/deepseek-v3.2"

def make_client():
    return OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=API_KEY,
    )

TRANSLATION_TESTS = [
    ("simple",       "Dzień dobry! Jak się masz?"),
    ("technical",    "Konwersja pliku PDF do formatu EPUB wymaga precyzyjnego zachowania układu strony."),
    ("literary",     "Stary człowiek siedział przy oknie i patrzył na deszcz spływający po szybie. Myślał o minionych latach, które ulotniły się jak dym."),
    ("complex_book", "Rozdział trzeci. Ewolucja sztucznej inteligencji w ostatniej dekadzie przyniosła rewolucyjne zmiany w sposobie przetwarzania języka naturalnego. Modele językowe osiągnęły poziom rozumienia tekstu, który jeszcze dekadę temu wydawał się niemożliwy."),
]


def call_stream(prompt: str, thinking: bool = False) -> dict:
    client = make_client()
    start = time.time()
    content_parts = []
    think_chars = 0
    first_token_time = None
    try:
        completion = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=1,
            top_p=0.95,
            max_tokens=4096,
            extra_body={"chat_template_kwargs": {"thinking": thinking}},
            stream=True,
        )
        for chunk in completion:
            if not getattr(chunk, "choices", None):
                continue
            delta = chunk.choices[0].delta
            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning:
                think_chars += len(reasoning)
            piece = delta.content
            if piece:
                if first_token_time is None:
                    first_token_time = time.time() - start
                content_parts.append(piece)

        elapsed = time.time() - start
        return {
            "ok": True, "status": 200,
            "content": "".join(content_parts).strip(),
            "thinking_chars": think_chars,
            "elapsed": elapsed,
            "ttft": first_token_time,
        }
    except Exception as e:
        return {"ok": False, "status": -1, "error": str(e),
                "content": "", "thinking_chars": 0, "elapsed": time.time() - start}


def call_non_stream(prompt: str, thinking: bool = False) -> dict:
    client = make_client()
    start = time.time()
    try:
        completion = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=1,
            top_p=0.95,
            max_tokens=512,
            extra_body={"chat_template_kwargs": {"thinking": thinking}},
            stream=False,
        )
        elapsed = time.time() - start
        content = (completion.choices[0].message.content or "").strip()
        return {"ok": True, "status": 200, "content": content, "elapsed": elapsed}
    except Exception as e:
        # extract HTTP status if available
        err = str(e)
        status = -1
        if "429" in err:
            status = 429
        elif "503" in err or "502" in err:
            status = 503
        return {"ok": False, "status": status, "error": err[:200],
                "content": "", "elapsed": time.time() - start}


# ============================================================
# TEST 1: Podstawowa łączność
# ============================================================
def test_basic():
    print("\n" + "="*60)
    print("TEST 1: Podstawowa łączność")
    print("="*60)
    r = call_stream("Say hello in one sentence.", thinking=False)
    if r["ok"]:
        print(f"  ✅ {r['elapsed']:.2f}s | TTFT: {r['ttft']:.2f}s | think: {r['thinking_chars']}c")
        print(f"  → {r['content'][:200]}")
    else:
        print(f"  ❌ {r['status']}: {r.get('error','')[:120]}")
    return r["ok"]


# ============================================================
# TEST 2: Jakość tłumaczenia (streaming, thinking=False)
# ============================================================
def test_translation():
    print("\n" + "="*60)
    print("TEST 2: Jakość tłumaczenia (PL → EN, thinking=False)")
    print("="*60)
    for name, text in TRANSLATION_TESTS:
        prompt = f"Translate the following Polish text to English. Output ONLY the translation.\n\nPolish:\n{text}"
        print(f"\n  [{name}] {text[:60]}...")
        r = call_stream(prompt, thinking=False)
        if r["ok"]:
            print(f"  ✅ {r['elapsed']:.2f}s | TTFT: {r.get('ttft',0):.2f}s | think: {r['thinking_chars']}c")
            print(f"     → {r['content'][:160]}")
        else:
            print(f"  ❌ {r['status']}: {r.get('error','')[:100]}")


# ============================================================
# TEST 3: Halucynacje / śmieci
# ============================================================
def test_garbage():
    print("\n" + "="*60)
    print("TEST 3: Halucynacje / śmieci (thinking=False)")
    print("="*60)
    tests = [
        ("math",           "What is 17 * 23? Reply with only the number.",              "391"),
        ("capital",        "What is the capital of France? Reply with only the city.",   "Paris"),
        ("empty_translate","Translate this Polish text to English:\n\n(empty)",          None),
    ]
    for name, prompt, expected in tests:
        r = call_stream(prompt, thinking=False)
        if r["ok"]:
            content = r["content"].strip()
            if expected:
                ok = expected.lower() in content.lower()
                icon = "✅" if ok else "⚠️ "
                print(f"  {icon} [{name}] expected='{expected}' got='{content[:80]}'  [{r['elapsed']:.1f}s]")
            else:
                icon = "⚠️  VERBOSE" if len(content) > 200 else "✅"
                print(f"  {icon} [{name}] empty input → '{content[:100]}'  [{r['elapsed']:.1f}s]")
        else:
            print(f"  ❌ [{name}] {r['status']}: {r.get('error','')[:80]}")


# ============================================================
# TEST 4: Współbieżność — thinking=False, push do 32
# ============================================================
def test_concurrency():
    print("\n" + "="*60)
    print("TEST 4: Współbieżność — thinking=False, push do 32")
    print("="*60)
    prompt = "Translate to English: Gdzie jest najbliższa stacja metra?"

    def worker(n):
        r = call_non_stream(prompt, thinking=False)
        return {"n": n, "ok": r["ok"], "status": r["status"],
                "elapsed": r["elapsed"], "error": r.get("error", "")}

    levels = [1, 4, 8, 12, 16, 20, 24, 32]
    for level in levels:
        print(f"\n  → {level} równoległych requestów...")
        start_all = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=level) as ex:
            futures = [ex.submit(worker, i) for i in range(level)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        wall = time.time() - start_all

        ok_n   = sum(1 for r in results if r["ok"])
        fail_n = level - ok_n
        statuses = sorted(r["status"] for r in results)
        avg_lat  = sum(r["elapsed"] for r in results) / len(results)
        errors   = list(set(r["error"] for r in results if not r["ok"]))
        n429     = statuses.count(429)

        icon = "✅" if fail_n == 0 else f"⚠️  ({n429}× 429)"
        print(f"    {icon}  OK: {ok_n}/{level} | ❌ Fail: {fail_n}")
        print(f"    Statuses: {statuses}")
        print(f"    Avg lat: {avg_lat:.2f}s | Wall: {wall:.2f}s | Throughput: {ok_n/wall:.1f} req/s")
        if errors:
            print(f"    Errors: {errors[:1]}")

        if fail_n > level * 0.25:
            print(f"    ⛔ >25% błędów. Zatrzymuję.")
            break
        time.sleep(2)


# ============================================================
# PORÓWNANIE REFERNCYJNE
# ============================================================
def print_reference():
    print("\n" + "="*60)
    print("MODELE REFERENCYJNE (z poprzednich testów)")
    print("="*60)
    print("  Mistral-Small 4 (119B) | lat ~1s  | concur ≤12  | no think")
    print("  Qwen3.5-122B think=OFF | lat ~0.9s| concur ≤7   | no think")
    print("  Qwen3.5-122B think=ON  | lat ~5s  | concur ≤16  | think")
    print("  DeepSeek-V3.2          | ???      | ???         | ← TEN TEST")


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    print(f"\n🚀 DeepSeek-V3.2 Test Suite via OpenAI Client")
    print(f"   Model: {MODEL}")
    print(f"   Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print_reference()

    ok = test_basic()
    if not ok:
        print("\n❌ Brak łączności. Przerywam.")
        exit(1)

    test_translation()
    test_garbage()
    test_concurrency()

    print("\n\n✅ Wszystkie testy zakończone.")
