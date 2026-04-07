package com.rebook.app.domain

import android.content.Context
import android.net.Uri
import com.rebook.app.data.AppConfig
import java.io.File

/**
 * Main conversion pipeline — Kotlin port of converter.py.
 * Orchestrates: file input → OCR (if PDF) → AI correction/translation → EPUB export.
 */
object Converter {

    enum class OutputFormat(val ext: String) {
        EPUB("epub"), MARKDOWN("md"), HTML("html")
    }

    data class ConversionParams(
        val inputUri: Uri,
        val outputFormat: OutputFormat = OutputFormat.EPUB,
        val useLlm: Boolean = false,
        val translate: Boolean = false,
        val langFrom: String = "",
        val langTo: String = "polski",
        val verify: Boolean = false,
    )

    /**
     * Run the full conversion pipeline.
     *
     * @return Path to the output file
     */
    suspend fun convert(
        context: Context,
        params: ConversionParams,
        config: AppConfig,
        onProgress: suspend (String, Int, String) -> Unit,
    ): String {
        val cacheDir = File(context.cacheDir, "rebook_convert").also { it.mkdirs() }

        // ── Step 1: Copy input to local file ──
        onProgress("ocr", 0, "Przygotowywanie pliku...")
        val inputFile = copyUriToFile(context, params.inputUri, cacheDir)
        val inputExt = inputFile.extension.lowercase()
        val baseName = inputFile.nameWithoutExtension

        // ── Step 2: Extract text ──
        val rawText: String = when (inputExt) {
            "pdf" -> {
                onProgress("ocr", 5, "OCR: uruchamianie ML Kit...")
                OcrEngine.ocrPdf(context, inputFile) { pct, msg ->
                    onProgress("ocr", pct, msg)
                }
            }
            "epub" -> {
                onProgress("ocr", 10, "Odczyt EPUB...")
                val text = EpubReader.read(inputFile)
                onProgress("ocr", 100, "EPUB odczytany")
                text
            }
            "md", "txt" -> {
                inputFile.readText()
            }
            else -> throw IllegalArgumentException("Nieobsługiwany format: .$inputExt")
        }

        if (rawText.isBlank()) {
            throw RuntimeException("Nie udało się wyodrębnić tekstu z pliku.")
        }

        // ── Step 3: AI Correction / Translation ──
        val correctedText: String = if (params.useLlm || params.translate) {
            onProgress("correction", 0, if (params.translate) "Tłumaczenie AI..." else "Korekta AI...")
            Corrector.processText(
                text = rawText,
                config = config,
                translate = params.translate,
                langFrom = params.langFrom,
                langTo = params.langTo,
            ) { pct, msg ->
                onProgress("correction", pct, msg)
            }
        } else {
            rawText
        }

        // ── Step 4: Export ──
        onProgress("export", 0, "Eksport ${params.outputFormat.name}...")

        // Build output title with language suffix
        val langSuffix = if (params.translate && params.langTo.isNotBlank()) {
            "_${params.langTo.take(3).lowercase()}"
        } else ""
        val outputName = "${baseName}${langSuffix}.${params.outputFormat.ext}"
        val outputFile = File(cacheDir, outputName)

        // Determine book title
        val bookTitle = if (params.translate && params.langTo.isNotBlank()) {
            "$baseName [${params.langTo}]"
        } else baseName

        // Determine language code for EPUB metadata
        val langCode = guessLangCode(params.langTo)

        when (params.outputFormat) {
            OutputFormat.EPUB -> {
                EpubWriter.write(correctedText, bookTitle, langCode, outputFile)
            }
            OutputFormat.MARKDOWN -> {
                outputFile.writeText(correctedText)
            }
            OutputFormat.HTML -> {
                val html = """<!DOCTYPE html>
<html lang="$langCode">
<head><meta charset="utf-8"><title>${bookTitle}</title>
<style>body{font-family:Georgia,serif;max-width:800px;margin:0 auto;padding:20px;line-height:1.6;}</style>
</head><body>
${markdownToBasicHtml(correctedText)}
</body></html>"""
                outputFile.writeText(html)
            }
        }

        onProgress("done", 100, "Gotowe: $outputName")
        return outputFile.absolutePath
    }

    /**
     * Copy a content URI to a local file.
     */
    private fun copyUriToFile(context: Context, uri: Uri, dir: File): File {
        val resolver = context.contentResolver
        val displayName = resolver.query(uri, null, null, null, null)?.use { cursor ->
            val idx = cursor.getColumnIndex(android.provider.OpenableColumns.DISPLAY_NAME)
            cursor.moveToFirst()
            if (idx >= 0) cursor.getString(idx) else null
        } ?: "input.pdf"

        val outFile = File(dir, displayName)
        resolver.openInputStream(uri)?.use { input ->
            outFile.outputStream().use { output -> input.copyTo(output) }
        }
        return outFile
    }

    private fun guessLangCode(langName: String): String {
        val map = mapOf(
            "polski" to "pl", "angielski" to "en", "english" to "en",
            "niemiecki" to "de", "deutsch" to "de", "german" to "de",
            "francuski" to "fr", "français" to "fr", "french" to "fr",
            "hiszpański" to "es", "español" to "es", "spanish" to "es",
            "portugalski" to "pt", "português" to "pt",
            "włoski" to "it", "italiano" to "it",
            "rosyjski" to "ru", "русский" to "ru",
            "ukraiński" to "uk", "українська" to "uk",
            "czeski" to "cs", "čeština" to "cs",
            "chiński" to "zh", "中文" to "zh",
            "japoński" to "ja", "日本語" to "ja",
        )
        return map[langName.lowercase()] ?: langName.take(2).lowercase()
    }

    private fun markdownToBasicHtml(md: String): String {
        val sb = StringBuilder()
        for (line in md.lines()) {
            val t = line.trim()
            when {
                t.startsWith("# ") -> sb.appendLine("<h1>${t.removePrefix("# ")}</h1>")
                t.startsWith("## ") -> sb.appendLine("<h2>${t.removePrefix("## ")}</h2>")
                t.startsWith("### ") -> sb.appendLine("<h3>${t.removePrefix("### ")}</h3>")
                t.startsWith("---") -> sb.appendLine("<hr>")
                t.isBlank() -> sb.appendLine("<br>")
                else -> sb.appendLine("<p>$t</p>")
            }
        }
        return sb.toString()
    }
}
