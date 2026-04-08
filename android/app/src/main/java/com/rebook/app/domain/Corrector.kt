package com.rebook.app.domain

import com.rebook.app.data.AppConfig
import kotlinx.coroutines.*

/**
 * AI text corrector/translator — Kotlin port of corrector.py.
 * Handles chunking, parallel processing, quality gate, and retry logic.
 */
object Corrector {

    private const val CHUNK_SIZE = 3000 // characters per chunk
    private const val MAX_PARALLEL = 15
    private const val MAX_RETRIES = 3

    /**
     * Build the system prompt for translation or correction.
     * Direct port of get_system_prompt() from corrector.py.
     */
    fun getSystemPrompt(translate: Boolean, langTo: String, langFrom: String): String {
        if (!translate) {
            return """Jesteś ekspertem od korekty tekstu z OCR. Twoim jedynym zadaniem jest poprawienie błędów powstałych podczas skanowania i rozpoznawania tekstu (OCR).

Zasady:
1. Połącz rozdzielone wyrazy (np. "roz dzielony" -> "rozdzielony")
2. Usuń losowe pogrubienia (znaczniki ** wewnątrz słów lub zdań, które nie mają sensu)
3. Popraw błędy interpunkcji
4. Popraw oczywiste literówki OCR (np. "rn" zamiast "m", "1" zamiast "l")
5. NIE zmieniaj treści, NIE dodawaj niczego, NIE parafrazuj
6. Zachowaj formatowanie markdown (nagłówki #, listy -, cytaty >) jeśli istnieją
7. NIE NUMERUJ akapitów — nie dodawaj cyfr (1., 2., 3.) ani numerów przed fragmentami tekstu jeśli ich nie było w oryginale.
8. Zwróć TYLKO poprawiony tekst, bez komentarzy ani przemyśleń"""
        }

        val frm = if (langFrom.isNotBlank()) "z języka: $langFrom" else "z języka źródłowego"
        val to = langTo.ifBlank { "polski" }

        val (ex1, ex2, ex3) = when {
            to.lowercase().startsWith("pol") -> Triple(
                "\"Chapter 1—My Life\" → \"# Rozdział 1 — Moje życie\"",
                "\"Introduction\" → \"# Wprowadzenie\"",
                "\"Foreword\" → \"# Przedmowa\""
            )
            to.lowercase().startsWith("ang") || to.lowercase().startsWith("eng") -> Triple(
                "\"Rozdział 1 — Moje życie\" → \"# Chapter 1 — My Life\"",
                "\"Wprowadzenie\" → \"# Introduction\"",
                "\"Przedmowa\" → \"# Foreword\""
            )
            to.lowercase().startsWith("niem") || to.lowercase().startsWith("deu") -> Triple(
                "\"Chapter 1—My Life\" → \"# Kapitel 1 — Mein Leben\"",
                "\"Introduction\" → \"# Einleitung\"",
                "\"Foreword\" → \"# Vorwort\""
            )
            else -> Triple(
                "\"Chapter 1—My Life\" → \"# [Chapter 1 — My Life in $to]\"",
                "\"Introduction\" → \"# [Introduction in $to]\"",
                "\"Foreword\" → \"# [Foreword in $to]\""
            )
        }

        return """Jesteś profesjonalnym tłumaczem książek. Twoim zadaniem jest przetłumaczenie poniższego tekstu $frm na język $to.

Zasady:
1. Tekst ma być przetłumaczony w sposób naturalny dla czytelnika z zachowaniem najwyższej poprawności oraz oryginalnego kontekstu wyjściowego autora.
2. Przetłumacz ABSOLUTNIE WSZYSTKO na język $to — w tym nagłówki, cytaty, podpisy, dialogi i wszelkie fragmenty w języku obcym. NIE zostawiaj niczego w oryginalnym języku.
3. ZACHOWAJ FORMATOWANIE Markdown (nagłówki #, pogrubienia **, listy -, cytaty >).
4. NAGŁÓWKI ROZDZIAŁÓW: Jeśli tekst zawiera nagłówki — przetłumacz je:
   - $ex1
   - $ex2
   - $ex3
5. NIE ŁĄCZ i NIE POMIJAJ akapitów. Każdy akapit z oryginału MUSI pojawić się w tłumaczeniu.
6. NAGŁÓWKI (linie zaczynające się od #): max 1-2 zdania. Długie akapity po # zamień na **tekst**.
7. WYCZYŚĆ ARTEFAKTY: XML, HTML, DOCTYPE, encje HTML — USUŃ i zostaw czysty tekst.
8. NIE NUMERUJ akapitów — nie dodawaj cyfr (1., 2., 3.) ani numerów przed fragmentami tekstu jeśli ich nie było w oryginale.
9. Zwróć TYLKO wynik tłumaczenia."""
    }

    /**
     * Split text into chunks of approximately CHUNK_SIZE characters,
     * breaking at paragraph boundaries.
     */
    fun chunkText(text: String, maxSize: Int = CHUNK_SIZE): List<String> {
        if (text.length <= maxSize) return listOf(text)

        val chunks = mutableListOf<String>()
        val paragraphs = text.split("\n\n")
        val current = StringBuilder()

        for (para in paragraphs) {
            if (current.length + para.length + 2 > maxSize && current.isNotEmpty()) {
                chunks.add(current.toString().trim())
                current.clear()
            }
            if (current.isNotEmpty()) current.append("\n\n")
            current.append(para)
        }
        if (current.isNotEmpty()) {
            chunks.add(current.toString().trim())
        }
        return chunks
    }

    /**
     * Process all chunks in parallel with AI correction/translation.
     * Port of correct_text_parallel() from corrector.py.
     */
    suspend fun processText(
        text: String,
        config: AppConfig,
        translate: Boolean = false,
        langFrom: String = "",
        langTo: String = "polski",
        onProgress: suspend (Int, String) -> Unit = { _, _ -> },
    ): String = coroutineScope {
        if (config.apiKey.isBlank() || config.llmProvider.isBlank()) return@coroutineScope text

        val systemPrompt = getSystemPrompt(translate, langTo, langFrom)
        val chunks = chunkText(text)
        val results = Array(chunks.size) { "" }
        val semaphore = kotlinx.coroutines.sync.Semaphore(MAX_PARALLEL)
        var completed = 0

        val jobs = chunks.mapIndexed { index, chunk ->
            async {
                semaphore.acquire()
                try {
                    var result = chunk
                    for (attempt in 1..MAX_RETRIES) {
                        try {
                            result = AiProvider.complete(
                                systemPrompt = systemPrompt,
                                userText = chunk,
                                config = config,
                            )
                            break
                        } catch (e: Exception) {
                            if (attempt == MAX_RETRIES) {
                                // Fallback to original text on final failure
                                result = chunk
                            } else {
                                delay(1000L * attempt) // exponential backoff
                            }
                        }
                    }
                    results[index] = result
                    completed++
                    val pct = (completed * 100) / chunks.size
                    val action = if (translate) "Tłumaczenie" else "Korekta"
                    onProgress(pct, "$action: $completed/${chunks.size}")
                } finally {
                    semaphore.release()
                }
            }
        }

        jobs.awaitAll()
        results.joinToString("\n\n")
    }

    /**
     * Verify translation quality by comparing original + translated chunks.
     * Sends both to AI for quality check and re-translation of errors.
     * Port of verify_translation() from corrector.py.
     */
    suspend fun verifyTranslation(
        original: String,
        translated: String,
        config: AppConfig,
        langFrom: String = "",
        langTo: String = "polski",
        onProgress: suspend (Int, String) -> Unit = { _, _ -> },
    ): String = coroutineScope {
        if (config.apiKey.isBlank()) return@coroutineScope translated

        val origChunks = chunkText(original)
        val transChunks = chunkText(translated)

        // Align chunks — use min of both sizes
        val count = minOf(origChunks.size, transChunks.size)
        if (count == 0) return@coroutineScope translated

        val to = langTo.ifBlank { "polski" }
        val frm = if (langFrom.isNotBlank()) langFrom else "język źródłowy"

        val verifyPrompt = """Jesteś ekspertem weryfikacji tłumaczeń. Otrzymujesz ORYGINAŁ i TŁUMACZENIE tekstu z $frm na $to.

Zasady:
1. Sprawdź czy tłumaczenie jest KOMPLETNE — żadne akapity/zdania nie zostały pominięte.
2. Sprawdź czy sens oryginału jest wiernie oddany.
3. Popraw nienaturalne, sztywne sformułowania na płynny, idiomatyczny język $to.
4. NIE dodawaj niczego od siebie. NIE komentuj. Zwróć TYLKO poprawione tłumaczenie.
5. Jeśli tłumaczenie jest poprawne — zwróć je bez zmian.
6. Zachowaj formatowanie Markdown (nagłówki #, listy -, pogrubienia **, cytaty >)."""

        val results = Array(count) { "" }
        val semaphore = kotlinx.coroutines.sync.Semaphore(MAX_PARALLEL)
        var completed = 0

        val jobs = (0 until count).map { index ->
            async {
                semaphore.acquire()
                try {
                    val userMsg = "=== ORYGINAŁ ===\n${origChunks[index]}\n\n=== TŁUMACZENIE ===\n${transChunks[index]}"
                    var result = transChunks[index]
                    for (attempt in 1..MAX_RETRIES) {
                        try {
                            result = AiProvider.complete(
                                systemPrompt = verifyPrompt,
                                userText = userMsg,
                                config = config,
                            )
                            break
                        } catch (e: Exception) {
                            if (attempt < MAX_RETRIES) delay(1000L * attempt)
                        }
                    }
                    results[index] = result
                    completed++
                    val pct = (completed * 100) / count
                    onProgress(pct, "🔍 Weryfikacja: $completed/$count")
                } finally {
                    semaphore.release()
                }
            }
        }

        jobs.awaitAll()

        // Append any remaining translated chunks that weren't verified
        val remaining = if (transChunks.size > count) {
            transChunks.drop(count).joinToString("\n\n")
        } else ""

        val verifiedPart = results.joinToString("\n\n")
        if (remaining.isNotBlank()) "$verifiedPart\n\n$remaining" else verifiedPart
    }
}
