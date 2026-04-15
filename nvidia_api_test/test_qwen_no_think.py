#!/usr/bin/env python3
"""
NVIDIA API Test — Qwen3.5-122B bez thinking + wysoka współbieżność
"""

import requests
import json
import time
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
    ("simple",       "Dzień dobry! Jak się masz?"),
    ("technical",    "Konwersja pliku PDF do formatu EPUB wymaga precyzyjnego zachowania układu strony."),
    ("literary",     "Stary człowiek siedział przy oknie i patrzył na deszcz spływający po szybie. Myślał o minionych latach, które ulotniły się jak dym."),
    ("complex_book", "Rozdział trzeci. Ewolucja sztucznej inteligencji w ostatniej dekadzie przyniosła rewolucyjne zmiany w sposobie przetwarzania języka naturalnego."),
]


def call_stream(prompt: str, thinking: bool = False) -> dict:
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 4096,
        "temperature": 0.60,
        "top_p": 0.95,
        "stream": True,
        "chat_template_kwargs": {"enable_thinking": thinking},
    }
    start = time.time()
    content_parts = []
    thinking_parts = []
    first_token_time = None

    try:
        r = requests.post(INVOKE_URL, headers=HEADERS_STREAM, json=payload, stream=True, timeout=120)
        if r.status_code != 200:
            return {"ok": False, "status": r.status_code, "error": r.text[:200],
                    "content": "", "thinking_chars": 0, "elapsed": time.time() - start}

        for line in r.iter_lines():
            if not line:
                continue
            dec = line.decode("utf-8")
            if not dec.startswith("data: "):
                continue
            data_str = dec[6:]
            if data_str.strip() == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                delta = chunk["choices"][0].get("delta", {})
                piece = delta.get("content") or ""
                reasoning = delta.get("reasoning_content") or ""
                if piece and first_token_time is None:
                    first_token_time = time.time() - start
                if reasoning:
                    thinking_parts.append(reasoning)
                if piece:
                    content_parts.append(piece)
            except Exception:
                pass

        elapsed = time.time() - start
        return {
            "ok": True, "status": 200,
            "content": "".join(content_parts).strip(),
            "thinking_chars": len("".join(thinking_parts)),
            "elapsed": elapsed,
            "ttft": first_token_time,
        }
    except Exception as e:
        return {"ok": False, "status": -1, "error": str(e),
                "content": "", "thinking_chars": 0, "elapsed": time.time() - start}


def call_non_stream(prompt: str, thinking: bool = False, max_tokens: int = 512) -> dict:
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.60,
        "top_p": 0.95,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": thinking},
    }
    start = time.time()
    try:
        r = requests.post(INVOKE_URL, headers=HEADERS_JSON, json=payload, timeout=120)
        elapsed = time.time() - start
        if r.status_code == 200:
            data = r.json()
            content = (data["choices"][0]["message"].get("content") or "").strip()
            return {"ok": True, "status": 200, "content": content, "elapsed": elapsed}
        else:
            return {"ok": False, "status": r.status_code,
                    "error": r.text[:200], "content": "", "elapsed": elapsed}
    except Exception as e:
        return {"ok": False, "status": -1, "error": str(e), "content": "", "elapsed": time.time() - start}


# ============================================================
# TEST 1: Porównanie thinking=True vs thinking=False  (streaming)
# ============================================================
def test_thinking_comparison():
    print("\n" + "="*60)
    print("TEST 1: Thinking ON vs OFF — latencja i jakość")
    print("="*60)
    prompt = "Translate to English: Stary człowiek siedział przy oknie i patrzył na deszcz."

    print("\n  [thinking=True]")
    r_on = call_stream(prompt, thinking=True)
    if r_on["ok"]:
        print(f"  ✅ {r_on['elapsed']:.2f}s | TTFT: {r_on['ttft']:.2f}s | think: {r_on['thinking_chars']} chars")
        print(f"     → {r_on['content'][:150]}")
    else:
        print(f"  ❌ {r_on['status']}: {r_on.get('error','')[:80]}")

    print("\n  [thinking=False]")
    r_off = call_stream(prompt, thinking=False)
    if r_off["ok"]:
        print(f"  ✅ {r_off['elapsed']:.2f}s | TTFT: {r_off['ttft']:.2f}s | think: {r_off['thinking_chars']} chars")
        print(f"     → {r_off['content'][:150]}")
    else:
        print(f"  ❌ {r_off['status']}: {r_off.get('error','')[:80]}")

    if r_on["ok"] and r_off["ok"]:
        speedup = r_on["elapsed"] / r_off["elapsed"]
        print(f"\n  ⚡ Speedup (thinking=False): {speedup:.1f}×  ({r_on['elapsed']:.1f}s → {r_off['elapsed']:.1f}s)")


# ============================================================
# TEST 2: Jakość tłumaczenia bez myślenia
# ============================================================
def test_translation_no_think():
    print("\n" + "="*60)
    print("TEST 2: Jakość tłumaczenia bez thinking (streaming)")
    print("="*60)
    for name, text in TRANSLATION_TESTS:
        prompt = f"Translate the following Polish text to English. Output ONLY the translation.\n\nPolish:\n{text}"
        print(f"\n  [{name}] {text[:55]}...")
        r = call_stream(prompt, thinking=False)
        if r["ok"]:
            print(f"  ✅ {r['elapsed']:.2f}s | think: {r['thinking_chars']}c")
            print(f"     → {r['content'][:150]}")
        else:
            print(f"  ❌ {r['status']}: {r.get('error','')[:80]}")


# ============================================================
# TEST 3: Współbieżność BEZ thinking — push do 32+
# ============================================================
def test_concurrency_no_think():
    print("\n" + "="*60)
    print("TEST 3: Współbieżność — thinking=False, push do 32+")
    print("="*60)
    prompt = "Translate to English: Gdzie jest najbliższa stacja metra?"

    def worker(n):
        r = call_non_stream(prompt, thinking=False)
        return {"n": n, "ok": r["ok"], "status": r["status"],
                "elapsed": r["elapsed"], "error": r.get("error", "")}

    levels = [8, 12, 16, 20, 24, 32]
    for level in levels:
        print(f"\n  → {level} równoległych requestów...")
        start_all = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=level) as ex:
            futures = [ex.submit(worker, i) for i in range(level)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        wall = time.time() - start_all

        ok_n = sum(1 for r in results if r["ok"])
        fail_n = level - ok_n
        statuses = sorted([r["status"] for r in results])
        avg_lat = sum(r["elapsed"] for r in results) / len(results)
        errors = list(set(r["error"] for r in results if not r["ok"]))

        rate_400 = statuses.count(429)
        icon = "✅" if fail_n == 0 else f"⚠️  ({rate_400}× 429)"
        print(f"    {icon} OK: {ok_n}/{level} | ❌ Fail: {fail_n}")
        print(f"    Statuses: {statuses}")
        print(f"    Avg lat: {avg_lat:.2f}s | Wall: {wall:.2f}s | Throughput: {ok_n/wall:.1f} req/s")
        if errors:
            print(f"    Errors: {errors[:1]}")

        if fail_n > level * 0.25:  # zatrzymaj jeśli >25% failuje
            print(f"    ⛔ Zbyt wiele błędów. Zatrzymuję.")
            break
        time.sleep(2)


# ============================================================
# TEST 4: Współbieżność Z thinking — dla porównania przy wyższych wartościach
# ============================================================
def test_concurrency_with_think():
    print("\n" + "="*60)
    print("TEST 4: Współbieżność — thinking=True (for reference, 20+)")
    print("="*60)
    prompt = "Translate to English: Gdzie jest najbliższa stacja metra?"

    def worker(n):
        r = call_non_stream(prompt, thinking=True)
        return {"n": n, "ok": r["ok"], "status": r["status"],
                "elapsed": r["elapsed"], "error": r.get("error", "")}

    levels = [20, 24, 32]
    for level in levels:
        print(f"\n  → {level} równoległych requestów (thinking=True)...")
        start_all = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=level) as ex:
            futures = [ex.submit(worker, i) for i in range(level)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        wall = time.time() - start_all

        ok_n = sum(1 for r in results if r["ok"])
        fail_n = level - ok_n
        statuses = sorted([r["status"] for r in results])
        avg_lat = sum(r["elapsed"] for r in results) / len(results)
        errors = list(set(r["error"] for r in results if not r["ok"]))
        rate_400 = statuses.count(429)
        icon = "✅" if fail_n == 0 else f"⚠️  ({rate_400}× 429)"
        print(f"    {icon} OK: {ok_n}/{level} | ❌ Fail: {fail_n}")
        print(f"    Statuses: {statuses}")
        print(f"    Avg lat: {avg_lat:.2f}s | Wall: {wall:.2f}s | Throughput: {ok_n/wall:.1f} req/s")
        if errors:
            print(f"    Errors: {errors[:1]}")
        if fail_n > level * 0.25:
            print(f"    ⛔ Zbyt wiele błędów. Zatrzymuję.")
            break
        time.sleep(2)


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    print(f"\n🚀 Qwen3.5-122B — thinking OFF vs ON + wysoka współbieżność")
    print(f"   Model: {MODEL}")
    print(f"   Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    test_thinking_comparison()
    test_translation_no_think()
    test_concurrency_no_think()
    test_concurrency_with_think()

    print("\n\n✅ Wszystkie testy zakończone.")
