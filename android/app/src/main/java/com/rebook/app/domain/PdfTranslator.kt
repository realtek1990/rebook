package com.rebook.app.domain

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.pdf.PdfRenderer
import android.os.ParcelFileDescriptor
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import com.rebook.app.data.AppConfig
import com.tom_roush.pdfbox.android.PDFBoxResourceLoader
import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.pdmodel.PDPageContentStream
import com.tom_roush.pdfbox.pdmodel.PDPageContentStream.AppendMode
import com.tom_roush.pdfbox.pdmodel.font.PDType1Font
import com.tom_roush.pdfbox.pdmodel.font.Standard14Fonts
import com.tom_roush.pdfbox.util.Matrix
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import java.io.File
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.math.min

/**
 * Layout-preserving PDF → PDF translation for Android.
 *
 * Pipeline per page:
 *  1. [PdfRenderer] renders page → Bitmap (300 dpi)
 *  2. ML Kit text recognition → blocks with pixel bounding boxes
 *  3. Pixel coords scaled to PDF point space
 *  4. [Corrector.processBlock] translates each block (1 block = 1 LLM call)
 *  5. [PDFBox] opens original PDF, paints white rect + translated text per block
 *
 * Supports page ranges and a suspend progress callback compatible with
 * [ConversionViewModel].
 */
object PdfTranslator {

    // Render scale: 300 dpi on a standard 72 pt/inch PDF page → 300/72 ≈ 4.167
    private const val PDF_DPI = 300f
    private const val PDF_POINTS_PER_INCH = 72f
    private const val SCALE = PDF_DPI / PDF_POINTS_PER_INCH  // pixels per PDF point

    /** Text block extracted from a page with its position in PDF points. */
    data class TextBlock(
        /** Bounding box in PDF coordinate space (origin = bottom-left, y up). */
        val x: Float,
        val y: Float,
        val width: Float,
        val height: Float,
        val text: String,
        /** Estimated font size in points. */
        val fontSize: Float,
    )

    /**
     * Translate [inputFile] PDF preserving layout; write result to [outputFile].
     *
     * @param pageStart 1-indexed first page (0 = from beginning)
     * @param pageEnd   1-indexed last page  (0 = to end)
     */
    suspend fun translate(
        context: Context,
        inputFile: File,
        outputFile: File,
        config: AppConfig,
        langFrom: String = "angielski",
        langTo: String = "polski",
        pageStart: Int = 0,
        pageEnd: Int = 0,
        onProgress: suspend (stage: String, pct: Int, msg: String) -> Unit,
    ): File = withContext(Dispatchers.IO) {

        // Initialise PDFBox Android resources once
        PDFBoxResourceLoader.init(context)

        val pfd = ParcelFileDescriptor.open(inputFile, ParcelFileDescriptor.MODE_READ_ONLY)
        val renderer = PdfRenderer(pfd)
        val totalPages = renderer.pageCount

        val from = if (pageStart > 0) (pageStart - 1).coerceIn(0, totalPages - 1) else 0
        val to   = if (pageEnd   > 0) pageEnd.coerceIn(from + 1, totalPages) else totalPages
        val pagesToProcess = from until to

        onProgress("translate_pdf", 0,
            "📄 Tłumaczenie PDF: $totalPages stron (strony ${from + 1}–$to)")

        // ── Phase 1: Extract + translate blocks page by page ─────────────────
        // Map: pageIndex → list of (block, translation)
        val pageTranslations = mutableMapOf<Int, List<Pair<TextBlock, String?>>>()

        val systemPrompt = ("Przetłumacz podany tekst z języka $langFrom na $langTo. "
            + "Zachowaj oryginalne formatowanie i nazwy własne. "
            + "Odpowiedz TYLKO przetłumaczonym tekstem, bez żadnych komentarzy.")

        var donePages = 0

        for (pageIdx in pagesToProcess) {
            val page = renderer.openPage(pageIdx)
            val pageWidthPt  = page.width.toFloat()   // PDF points
            val pageHeightPt = page.height.toFloat()

            // Render to bitmap
            val bmpW = (pageWidthPt  * SCALE).toInt()
            val bmpH = (pageHeightPt * SCALE).toInt()
            val bitmap = Bitmap.createBitmap(bmpW, bmpH, Bitmap.Config.ARGB_8888)
            val canvas = Canvas(bitmap)
            canvas.drawColor(Color.WHITE)
            page.render(bitmap, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
            page.close()

            // ML Kit text recognition → blocks with pixel bboxes
            val blocks = recognizeBlocks(bitmap, pageWidthPt, pageHeightPt)
            bitmap.recycle()

            // Translate each block concurrently (bounded by Corrector workers)
            val translations: List<Pair<TextBlock, String?>> = coroutineScope {
                blocks.map { block ->
                    async(Dispatchers.IO) {
                        val tr = try {
                            Corrector.processBlock(block.text, systemPrompt, config)
                        } catch (e: Exception) { null }
                        block to tr
                    }
                }.awaitAll()
            }

            pageTranslations[pageIdx] = translations
            donePages++
            val pct = (donePages.toFloat() / pagesToProcess.count() * 80).toInt()
            onProgress("translate_pdf", pct,
                "Tłumaczenie… $donePages/${pagesToProcess.count()} stron")
        }

        renderer.close()
        pfd.close()

        // ── Phase 2: Render output PDF with PDFBox ────────────────────────────
        onProgress("translate_pdf", 82, "📝 Składanie PDF…")

        val document = PDDocument.load(inputFile)
        val font = PDType1Font(Standard14Fonts.FontName.HELVETICA)

        for ((pageIdx, pairs) in pageTranslations) {
            val pdPage = document.getPage(pageIdx)
            val pageH  = pdPage.mediaBox.height  // for y-axis flip

            val contentStream = PDPageContentStream(document, pdPage, AppendMode.APPEND, true, true)
            contentStream.use { cs ->
                for ((block, translation) in pairs) {
                    if (translation.isNullOrBlank()) continue

                    // PDF coordinate origin = bottom-left, y increases upward
                    val pdfY = pageH - block.y - block.height   // flip y

                    // White rectangle to cover original text
                    cs.setNonStrokingColor(1f, 1f, 1f)
                    cs.addRect(block.x, pdfY, block.width, block.height)
                    cs.fill()

                    // Insert translated text — shrink until it fits the box
                    cs.setNonStrokingColor(0f, 0f, 0f)
                    cs.beginText()
                    var fontSize = block.fontSize
                    var fitted = false
                    while (fontSize >= 5f && !fitted) {
                        val line = truncateToWidth(translation, font, fontSize, block.width)
                        cs.setFont(font, fontSize)
                        cs.newLineAtOffset(block.x + 1f, pdfY + 2f)
                        cs.showText(line)
                        fitted = true
                        fontSize -= 1f
                    }
                    cs.endText()
                }
            }
        }

        onProgress("translate_pdf", 95, "💾 Zapisywanie PDF…")
        document.save(outputFile)
        document.close()

        onProgress("translate_pdf", 100, "✅ Gotowe! → ${outputFile.name}")
        outputFile
    }

    // ── ML Kit text recognition ───────────────────────────────────────────────

    private suspend fun recognizeBlocks(
        bitmap: Bitmap,
        pageWidthPt: Float,
        pageHeightPt: Float,
    ): List<TextBlock> = suspendCancellableCoroutine { cont ->
        val image = InputImage.fromBitmap(bitmap, 0)
        val recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
        recognizer.process(image)
            .addOnSuccessListener { visionText ->
                val bmpW = bitmap.width.toFloat()
                val bmpH = bitmap.height.toFloat()
                val result = visionText.textBlocks.mapNotNull { block ->
                    val rect = block.boundingBox ?: return@mapNotNull null
                    val text = block.lines.joinToString(" ") { it.text }.trim()
                    if (text.length < 3) return@mapNotNull null

                    // Scale pixel → PDF points (y origin stays top for now, flipped later)
                    val x = rect.left   / bmpW * pageWidthPt
                    val y = rect.top    / bmpH * pageHeightPt
                    val w = rect.width().toFloat()  / bmpW * pageWidthPt
                    val h = rect.height().toFloat() / bmpH * pageHeightPt

                    // Estimate font size from block height and number of lines
                    val lineCount = block.lines.size.coerceAtLeast(1)
                    val fontSize  = (h / lineCount * 0.85f).coerceIn(6f, 72f)

                    TextBlock(x, y, w, h, text, fontSize)
                }
                cont.resume(result)
            }
            .addOnFailureListener { cont.resumeWithException(it) }
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    /**
     * Truncate [text] so its rendered width ≤ [maxWidth] PDF points at [fontSize].
     * Uses simple character-count approximation (PDFBox glyph width lookup is expensive).
     */
    private fun truncateToWidth(text: String, font: PDType1Font, fontSize: Float, maxWidth: Float): String {
        val avgGlyphWidth = fontSize * 0.5f  // rough average for Helvetica
        val maxChars = (maxWidth / avgGlyphWidth).toInt().coerceAtLeast(1)
        return if (text.length <= maxChars) text else text.take(maxChars - 1) + "…"
    }
}
