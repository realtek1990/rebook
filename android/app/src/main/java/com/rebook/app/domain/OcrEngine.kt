package com.rebook.app.domain

import android.content.Context
import android.graphics.Bitmap
import android.graphics.pdf.PdfRenderer
import android.os.ParcelFileDescriptor
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import com.google.android.gms.tasks.Tasks
import com.rebook.app.data.AppConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import org.json.JSONArray
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import android.util.Base64

/**
 * PDF → text extraction supporting multiple OCR providers:
 *  - ML Kit (local, offline, always available)
 *  - Mistral OCR (cloud, best quality for scanned docs)
 *  - Gemini Cloud OCR (native PDF understanding)
 *
 * Dispatcher pattern: resolves provider from AppConfig and routes accordingly.
 * Auto mode: tries Mistral → Gemini → ML Kit.
 */
object OcrEngine {

    private const val RENDER_DPI_SCALE = 2
    private const val MISTRAL_OCR_MODEL_DEFAULT = "mistral-ocr-latest"
    private const val GEMINI_OCR_MODEL_DEFAULT  = "gemini-2.5-flash-lite"
    private const val GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
    private const val MISTRAL_OCR_URL = "https://api.mistral.ai/v1/ocr"

    private val OCR_PROMPT = """
        Wyciagnij caly tekst z tego dokumentu PDF jako czysty Markdown.

        Zasady:
        1. Uzywaj # dla tytulów rozdzialow i ## dla podrozdzialow.
        2. Kazdy akapit oddziel pusta linia.
        3. Zachowaj listy punktowane jako - item.
        4. Zachowaj listy numerowane jako 1. item.
        5. NIE dodawaj wlasnych komentarzy, podsumowań ani wstepow.
        6. Zwroc TYLKO tekst dokumentu w formacie Markdown.
    """.trimIndent()

    // ─── Public dispatcher ────────────────────────────────────────────────────

    /**
     * Main entry point. Dispatches to the correct OCR backend based on config.
     * Auto mode: Mistral → Gemini → ML Kit (with silent fallback).
     *
     * @return Extracted markdown text.
     */
    suspend fun ocrPdf(
        context: Context,
        pdfFile: File,
        config: AppConfig,
        onProgress: suspend (Int, String) -> Unit = { _, _ -> },
    ): String = withContext(Dispatchers.IO) {
        when (config.ocrProvider) {
            "mistral" -> ocrMistral(pdfFile, config, onProgress)
            "gemini"  -> ocrGemini(pdfFile, config, onProgress)
            "marker"  -> ocrMlKit(context, pdfFile, onProgress)
            else      -> ocrAuto(context, pdfFile, config, onProgress) // "auto"
        }
    }

    // ─── Auto mode ───────────────────────────────────────────────────────────

    private suspend fun ocrAuto(
        context: Context,
        pdfFile: File,
        config: AppConfig,
        onProgress: suspend (Int, String) -> Unit,
    ): String {
        val key = config.effectiveOcrApiKey

        if (key.isNotBlank()) {
            // Try Mistral first (best quality for scanned docs)
            try {
                return ocrMistral(pdfFile, config, onProgress)
            } catch (e: Exception) {
                onProgress(0, "⚠️ Mistral OCR niedostępny — próbuję Gemini…")
            }

            // Try Gemini if Mistral failed
            if (config.llmProvider.lowercase() == "gemini") {
                try {
                    return ocrGemini(pdfFile, config, onProgress)
                } catch (e: Exception) {
                    onProgress(0, "⚠️ Gemini OCR niedostępny — używam ML Kit…")
                }
            }
        }

        // Fallback to local ML Kit
        return ocrMlKit(context, pdfFile, onProgress)
    }

    // ─── Mistral OCR ─────────────────────────────────────────────────────────

    suspend fun ocrMistral(
        pdfFile: File,
        config: AppConfig,
        onProgress: suspend (Int, String) -> Unit = { _, _ -> },
    ): String = withContext(Dispatchers.IO) {
        val key = config.effectiveOcrApiKey
        require(key.isNotBlank()) { "Brak klucza Mistral OCR w ustawieniach." }

        val model = config.ocrModel.ifBlank { MISTRAL_OCR_MODEL_DEFAULT }

        onProgress(10, "Mistral OCR — przesyłanie PDF…")
        val b64 = Base64.encodeToString(pdfFile.readBytes(), Base64.NO_WRAP)

        val payload = JSONObject().apply {
            put("model", model)
            put("document", JSONObject().apply {
                put("type", "document_url")
                put("document_url", "data:application/pdf;base64,$b64")
            })
            put("include_image_base64", false)
        }

        onProgress(30, "Mistral OCR przetwarza dokument…")
        val result = httpPost(
            url = MISTRAL_OCR_URL,
            body = payload.toString(),
            headers = mapOf(
                "Content-Type" to "application/json",
                "Authorization" to "Bearer $key"
            )
        )

        val json = JSONObject(result)
        val pages = json.getJSONArray("pages")
        val sb = StringBuilder()
        for (i in 0 until pages.length()) {
            sb.append(pages.getJSONObject(i).optString("markdown", ""))
            if (i < pages.length() - 1) sb.append("\n\n")
        }

        val text = sb.toString().trim()
        onProgress(100, "✅ Mistral OCR: ${pages.length()} stron, ${text.length} znaków")
        text
    }

    // ─── Gemini Cloud OCR ────────────────────────────────────────────────────

    suspend fun ocrGemini(
        pdfFile: File,
        config: AppConfig,
        onProgress: suspend (Int, String) -> Unit = { _, _ -> },
    ): String = withContext(Dispatchers.IO) {
        val key = config.effectiveOcrApiKey
        require(key.isNotBlank()) { "Brak klucza Gemini API dla Cloud OCR." }

        val model = config.ocrModel.ifBlank { GEMINI_OCR_MODEL_DEFAULT }
        val b64 = Base64.encodeToString(pdfFile.readBytes(), Base64.NO_WRAP)

        onProgress(20, "Gemini Cloud OCR — przesyłanie PDF…")

        val payload = JSONObject().apply {
            put("contents", JSONArray().put(JSONObject().apply {
                put("parts", JSONArray().apply {
                    put(JSONObject().apply {
                        put("inline_data", JSONObject().apply {
                            put("mime_type", "application/pdf")
                            put("data", b64)
                        })
                    })
                    put(JSONObject().put("text", OCR_PROMPT))
                })
            }))
            put("generationConfig", JSONObject().apply {
                put("temperature", 0.0)
                put("maxOutputTokens", 65536)
            })
        }

        onProgress(40, "Gemini OCR przetwarza dokument…")
        val result = httpPost(
            url = "$GEMINI_BASE_URL/models/$model:generateContent?key=$key",
            body = payload.toString(),
            headers = mapOf("Content-Type" to "application/json")
        )

        val json = JSONObject(result)
        val candidates = json.getJSONArray("candidates")
        if (candidates.length() == 0) throw RuntimeException("Gemini OCR: brak odpowiedzi")

        val parts = candidates.getJSONObject(0)
            .getJSONObject("content")
            .getJSONArray("parts")
        val sb = StringBuilder()
        for (i in 0 until parts.length()) {
            sb.append(parts.getJSONObject(i).optString("text", ""))
        }
        val text = sb.toString().trim()
        onProgress(100, "✅ Gemini OCR: ${text.length} znaków")
        text
    }

    // ─── ML Kit (local, offline fallback) ────────────────────────────────────

    suspend fun ocrMlKit(
        context: Context,
        pdfFile: File,
        onProgress: suspend (Int, String) -> Unit = { _, _ -> },
    ): String = withContext(Dispatchers.IO) {
        val recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
        val fd = ParcelFileDescriptor.open(pdfFile, ParcelFileDescriptor.MODE_READ_ONLY)
        val renderer = PdfRenderer(fd)
        val pageCount = renderer.pageCount
        val pages = mutableListOf<String>()

        onProgress(0, "ML Kit OCR: 0/$pageCount")

        for (i in 0 until pageCount) {
            val page = renderer.openPage(i)
            val width = page.width * RENDER_DPI_SCALE
            val height = page.height * RENDER_DPI_SCALE
            val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
            page.render(bitmap, null, null, PdfRenderer.Page.RENDER_MODE_FOR_PRINT)
            page.close()

            val inputImage = InputImage.fromBitmap(bitmap, 0)
            val visionText = Tasks.await(recognizer.process(inputImage))

            val pageLines = StringBuilder()
            for (block in visionText.textBlocks) {
                val blockText = block.lines.joinToString(" ") { it.text }.trim()
                if (blockText.isBlank()) continue
                val isLikelyHeading = blockText.length < 80
                    && !blockText.endsWith(".")
                    && !blockText.endsWith(",")
                    && !blockText.endsWith(":")
                    && block.lines.size <= 2
                    && blockText.first().isUpperCase()

                if (isLikelyHeading) {
                    pageLines.appendLine()
                    pageLines.appendLine("## $blockText")
                    pageLines.appendLine()
                } else {
                    pageLines.appendLine(blockText)
                    pageLines.appendLine()
                }
            }
            pages.add(pageLines.toString().trim())
            bitmap.recycle()

            val pct = ((i + 1) * 100) / pageCount
            onProgress(pct, "ML Kit OCR: ${i + 1}/$pageCount")
        }

        renderer.close()
        fd.close()
        recognizer.close()
        pages.joinToString("\n\n---\n\n")
    }

    // ─── HTTP helper ─────────────────────────────────────────────────────────

    private fun httpPost(url: String, body: String, headers: Map<String, String>): String {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.requestMethod = "POST"
        conn.doOutput = true
        conn.connectTimeout = 30_000
        conn.readTimeout = 600_000
        headers.forEach { (k, v) -> conn.setRequestProperty(k, v) }

        conn.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }

        val code = conn.responseCode
        val stream = if (code in 200..299) conn.inputStream else conn.errorStream
        val resp = stream.bufferedReader().readText()

        if (code !in 200..299) {
            throw RuntimeException("HTTP $code: ${resp.take(300)}")
        }
        return resp
    }
}
