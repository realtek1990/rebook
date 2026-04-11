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
    private const val GEMINI_OCR_MODEL_DEFAULT  = "gemini-3.1-flash-lite-preview"
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

    private const val SEGMENT_SIZE = 100 // pages per cloud API call

    // ─── PDF page helpers ─────────────────────────────────────────────────────

    /**
     * Get page count of a PDF using PdfRenderer.
     */
    fun getPdfPageCount(context: Context, pdfFile: File): Int {
        val fd = ParcelFileDescriptor.open(pdfFile, ParcelFileDescriptor.MODE_READ_ONLY)
        val renderer = PdfRenderer(fd)
        val count = renderer.pageCount
        renderer.close()
        fd.close()
        return count
    }

    /**
     * Extract pages [pageStart, pageEnd] (1-indexed, inclusive) from a PDF.
     * Returns a temp File containing only the selected pages.
     */
    private fun splitPdfPages(context: Context, pdfFile: File, pageStart: Int, pageEnd: Int): File {
        val fd = ParcelFileDescriptor.open(pdfFile, ParcelFileDescriptor.MODE_READ_ONLY)
        val renderer = PdfRenderer(fd)
        val totalPages = renderer.pageCount
        val ps = (pageStart - 1).coerceAtLeast(0)
        val pe = (pageEnd - 1).coerceAtMost(totalPages - 1)

        val doc = android.graphics.pdf.PdfDocument()
        for (i in ps..pe) {
            val srcPage = renderer.openPage(i)
            val w = srcPage.width
            val h = srcPage.height
            val pageInfo = android.graphics.pdf.PdfDocument.PageInfo.Builder(w * RENDER_DPI_SCALE, h * RENDER_DPI_SCALE, i).create()
            val newPage = doc.startPage(pageInfo)

            val bitmap = Bitmap.createBitmap(w * RENDER_DPI_SCALE, h * RENDER_DPI_SCALE, Bitmap.Config.ARGB_8888)
            srcPage.render(bitmap, null, null, PdfRenderer.Page.RENDER_MODE_FOR_PRINT)
            srcPage.close()

            val canvas = newPage.canvas
            canvas.drawBitmap(bitmap, 0f, 0f, null)
            bitmap.recycle()
            doc.finishPage(newPage)
        }
        renderer.close()
        fd.close()

        val tmpFile = File(context.cacheDir, "segment_${pageStart}_${pageEnd}.pdf")
        tmpFile.outputStream().use { doc.writeTo(it) }
        doc.close()
        return tmpFile
    }

    /**
     * Read PDF bytes with optional page range extraction.
     * If no range, reads the whole file.
     */
    private fun readPdfBytes(
        context: Context, pdfFile: File, pageStart: Int, pageEnd: Int, totalPages: Int
    ): ByteArray {
        val ps = if (pageStart > 0) pageStart else 1
        val pe = if (pageEnd > 0) pageEnd.coerceAtMost(totalPages) else totalPages
        return if (ps > 1 || pe < totalPages) {
            val tmpFile = splitPdfPages(context, pdfFile, ps, pe)
            val bytes = tmpFile.readBytes()
            tmpFile.delete()
            bytes
        } else {
            pdfFile.readBytes()
        }
    }

    // ─── Public dispatcher ────────────────────────────────────────────────────

    /**
     * Main entry point. Dispatches to the correct OCR backend based on config.
     * Auto mode: Mistral → Gemini → ML Kit (with silent fallback).
     *
     * @param pageStart First page (1-indexed, 0 = from beginning)
     * @param pageEnd Last page (1-indexed, 0 = to end)
     * @return Extracted markdown text.
     */
    suspend fun ocrPdf(
        context: Context,
        pdfFile: File,
        config: AppConfig,
        pageStart: Int = 0,
        pageEnd: Int = 0,
        onProgress: suspend (Int, String) -> Unit = { _, _ -> },
    ): String = withContext(Dispatchers.IO) {
        when (config.ocrProvider) {
            "mistral" -> ocrMistral(context, pdfFile, config, pageStart, pageEnd, onProgress)
            "gemini"  -> ocrGemini(context, pdfFile, config, pageStart, pageEnd, onProgress)
            "marker"  -> ocrMlKit(context, pdfFile, pageStart, pageEnd, onProgress)
            else      -> ocrAuto(context, pdfFile, config, pageStart, pageEnd, onProgress) // "auto"
        }
    }

    // ─── Auto mode ───────────────────────────────────────────────────────────

    private suspend fun ocrAuto(
        context: Context,
        pdfFile: File,
        config: AppConfig,
        pageStart: Int,
        pageEnd: Int,
        onProgress: suspend (Int, String) -> Unit,
    ): String {
        val key = config.effectiveOcrApiKey

        if (key.isNotBlank()) {
            // Try Mistral first (best quality for scanned docs)
            try {
                return ocrMistral(context, pdfFile, config, pageStart, pageEnd, onProgress)
            } catch (e: Exception) {
                onProgress(0, "⚠️ Mistral OCR niedostępny — próbuję Gemini…")
            }

            // Try Gemini if Mistral failed
            if (config.llmProvider.lowercase() == "gemini") {
                try {
                    return ocrGemini(context, pdfFile, config, pageStart, pageEnd, onProgress)
                } catch (e: Exception) {
                    onProgress(0, "⚠️ Gemini OCR niedostępny — używam ML Kit…")
                }
            }
        }

        // Fallback to local ML Kit
        return ocrMlKit(context, pdfFile, pageStart, pageEnd, onProgress)
    }

    // ─── Mistral OCR ─────────────────────────────────────────────────────────

    suspend fun ocrMistral(
        context: Context,
        pdfFile: File,
        config: AppConfig,
        pageStart: Int = 0,
        pageEnd: Int = 0,
        onProgress: suspend (Int, String) -> Unit = { _, _ -> },
    ): String = withContext(Dispatchers.IO) {
        val key = config.effectiveOcrApiKey
        require(key.isNotBlank()) { "Brak klucza Mistral OCR w ustawieniach." }

        val model = config.ocrModel.ifBlank { MISTRAL_OCR_MODEL_DEFAULT }
        val totalPages = getPdfPageCount(context, pdfFile)
        val ps = if (pageStart > 0) pageStart else 1
        val pe = if (pageEnd > 0) pageEnd.coerceAtMost(totalPages) else totalPages
        val pageCount = pe - ps + 1

        if (ps > 1 || pe < totalPages) {
            onProgress(5, "Mistral OCR — strony $ps–$pe z $totalPages…")
        }

        // Auto-segment large ranges
        if (pageCount > SEGMENT_SIZE) {
            val allParts = mutableListOf<String>()
            val numSegments = (pageCount + SEGMENT_SIZE - 1) / SEGMENT_SIZE
            for (segIdx in 0 until numSegments) {
                val segStart = ps + segIdx * SEGMENT_SIZE
                val segEnd = (ps + (segIdx + 1) * SEGMENT_SIZE - 1).coerceAtMost(pe)
                val pct = 10 + 80 * segIdx / numSegments
                onProgress(pct, "Mistral OCR — segment ${segIdx+1}/$numSegments (strony $segStart–$segEnd)…")

                val segBytes = readPdfBytes(context, pdfFile, segStart, segEnd, totalPages)
                val segText = mistralOcrSingle(key, model, segBytes)
                if (segText.isNotBlank()) allParts.add(segText)

                if (segIdx < numSegments - 1) {
                    kotlinx.coroutines.delay(2000) // rate limit courtesy
                }
            }
            val text = allParts.joinToString("\n\n").trim()
            onProgress(100, "✅ Mistral OCR zakończone ($pageCount stron, ${text.length} znaków)")
            return@withContext text
        }

        // Single request
        onProgress(10, "Mistral OCR — $pageCount stron…")
        val pdfBytes = readPdfBytes(context, pdfFile, ps, pe, totalPages)
        val text = mistralOcrSingle(key, model, pdfBytes)
        onProgress(100, "✅ Mistral OCR: $pageCount stron, ${text.length} znaków")
        text
    }

    private fun mistralOcrSingle(key: String, model: String, pdfBytes: ByteArray): String {
        val b64 = Base64.encodeToString(pdfBytes, Base64.NO_WRAP)
        val payload = JSONObject().apply {
            put("model", model)
            put("document", JSONObject().apply {
                put("type", "document_url")
                put("document_url", "data:application/pdf;base64,$b64")
            })
            put("include_image_base64", false)
        }
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
            val md = pages.getJSONObject(i).optString("markdown", "")
            if (md.isNotBlank()) {
                if (sb.isNotEmpty()) sb.append("\n\n")
                sb.append(md)
            }
        }
        return sb.toString().trim()
    }

    // ─── Gemini Cloud OCR ────────────────────────────────────────────────────

    suspend fun ocrGemini(
        context: Context,
        pdfFile: File,
        config: AppConfig,
        pageStart: Int = 0,
        pageEnd: Int = 0,
        onProgress: suspend (Int, String) -> Unit = { _, _ -> },
    ): String = withContext(Dispatchers.IO) {
        val key = config.effectiveOcrApiKey
        require(key.isNotBlank()) { "Brak klucza Gemini API dla Cloud OCR." }

        val model = config.ocrModel.ifBlank { GEMINI_OCR_MODEL_DEFAULT }
        val totalPages = getPdfPageCount(context, pdfFile)
        val ps = if (pageStart > 0) pageStart else 1
        val pe = if (pageEnd > 0) pageEnd.coerceAtMost(totalPages) else totalPages
        val pageCount = pe - ps + 1

        if (ps > 1 || pe < totalPages) {
            onProgress(10, "Gemini OCR — strony $ps–$pe z $totalPages…")
        } else {
            onProgress(20, "Gemini Cloud OCR — przesyłanie PDF…")
        }

        val pdfBytes = readPdfBytes(context, pdfFile, ps, pe, totalPages)
        val b64 = Base64.encodeToString(pdfBytes, Base64.NO_WRAP)

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
        onProgress(100, "✅ Gemini OCR: $pageCount stron, ${text.length} znaków")
        text
    }

    // ─── ML Kit (local, offline fallback) ────────────────────────────────────

    suspend fun ocrMlKit(
        context: Context,
        pdfFile: File,
        pageStart: Int = 0,
        pageEnd: Int = 0,
        onProgress: suspend (Int, String) -> Unit = { _, _ -> },
    ): String = withContext(Dispatchers.IO) {
        val recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
        val fd = ParcelFileDescriptor.open(pdfFile, ParcelFileDescriptor.MODE_READ_ONLY)
        val renderer = PdfRenderer(fd)
        val totalCount = renderer.pageCount
        val ps = if (pageStart > 0) (pageStart - 1).coerceAtLeast(0) else 0
        val pe = if (pageEnd > 0) (pageEnd - 1).coerceAtMost(totalCount - 1) else totalCount - 1
        val pageCount = pe - ps + 1
        val pages = mutableListOf<String>()

        if (ps > 0 || pe < totalCount - 1) {
            onProgress(0, "ML Kit OCR: strony ${ps+1}–${pe+1} z $totalCount")
        } else {
            onProgress(0, "ML Kit OCR: 0/$totalCount")
        }

        for (i in ps..pe) {
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

            val done = i - ps + 1
            val pct = (done * 100) / pageCount
            onProgress(pct, "ML Kit OCR: $done/$pageCount")
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
