package com.rebook.app.domain

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.pdf.PdfRenderer
import android.os.ParcelFileDescriptor
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import com.rebook.app.data.AppConfig
import com.tom_roush.pdfbox.android.PDFBoxResourceLoader
import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.pdmodel.PDPage
import com.tom_roush.pdfbox.pdmodel.PDPageContentStream
import com.tom_roush.pdfbox.pdmodel.PDPageContentStream.AppendMode
import com.tom_roush.pdfbox.pdmodel.font.PDType1Font
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.withContext
import java.io.File
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/**
 * Layout-preserving PDF → PDF translation for Android.
 *
 * Pipeline:
 *  1. [PdfRenderer] renders pages → Bitmaps (300 dpi)
 *  2. ML Kit text recognition → blocks with pixel bounding boxes
 *  3. All blocks from ALL pages are translated in parallel (max 15 workers)
 *  4. [PDFBox] creates output PDF containing ONLY translated pages
 *
 * Key fixes (v3.15.1):
 *  - Parallel translation across ALL pages simultaneously (was sequential)
 *  - Output PDF contains only the selected page range (was whole book)
 *  - Safe ASCII transliteration for Helvetica font (was dropping Polish chars)
 */
object PdfTranslator {

    private const val PDF_DPI = 300f
    private const val PDF_POINTS_PER_INCH = 72f
    private const val SCALE = PDF_DPI / PDF_POINTS_PER_INCH
    private const val MAX_PARALLEL = 15

    /** Text block extracted from a page with its position in PDF points. */
    data class TextBlock(
        val x: Float,
        val y: Float,
        val width: Float,
        val height: Float,
        val text: String,
        val fontSize: Float,
    )

    /** A block with its translation result, tagged with page index. */
    private data class TranslatedBlock(
        val pageIdx: Int,
        val block: TextBlock,
        val translation: String?,
    )

    /**
     * Translate [inputFile] PDF preserving layout; write result to [outputFile].
     * Output contains ONLY pages from [pageStart]..[pageEnd].
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

        PDFBoxResourceLoader.init(context)

        val pfd = ParcelFileDescriptor.open(inputFile, ParcelFileDescriptor.MODE_READ_ONLY)
        val renderer = PdfRenderer(pfd)
        val totalPages = renderer.pageCount

        val from = if (pageStart > 0) (pageStart - 1).coerceIn(0, totalPages - 1) else 0
        val to   = if (pageEnd   > 0) pageEnd.coerceIn(from + 1, totalPages) else totalPages
        val pagesToProcess = from until to
        val pageCount = pagesToProcess.count()

        onProgress("translate_pdf", 0,
            "📄 Tłumaczenie PDF: $pageCount stron (${from + 1}–$to z $totalPages)")

        // ══════════════════════════════════════════════════════════════════
        // Phase 1: OCR all pages — extract text blocks
        // ══════════════════════════════════════════════════════════════════
        data class PageData(
            val pageIdx: Int,
            val widthPt: Float,
            val heightPt: Float,
            val blocks: List<TextBlock>,
        )

        val allPages = mutableListOf<PageData>()
        var ocrDone = 0

        for (pageIdx in pagesToProcess) {
            val page = renderer.openPage(pageIdx)
            val pageWidthPt  = page.width.toFloat()
            val pageHeightPt = page.height.toFloat()

            val bmpW = (pageWidthPt  * SCALE).toInt()
            val bmpH = (pageHeightPt * SCALE).toInt()
            val bitmap = Bitmap.createBitmap(bmpW, bmpH, Bitmap.Config.ARGB_8888)
            val canvas = Canvas(bitmap)
            canvas.drawColor(Color.WHITE)
            page.render(bitmap, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
            page.close()

            val blocks = recognizeBlocks(bitmap, pageWidthPt, pageHeightPt)
            bitmap.recycle()

            allPages.add(PageData(pageIdx, pageWidthPt, pageHeightPt, blocks))
            ocrDone++
            val ocrPct = (ocrDone.toFloat() / pageCount * 20).toInt()
            onProgress("translate_pdf", ocrPct, "OCR: $ocrDone/$pageCount stron")
        }

        renderer.close()
        pfd.close()

        // ══════════════════════════════════════════════════════════════════
        // Phase 2: Translate ALL blocks from ALL pages in parallel
        // ══════════════════════════════════════════════════════════════════
        val systemPrompt = ("Przetłumacz podany tekst z języka $langFrom na $langTo. "
            + "Zachowaj oryginalne formatowanie i nazwy własne. "
            + "Odpowiedz TYLKO przetłumaczonym tekstem, bez żadnych komentarzy.")

        // Flatten all blocks into a single list for parallel processing
        data class BlockTask(val pageIdx: Int, val blockIdx: Int, val block: TextBlock)

        val allTasks = allPages.flatMap { pageData ->
            pageData.blocks.mapIndexed { blockIdx, block ->
                BlockTask(pageData.pageIdx, blockIdx, block)
            }
        }

        val totalBlocks = allTasks.size
        onProgress("translate_pdf", 20,
            "🌐 Tłumaczenie $totalBlocks bloków tekstu ($MAX_PARALLEL workerów)…")

        val semaphore = Semaphore(MAX_PARALLEL)
        var completedBlocks = 0

        val translatedBlocks: List<TranslatedBlock> = coroutineScope {
            allTasks.map { task ->
                async(Dispatchers.IO) {
                    semaphore.acquire()
                    try {
                        val tr = try {
                            Corrector.processBlock(task.block.text, systemPrompt, config)
                        } catch (e: Exception) { null }

                        completedBlocks++
                        val pct = 20 + (completedBlocks.toFloat() / totalBlocks * 60).toInt()
                        onProgress("translate_pdf", pct,
                            "Tłumaczenie: $completedBlocks/$totalBlocks bloków")

                        TranslatedBlock(task.pageIdx, task.block, tr)
                    } finally {
                        semaphore.release()
                    }
                }
            }.awaitAll()
        }

        // Group by page
        val translationsByPage = translatedBlocks.groupBy { it.pageIdx }

        // ══════════════════════════════════════════════════════════════════
        // Phase 3: Build output PDF with ONLY the selected pages
        // ══════════════════════════════════════════════════════════════════
        onProgress("translate_pdf", 82, "📝 Składanie PDF…")

        val sourceDoc = PDDocument.load(inputFile)
        val outputDoc = PDDocument()
        val font = PDType1Font.HELVETICA

        for (pageData in allPages) {
            // Import the page from source into new document
            val srcPage = sourceDoc.getPage(pageData.pageIdx)
            val importedPage = outputDoc.importPage(srcPage)
            val pageH = importedPage.mediaBox.height

            val pairs = translationsByPage[pageData.pageIdx].orEmpty()

            val contentStream = PDPageContentStream(outputDoc, importedPage, AppendMode.APPEND, true, true)
            contentStream.use { cs ->
                for (tb in pairs) {
                    val translation = tb.translation
                    if (translation.isNullOrBlank()) continue

                    val block = tb.block
                    val pdfY = pageH - block.y - block.height

                    // White rectangle to cover original text
                    cs.setNonStrokingColor(1f, 1f, 1f)
                    cs.addRect(block.x, pdfY, block.width, block.height)
                    cs.fill()

                    // Insert translated text (ASCII-safe for Helvetica)
                    val safeText = transliterateToAscii(translation)
                    cs.setNonStrokingColor(0f, 0f, 0f)
                    cs.beginText()

                    // Multi-line fitting: split into lines that fit the box width
                    val lines = wrapText(safeText, font, block.fontSize, block.width)
                    val lineHeight = block.fontSize * 1.2f
                    val maxLines = (block.height / lineHeight).toInt().coerceAtLeast(1)

                    var fontSize = block.fontSize
                    var fittedLines = lines.take(maxLines)

                    // If text doesn't fit, try smaller font
                    if (lines.size > maxLines) {
                        fontSize = (block.height / lines.size / 1.2f).coerceIn(5f, block.fontSize)
                        val newLines = wrapText(safeText, font, fontSize, block.width)
                        val newMaxLines = (block.height / (fontSize * 1.2f)).toInt().coerceAtLeast(1)
                        fittedLines = newLines.take(newMaxLines)
                    }

                    cs.setFont(font, fontSize)
                    val fLineHeight = fontSize * 1.2f

                    for ((lineIdx, line) in fittedLines.withIndex()) {
                        val y = pdfY + block.height - fLineHeight * (lineIdx + 1) + 2f
                        cs.newLineAtOffset(block.x + 1f, y)
                        cs.showText(line)
                        cs.newLineAtOffset(-(block.x + 1f), -y) // reset offset
                    }
                    cs.endText()
                }
            }
        }

        onProgress("translate_pdf", 95, "💾 Zapisywanie PDF…")
        outputDoc.save(outputFile)
        outputDoc.close()
        sourceDoc.close()

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

                    val x = rect.left   / bmpW * pageWidthPt
                    val y = rect.top    / bmpH * pageHeightPt
                    val w = rect.width().toFloat()  / bmpW * pageWidthPt
                    val h = rect.height().toFloat() / bmpH * pageHeightPt

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
     * Transliterate Polish/accent characters to ASCII for Helvetica.
     * Helvetica (Type1) only supports WinAnsiEncoding — Polish chars cause
     * IllegalArgumentException. This is a safe fallback.
     */
    private fun transliterateToAscii(text: String): String {
        val map = mapOf(
            'ą' to 'a', 'ć' to 'c', 'ę' to 'e', 'ł' to 'l', 'ń' to 'n',
            'ó' to 'o', 'ś' to 's', 'ź' to 'z', 'ż' to 'z',
            'Ą' to 'A', 'Ć' to 'C', 'Ę' to 'E', 'Ł' to 'L', 'Ń' to 'N',
            'Ó' to 'O', 'Ś' to 'S', 'Ź' to 'Z', 'Ż' to 'Z',
            'ä' to 'a', 'ö' to 'o', 'ü' to 'u', 'ß' to 's',
            'Ä' to 'A', 'Ö' to 'O', 'Ü' to 'U',
            'é' to 'e', 'è' to 'e', 'ê' to 'e', 'ë' to 'e',
            'à' to 'a', 'â' to 'a', 'î' to 'i', 'ô' to 'o', 'û' to 'u',
            'ç' to 'c', 'ñ' to 'n', 'ù' to 'u',
            '—' to '-', '–' to '-', '"' to '"', '"' to '"',
            ''' to '\'', ''' to '\'', '…' to '.',
        )
        return text.map { map[it] ?: it }.joinToString("")
    }

    /**
     * Wrap [text] into multiple lines to fit [maxWidth] PDF points at [fontSize].
     */
    private fun wrapText(text: String, font: PDType1Font, fontSize: Float, maxWidth: Float): List<String> {
        val avgGlyphWidth = fontSize * 0.5f
        val maxChars = (maxWidth / avgGlyphWidth).toInt().coerceAtLeast(5)

        if (text.length <= maxChars) return listOf(text)

        val lines = mutableListOf<String>()
        val words = text.split(" ")
        val current = StringBuilder()

        for (word in words) {
            if (current.length + word.length + 1 > maxChars && current.isNotEmpty()) {
                lines.add(current.toString().trim())
                current.clear()
            }
            if (current.isNotEmpty()) current.append(" ")
            current.append(word)
        }
        if (current.isNotEmpty()) lines.add(current.toString().trim())

        return lines
    }
}
