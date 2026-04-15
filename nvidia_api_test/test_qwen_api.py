#!/usr/bin/env python3
"""
NVIDIA API Test Suite — Qwen3.5-122B (thinking mode)
Comparison against mistral-small-4-119b-2603
"""

import requests
import json
import time
import threading
import concurrent.futures
from datetime import datetime

INVOKE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
API_KEY = "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"
MODEL = "qwen/qwen3.5-122b-a10b"

HEADERS_STREAM = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "text/event-stream"
}
HEADERS_JSON = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json"
}

TRANSLATION_TESTS = [
    {
        "id": "simple",
        "text": "Dzień dobry! Jak się masz?",
    },
    {
        "id": "technical",
        "text": "Konwersja pliku PDF do formatu EPUB wymaga precyzyjnego zachowania układu strony.",
    },
    {
        "id": "literary",
        "text": "Stary człowiek siedział przy oknie i patrzył na deszcz spływający po szybie. Myślał o minionych latach, które ulotniły się jak dym.",
    },
    {
        "id": "complex_book",
        "text": "Rozdział trzeci. Ewolucja sztucznej inteligencji w ostatniej dekadzie przyniosła rewolucyjne zmiany w sposobie przetwarzania języka naturalnego. Modele językowe osiągnęły poziom rozumienia tekstu, który jeszcze dekadę temu wydawał się niemożliwy.",
    },
]


def call_api_stream(prompt: str, temperature: float = 0.60) -> dict:
    """Call API in streaming mode, collect full response, measure thinking tokens."""
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 8192,
        "temperature": temperature,
        "top_p": 0.95,
        "stream": True,
        "chat_template_kwargs": {"enable_thinking": True},
    }
    start = time.time()
    thinking_tokens = []
    content_tokens = []
    in_thinking = False
    first_token_time = None

    try:
        response = requests.post(
            INVOKE_URL, headers=HEADERS_STREAM, json=payload, stream=True, timeout=120
        )
        if response.status_code != 200:
            elapsed = time.time() - start
            return {
                "ok": False, "content": "", "thinking": "",
                "elapsed": elapsed, "status": response.status_code,
                "error": response.text[:300]
            }

        for line in response.iter_lines():
            if not line:
                continue
            decoded = line.decode("utf-8")
            if decoded.startswith("data: "):
                data_str = decoded[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    piece = delta.get("content", "") or ""
                    reasoning = delta.get("reasoning_content", "") or ""

                    if piece and first_token_time is None:
                        first_token_time = time.time() - start

                    # Collect thinking (some models put it in reasoning_content)
                    if reasoning:
                        thinking_tokens.append(reasoning)

                    # Detect inline <think> tags as fallback
                    if "<think>" in piece:
                        in_thinking = True
                    if "</think>" in piece:
                        in_thinking = False
                        piece = piece.split("</think>")[-1]
                    elif in_thinking:
                        thinking_tokens.append(piece)
                        piece = ""

                    if piece and not in_thinking:
                        content_tokens.append(piece)
                except json.JSONDecodeError:
                    pass

        elapsed = time.time() - start
        full_content = "".join(content_tokens).strip()
        full_thinking = "".join(thinking_tokens).strip()
        return {
            "ok": True,
            "content": full_content,
            "thinking": full_thinking,
            "thinking_chars": len(full_thinking),
            "elapsed": elapsed,
            "ttft": first_token_time,
            "status": 200,
        }

    except Exception as e:
        elapsed = time.time() - start
        return {"ok": False, "content": "", "thinking": "", "elapsed": elapsed, "status": -1, "error": str(e)}


def call_api_non_stream(prompt: str, temperature: float = 0.60) -> dict:
    """Non-streaming fallback for concurrency tests (faster to manage)."""
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 512,
        "temperature": temperature,
        "top_p": 0.95,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": True},
    }
    start = time.time()
    try:
        response = requests.post(INVOKE_URL, headers=HEADERS_JSON, json=payload, timeout=120)
        elapsed = time.time() - start
        if response.status_code == 200:
            data = response.json()
            content = data["choices"][0]["message"].get("content", "") or ""
            return {"ok": True, "content": content.strip(), "elapsed": elapsed, "status": 200}
        else:
            return {"ok": False, "content": "", "elapsed": elapsed,
                    "status": response.status_code, "error": response.text[:300]}
    except Exception as e:
        elapsed = time.time() - start
        return {"ok": False, "content": "", "elapsed": elapsed, "status": -1, "error": str(e)}


# ============================================================
# TEST 1: Basic connectivity + thinking chain visibility
# ============================================================
def test_basic():
    print("\n" + "="*60)
    print("TEST 1: Basic connectivity + thinking chain")
    print("="*60)
    result = call_api_stream("Say hello in one sentence.")
    if result["ok"]:
        print(f"  ✅ OK | total: {result['elapsed']:.2f}s | TTFT: {result.get('ttft', '?')}s")
        print(f"  Thinking chars: {result['thinking_chars']}")
        if result["thinking"]:
            print(f"  Thinking snippet: {result['thinking'][:150]}...")
        print(f"  Response: {result['content'][:200]}")
    else:
        print(f"  ❌ FAILED: HTTP {result['status']}")
        print(f"  Error: {result.get('error','')}")
    return result["ok"]


# ============================================================
# TEST 2: Translation quality (streaming, with thinking)
# ============================================================
def test_translation_quality():
    print("\n" + "="*60)
    print("TEST 2: Translation quality (PL -> EN) + thinking overhead")
    print("="*60)
    results = []
    for test in TRANSLATION_TESTS:
        prompt = (
            "Translate the following Polish text to English. "
            "Output ONLY the English translation, nothing else.\n\n"
            f"Polish text:\n{test['text']}"
        )
        print(f"\n  [{test['id']}] Input: {test['text'][:60]}...")
        result = call_api_stream(prompt)
        if result["ok"]:
            content = result["content"]
            print(f"  ✅ [{result['elapsed']:.2f}s | think: {result['thinking_chars']}chars]")
            print(f"     Output: {content[:150]}")
            if result["thinking"]:
                print(f"     Thinking: {result['thinking'][:100]}...")
            results.append({
                "id": test["id"], "ok": True,
                "output": content,
                "elapsed": result["elapsed"],
                "thinking_chars": result["thinking_chars"]
            })
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
    tests = [
        ("math", "What is 17 * 23? Reply with only the number.", "391"),
        ("capital", "What is the capital of France? Reply with only the city name.", "Paris"),
        ("empty_translate", "Translate this Polish text to English:\n\n(empty)", None),
    ]
    for name, prompt, expected in tests:
        result = call_api_stream(prompt)
        if result["ok"]:
            content = result["content"].strip()
            if expected:
                ok = expected.lower() in content.lower()
                icon = "✅" if ok else "⚠️ "
                print(f"  {icon} [{name}] Expected '{expected}', got: '{content[:80]}'  [⏱ {result['elapsed']:.1f}s, 💭 {result['thinking_chars']}c]")
            else:
                is_garbage = len(content) > 300
                icon = "⚠️  VERBOSE" if is_garbage else "✅"
                print(f"  {icon} [{name}] Empty input: '{content[:120]}'  [⏱ {result['elapsed']:.1f}s]")
        else:
            print(f"  ❌ [{name}] FAILED: {result.get('error','')[:80]}")


# ============================================================
# TEST 4: Concurrency stress test (non-stream for speed)
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
        return {
            "n": n, "ok": result["ok"], "status": result["status"],
            "elapsed": elapsed, "error": result.get("error", "")
        }

    concurrency_levels = [1, 2, 4, 8, 12, 16]
    prev_failed = False
    for level in concurrency_levels:
        if prev_failed:
            break
        print(f"\n  → Sending {level} concurrent requests...")
        start_all = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=level) as executor:
            futures = [executor.submit(worker, i) for i in range(level)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        total_time = time.time() - start_all

        ok_count = sum(1 for r in results if r["ok"])
        fail_count = level - ok_count
        statuses = sorted([r["status"] for r in results])
        avg_time = sum(r["elapsed"] for r in results) / len(results)
        errors = list(set(r["error"] for r in results if not r["ok"]))

        print(f"    ✅ Success: {ok_count}/{level} | ❌ Fail: {fail_count}")
        print(f"    Statuses: {statuses}")
        print(f"    Avg latency: {avg_time:.2f}s | Wall time: {total_time:.2f}s")
        if errors:
            print(f"    Errors: {errors[:2]}")
        if fail_count > 0:
            print(f"    ⛔ Rate limit hit at concurrency={level}. Stopping.")
            prev_failed = True

        time.sleep(2)


# ============================================================
# SUMMARY vs Mistral
# ============================================================
def print_comparison_header():
    print("\n" + "="*60)
    print("COMPARISON REFERENCE (from previous Mistral test)")
    print("="*60)
    print("  Model   : mistralai/mistral-small-4-119b-2603")
    print("  Latency : ~0.8–0.9s/request")
    print("  Thinking: NONE (no chain-of-thought)")
    print("  Concur. : 12 safe, fail at 16")
    print("  Quality : Very good, no hallucinations")
    print()
    print("  Model   : qwen/qwen3.5-122b-a10b  ← THIS TEST")
    print("  Thinking: YES (enable_thinking=True)")
    print("  Expect  : Slower but potentially higher accuracy")


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    print(f"\n🚀 NVIDIA API Test Suite — {MODEL} (thinking mode)")
    print(f"   Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print_comparison_header()

    basic_ok = test_basic()
    if not basic_ok:
        print("\n❌ Basic connectivity failed. Aborting further tests.")
        exit(1)

    test_translation_quality()
    test_garbage_detection()
    test_concurrency()

    print("\n\n✅ All tests completed.")
