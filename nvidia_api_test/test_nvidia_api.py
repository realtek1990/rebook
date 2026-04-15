#!/usr/bin/env python3
"""
NVIDIA API Test Suite
Tests: concurrency limits, translation quality, garbage output detection
"""

import requests
import json
import time
import threading
import concurrent.futures
from datetime import datetime

INVOKE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
API_KEY = "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"
MODEL = "mistralai/mistral-small-4-119b-2603"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json"
}

# --- Test texts for translation (PL -> EN) ---
TRANSLATION_TESTS = [
    {
        "id": "simple",
        "text": "Dzień dobry! Jak się masz?",
        "expected_en": "Good morning! How are you?"
    },
    {
        "id": "technical",
        "text": "Konwersja pliku PDF do formatu EPUB wymaga precyzyjnego zachowania układu strony.",
        "expected_en": "Converting a PDF file to EPUB format requires precise preservation of the page layout."
    },
    {
        "id": "literary",
        "text": "Stary człowiek siedział przy oknie i patrzył na deszcz spływający po szybie. Myślał o minionych latach, które ulotniły się jak dym.",
        "expected_en": "An old man sat by the window and watched the rain running down the glass. He thought about the years gone by, which had vanished like smoke."
    },
    {
        "id": "complex_book",
        "text": "Rozdział trzeci. Ewolucja sztucznej inteligencji w ostatniej dekadzie przyniosła rewolucyjne zmiany w sposobie przetwarzania języka naturalnego. Modele językowe osiągnęły poziom rozumienia tekstu, który jeszcze dekadę temu wydawał się niemożliwy.",
        "expected_en": "Chapter three. The evolution of artificial intelligence in the last decade has brought revolutionary changes in natural language processing. Language models have reached a level of text understanding that seemed impossible just a decade ago."
    },
]

def call_api_non_stream(prompt: str, temperature: float = 0.10) -> dict:
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 4096,
        "temperature": temperature,
        "top_p": 1.00,
        "stream": False
    }
    start = time.time()
    try:
        response = requests.post(INVOKE_URL, headers=HEADERS, json=payload, timeout=60)
        elapsed = time.time() - start
        if response.status_code == 200:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return {"ok": True, "content": content, "elapsed": elapsed, "status": 200}
        else:
            return {"ok": False, "content": "", "elapsed": elapsed, "status": response.status_code, "error": response.text[:300]}
    except Exception as e:
        elapsed = time.time() - start
        return {"ok": False, "content": "", "elapsed": elapsed, "status": -1, "error": str(e)}


# ============================================================
# TEST 1: Basic connectivity & model response
# ============================================================
def test_basic():
    print("\n" + "="*60)
    print("TEST 1: Basic connectivity")
    print("="*60)
    result = call_api_non_stream("Say hello in one sentence.")
    if result["ok"]:
        print(f"  ✅ OK [{result['elapsed']:.2f}s]")
        print(f"  Response: {result['content'][:200]}")
    else:
        print(f"  ❌ FAILED: HTTP {result['status']}")
        print(f"  Error: {result.get('error','')}")
    return result["ok"]


# ============================================================
# TEST 2: Translation quality
# ============================================================
def test_translation_quality():
    print("\n" + "="*60)
    print("TEST 2: Translation quality (PL -> EN)")
    print("="*60)
    results = []
    for test in TRANSLATION_TESTS:
        prompt = (
            f"Translate the following Polish text to English. "
            f"Output ONLY the English translation, nothing else.\n\n"
            f"Polish text:\n{test['text']}"
        )
        print(f"\n  [{test['id']}] Input: {test['text'][:60]}...")
        result = call_api_non_stream(prompt)
        if result["ok"]:
            content = result["content"].strip()
            print(f"  ✅ [{result['elapsed']:.2f}s] Output: {content[:120]}")
            results.append({"id": test["id"], "ok": True, "output": content, "elapsed": result["elapsed"]})
        else:
            print(f"  ❌ FAILED: {result.get('error','')[:100]}")
            results.append({"id": test["id"], "ok": False})
    return results


# ============================================================
# TEST 3: Garbage / hallucination detection
# ============================================================
def test_garbage_detection():
    print("\n" + "="*60)
    print("TEST 3: Garbage / hallucination detection")
    print("="*60)

    # Ask for a simple, verifiable fact
    tests = [
        ("math", "What is 17 * 23? Reply with only the number.", "391"),
        ("capital", "What is the capital of France? Reply with only the city name.", "Paris"),
        ("empty_translate", "Translate this Polish text to English:\n\n(empty)", None),
    ]
    for name, prompt, expected in tests:
        result = call_api_non_stream(prompt)
        if result["ok"]:
            content = result["content"].strip()
            if expected:
                ok = expected.lower() in content.lower()
                icon = "✅" if ok else "⚠️ "
                print(f"  {icon} [{name}] Expected '{expected}', got: '{content[:80]}'")
            else:
                # Check for garbage on empty input
                is_garbage = len(content) > 200
                icon = "⚠️  VERBOSE" if is_garbage else "✅"
                print(f"  {icon} [{name}] Empty input response: '{content[:120]}'")
        else:
            print(f"  ❌ [{name}] FAILED: {result.get('error','')[:80]}")


# ============================================================
# TEST 4: Concurrency stress test
# ============================================================
def test_concurrency():
    print("\n" + "="*60)
    print("TEST 4: Concurrency stress test")
    print("="*60)

    prompt = "Translate to English: Gdzie jest najbliższa stacja metra?"

    def worker(n):
        start = time.time()
        result = call_api_non_stream(prompt)
        elapsed = time.time() - start
        status = result["status"]
        ok = result["ok"]
        return {"n": n, "ok": ok, "status": status, "elapsed": elapsed, "error": result.get("error", "")}

    concurrency_levels = [1, 2, 4, 8, 12, 16]
    for level in concurrency_levels:
        print(f"\n  → Sending {level} concurrent requests...")
        start_all = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=level) as executor:
            futures = [executor.submit(worker, i) for i in range(level)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        total_time = time.time() - start_all

        ok_count = sum(1 for r in results if r["ok"])
        fail_count = level - ok_count
        statuses = [r["status"] for r in results]
        avg_time = sum(r["elapsed"] for r in results) / len(results)
        errors = [r["error"] for r in results if not r["ok"]]

        print(f"    ✅ Success: {ok_count}/{level} | ❌ Fail: {fail_count}")
        print(f"    Statuses: {statuses}")
        print(f"    Avg latency: {avg_time:.2f}s | Wall time: {total_time:.2f}s")
        if errors:
            print(f"    Errors: {list(set(errors))[:2]}")

        if fail_count > 0:
            print(f"    ⛔ Rate limit hit at concurrency={level}. Stopping.")
            break

        time.sleep(2)  # small breather between levels


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    print(f"\n🚀 NVIDIA API Test Suite — {MODEL}")
    print(f"   Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    basic_ok = test_basic()
    if not basic_ok:
        print("\n❌ Basic connectivity failed. Aborting further tests.")
        exit(1)

    test_translation_quality()
    test_garbage_detection()
    test_concurrency()

    print("\n\n✅ All tests completed.")
