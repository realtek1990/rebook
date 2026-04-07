package com.rebook.app.domain

import android.content.Context
import android.graphics.Bitmap
import android.graphics.pdf.PdfRenderer
import android.os.ParcelFileDescriptor
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import com.google.android.gms.tasks.Tasks
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

/**
 * PDF → text extraction using ML Kit Text Recognition.
 * Replaces Marker OCR from the desktop version.
 *
 * Flow: PDF → PdfRenderer → Bitmap per page → ML Kit → text
 */
object OcrEngine {

    private const val RENDER_DPI_SCALE = 2 // 2x for better OCR quality (144 DPI equivalent)

    /**
     * Extract text from all pages of a PDF file.
     *
     * @param pdfFile The PDF file to process
     * @param onProgress Callback with (percentComplete, statusMessage)
     * @return Full extracted text with page separators
     */
    suspend fun ocrPdf(
        context: Context,
        pdfFile: File,
        onProgress: suspend (Int, String) -> Unit = { _, _ -> },
    ): String = withContext(Dispatchers.IO) {
        val recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)

        val fd = ParcelFileDescriptor.open(pdfFile, ParcelFileDescriptor.MODE_READ_ONLY)
        val renderer = PdfRenderer(fd)
        val pageCount = renderer.pageCount
        val pages = mutableListOf<String>()

        onProgress(0, "OCR: 0/$pageCount")

        for (i in 0 until pageCount) {
            val page = renderer.openPage(i)

            // Create bitmap at 2x resolution for better OCR
            val width = page.width * RENDER_DPI_SCALE
            val height = page.height * RENDER_DPI_SCALE
            val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)

            // Render page to bitmap
            page.render(bitmap, null, null, PdfRenderer.Page.RENDER_MODE_FOR_PRINT)
            page.close()

            // Run ML Kit OCR (blocking on IO dispatcher)
            val inputImage = InputImage.fromBitmap(bitmap, 0)
            val visionText = Tasks.await(recognizer.process(inputImage))

            // Collect text blocks with proper ordering
            val pageText = visionText.textBlocks.joinToString("\n\n") { block ->
                block.lines.joinToString("\n") { line -> line.text }
            }

            pages.add(pageText)
            bitmap.recycle() // Free memory immediately

            val pct = ((i + 1) * 100) / pageCount
            onProgress(pct, "OCR: ${i + 1}/$pageCount")
        }

        renderer.close()
        fd.close()
        recognizer.close()

        pages.joinToString("\n\n---\n\n")
    }
}
