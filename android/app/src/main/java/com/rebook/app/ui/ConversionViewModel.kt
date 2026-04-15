package com.rebook.app.ui

import android.app.Application
import android.media.MediaPlayer
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.rebook.app.ConversionService
import com.rebook.app.data.AppConfig
import com.rebook.app.data.AppConfigStore
import com.rebook.app.domain.Converter
import com.rebook.app.domain.OcrEngine
import com.rebook.app.domain.TtsEngine
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import java.io.File

data class ConversionState(
    val selectedFileUri: Uri? = null,
    val selectedFileName: String = "",
    val selectedFileSize: String = "",
    val outputFormat: Converter.OutputFormat = Converter.OutputFormat.EPUB,
    val useAi: Boolean = true,
    val translate: Boolean = false,
    val translatePdf: Boolean = false,   // layout-preserving PDF→PDF translation
    val translateImages: Boolean = false,
    val langFrom: String = "",
    val langTo: String = "polski",
    val verify: Boolean = false,
    val isConverting: Boolean = false,
    val isCancelled: Boolean = false,
    val progressStage: String = "",
    val progressPercent: Float = 0f,
    val progressMessage: String = "",
    val logMessages: List<String> = emptyList(),
    val outputPath: String? = null,
    val error: String? = null,
    val config: AppConfig = AppConfig(),
    // ── Page range (PDF only) ─────────────────────────────────────────
    val pageStart: String = "",
    val pageEnd: String = "",
    val totalPageCount: Int = 0,
    val isPdf: Boolean = false,
    // ── Audiobook TTS ────────────────────────────────────────────────
    val ttsVoice: String = "pl-PL-MarekNeural",
    val isGeneratingAudiobook: Boolean = false,
    val audiobookProgress: String = "",
    val audiobookOutputDir: String? = null,
    val audiobookError: String? = null,
    val isSamplePlaying: Boolean = false,
    // Directly-picked EPUB for audiobook (independent of conversion output)
    val audiobookEpubUri: Uri? = null,
    val audiobookEpubName: String = "",
    val audiobookProgressPercent: Float = -1f,  // -1 = indeterminate, 0..1 = progress
    // ── Chapter selection ─────────────────────────────────────────────
    val audiobookChapters: List<ChapterInfo> = emptyList(),
    val selectedChapterIndices: Set<Int> = emptySet(),
    val showChapterSelector: Boolean = false,
    // ── Pipeline ─────────────────────────────────────────────────────
    val pipelineAutoAudiobook: Boolean = false,   // auto-generate audiobook after conversion
    val pipelineAudiobookVoice: String = "pl-PL-MarekNeural",
)

data class ChapterInfo(val index: Int, val title: String, val wordCount: Int)

class ConversionViewModel(application: Application) : AndroidViewModel(application) {

    private val configStore = AppConfigStore(application)
    private val _state = MutableStateFlow(ConversionState())
    val state: StateFlow<ConversionState> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            configStore.observe().collect { config ->
                _state.update { it.copy(config = config) }
            }
        }
    }

    fun setFile(uri: Uri, name: String, size: Long) {
        val isPdf = name.endsWith(".pdf", ignoreCase = true)
        _state.update {
            it.copy(
                selectedFileUri = uri,
                selectedFileName = name,
                selectedFileSize = formatSize(size),
                outputPath = null,
                error = null,
                isPdf = isPdf,
                pageStart = "",
                pageEnd = "",
                totalPageCount = 0,
            )
        }
        // Detect page count for PDFs
        if (isPdf) {
            viewModelScope.launch(kotlinx.coroutines.Dispatchers.IO) {
                try {
                    val app = getApplication<android.app.Application>()
                    val cacheDir = File(app.cacheDir, "rebook_convert").also { it.mkdirs() }
                    val tmpFile = File(cacheDir, name)
                    app.contentResolver.openInputStream(uri)?.use { inp ->
                        tmpFile.outputStream().use { inp.copyTo(it) }
                    }
                    val count = OcrEngine.getPdfPageCount(app, tmpFile)
                    _state.update { it.copy(totalPageCount = count) }
                } catch (_: Exception) { /* ignore */ }
            }
        }
    }

    fun removeFile() {
        _state.update {
            it.copy(selectedFileUri = null, selectedFileName = "", selectedFileSize = "", outputPath = null, error = null)
        }
    }

    fun setOutputFormat(format: Converter.OutputFormat) { _state.update { it.copy(outputFormat = format) } }
    fun setUseAi(v: Boolean) { _state.update { it.copy(useAi = v) } }
    fun setTranslate(v: Boolean) { _state.update { it.copy(translate = v) } }
    fun setTranslatePdf(v: Boolean) { _state.update { it.copy(translatePdf = v) } }
    fun setTranslateImages(v: Boolean) { _state.update { it.copy(translateImages = v) } }
    fun setLangFrom(v: String) { _state.update { it.copy(langFrom = v) } }
    fun setLangTo(v: String) { _state.update { it.copy(langTo = v) } }
    fun setVerify(v: Boolean) { _state.update { it.copy(verify = v) } }
    fun setPageStart(v: String) { _state.update { it.copy(pageStart = v) } }
    fun setPageEnd(v: String) { _state.update { it.copy(pageEnd = v) } }
    // Pipeline
    fun setPipelineAutoAudiobook(v: Boolean) { _state.update { it.copy(pipelineAutoAudiobook = v) } }
    fun setPipelineAudiobookVoice(v: String) { _state.update { it.copy(pipelineAudiobookVoice = v, ttsVoice = v) } }

    fun saveConfig(config: AppConfig) {
        viewModelScope.launch { configStore.save(config) }
    }

    fun startConversion() {
        val uri = _state.value.selectedFileUri ?: return
        if (_state.value.isConverting) return

        _state.update {
            it.copy(
                isConverting = true,
                isCancelled = false,
                progressPercent = 0f,
                progressMessage = "",
                logMessages = emptyList(),
                outputPath = null,
                error = null,
            )
        }

        // Start foreground service so Android won't kill us when backgrounded
        val fileName = _state.value.selectedFileName.ifBlank { "dokument" }
        ConversionService.start(getApplication(), "ReBook — $fileName")

        viewModelScope.launch {
            try {
                val params = Converter.ConversionParams(
                    inputUri = uri,
                    outputFormat = _state.value.outputFormat,
                    useLlm = _state.value.useAi || _state.value.translate,
                    translate = _state.value.translate,
                    translatePdf = _state.value.translatePdf,
                    langFrom = _state.value.langFrom,
                    langTo = _state.value.langTo,
                    verify = _state.value.verify,
                    pageStart = _state.value.pageStart.toIntOrNull() ?: 0,
                    pageEnd = _state.value.pageEnd.toIntOrNull() ?: 0,
                )

                val result = Converter.convert(
                    context = getApplication(),
                    params = params,
                    config = _state.value.config,
                ) { stage, pct, msg ->
                    if (_state.value.isCancelled) {
                        throw InterruptedException("Konwersja zatrzymana")
                    }
                    val totalPct = mapStageProgress(stage, pct)
                    _state.update {
                        it.copy(
                            progressStage = stage,
                            progressPercent = totalPct,
                            progressMessage = msg,
                            logMessages = it.logMessages + msg,
                        )
                    }
                    // Keep notification in sync with progress
                    ConversionService.updateProgress(getApplication(), (totalPct * 100).toInt(), msg)
                }

                _state.update {
                    it.copy(
                        isConverting = false,
                        outputPath = result,
                        progressPercent = 1f,
                        progressMessage = "✅ Gotowe!",
                    )
                }
                // ── Pipeline auto-audiobook ───────────────────────────────────
                if (_state.value.pipelineAutoAudiobook && result.endsWith(".epub")) {
                    // Set pipeline voice and trigger audiobook generation
                    _state.update { it.copy(ttsVoice = it.pipelineAudiobookVoice) }
                    startAudiobook()
                }
            } catch (e: InterruptedException) {
                _state.update {
                    it.copy(isConverting = false, progressMessage = "⛔ Zatrzymano")
                }
            } catch (e: Exception) {
                _state.update {
                    it.copy(
                        isConverting = false,
                        error = e.message ?: "Unknown error",
                        progressMessage = "❌ Błąd: ${e.message}",
                    )
                }
            } finally {
                // Always stop foreground service when conversion ends
                ConversionService.stop(getApplication())
            }
        }
    }

    fun stopConversion() {
        _state.update { it.copy(isCancelled = true) }
    }

    // ── Audiobook TTS ────────────────────────────────────────────────

    private val ttsEngine = TtsEngine()

    fun setTtsVoice(voice: String) {
        _state.update { it.copy(ttsVoice = voice) }
    }

    private var audiobookJob: kotlinx.coroutines.Job? = null

    fun cancelAudiobook() {
        audiobookJob?.cancel()
        audiobookJob = null
        _state.update {
            it.copy(
                isGeneratingAudiobook = false,
                audiobookProgress = "⏹ Anulowano",
                audiobookProgressPercent = -1f,
            )
        }
        ConversionService.stop(getApplication())
    }

    fun setAudiobookEpub(uri: Uri, name: String) {
        _state.update {
            it.copy(
                audiobookEpubUri = uri,
                audiobookEpubName = name,
                audiobookProgress = "",
                audiobookError = null,
                audiobookOutputDir = null,
            )
        }
    }

    fun playSample() {
        if (_state.value.isSamplePlaying) return
        _state.update { it.copy(isSamplePlaying = true) }
        viewModelScope.launch {
            val result = ttsEngine.generateSample(_state.value.ttsVoice)
            result.onSuccess { tmpFile ->
                try {
                    val player = MediaPlayer()
                    player.setDataSource(tmpFile.absolutePath)
                    player.prepare()
                    player.setOnCompletionListener {
                        it.release()
                        tmpFile.delete()
                        _state.update { s -> s.copy(isSamplePlaying = false) }
                    }
                    player.start()
                } catch (e: Exception) {
                    tmpFile.delete()
                    _state.update { it.copy(isSamplePlaying = false) }
                }
            }.onFailure {
                _state.update { s -> s.copy(isSamplePlaying = false, audiobookError = it.message) }
            }
        }
    }

    fun loadChapters() {
        val epubFile = resolveAudiobookEpub() ?: return
        viewModelScope.launch {
            try {
                val chapters = extractEpubChapters(epubFile)
                _state.update { it.copy(
                    audiobookChapters = chapters,
                    selectedChapterIndices = chapters.map { c -> c.index }.toSet(),
                    showChapterSelector = true,
                ) }
            } catch (e: Exception) {
                _state.update { it.copy(audiobookError = e.message) }
            }
        }
    }

    fun setSelectedChapters(indices: Set<Int>) {
        _state.update { it.copy(selectedChapterIndices = indices) }
    }

    fun dismissChapterSelector() {
        _state.update { it.copy(showChapterSelector = false) }
    }

    fun confirmChapterSelection() {
        _state.update { it.copy(showChapterSelector = false) }
        startAudiobookWithSelection()
    }

    private fun resolveAudiobookEpub(): File? {
        val app = getApplication<android.app.Application>()
        val explicitUri = _state.value.audiobookEpubUri
        val epubPath: String? = if (explicitUri == null)
            _state.value.outputPath?.takeIf { it.endsWith(".epub") } else null
        val epubUri: Uri? = explicitUri
            ?: if (epubPath == null &&
                _state.value.selectedFileName.endsWith(".epub", ignoreCase = true))
                _state.value.selectedFileUri else null

        if (epubPath == null && epubUri == null) return null

        return if (epubPath != null) {
            File(epubPath)
        } else {
            val tmp = File(app.cacheDir,
                _state.value.selectedFileName.ifBlank { "input.epub" })
            app.contentResolver
                .openInputStream(epubUri!!)?.use { ins ->
                    tmp.outputStream().use { ins.copyTo(it) }
                }
            tmp
        }
    }

    fun startAudiobook() {
        if (_state.value.isGeneratingAudiobook) return
        // Show chapter selector first
        loadChapters()
    }

    private fun startAudiobookWithSelection() {
        if (_state.value.isGeneratingAudiobook) return

        val epubFile = resolveAudiobookEpub() ?: return
        val selectedIndices = _state.value.selectedChapterIndices
        if (selectedIndices.isEmpty()) return

        val totalChapters = _state.value.audiobookChapters.size

        _state.update {
            it.copy(
                isGeneratingAudiobook = true,
                audiobookProgress = "📖 Czytam EPUB… (${selectedIndices.size}/$totalChapters rozdziałów)",
                audiobookProgressPercent = -1f,
                audiobookOutputDir = null,
                audiobookError = null,
            )
        }

        val app = getApplication<android.app.Application>()
        ConversionService.start(app, "🎧 Audiobook — generuję…")

        audiobookJob = viewModelScope.launch {
            try {
                val cacheDir = File(app.cacheDir, "${epubFile.nameWithoutExtension}_audiobook")
                if (cacheDir.exists()) cacheDir.deleteRecursively()
                cacheDir.mkdirs()

                _state.update { it.copy(
                    audiobookProgress = "📝 Wyciągam tekst z EPUB…",
                    audiobookProgressPercent = 0.02f,
                ) }
                val text = extractEpubChapterTexts(epubFile, selectedIndices)

                val files = ttsEngine.generateAudiobook(
                    text = text,
                    voice = _state.value.ttsVoice,
                    outputDir = cacheDir,
                    rate = "0%",
                ) { done, total, msg ->
                    val pct = if (total > 0) 0.05f + (done.toFloat() / total) * 0.75f else -1f
                    _state.update { it.copy(
                        audiobookProgress = "🎙 $msg",
                        audiobookProgressPercent = pct,
                    ) }
                    ConversionService.updateProgress(app, (pct * 100).toInt(), msg)
                }

                _state.update { it.copy(
                    audiobookProgress = "📂 Zapisuję do Music/ReBook/…",
                    audiobookProgressPercent = 0.82f,
                ) }
                val musicDir = File(
                    android.os.Environment.getExternalStoragePublicDirectory(
                        android.os.Environment.DIRECTORY_MUSIC
                    ),
                    "ReBook/${epubFile.nameWithoutExtension}"
                )
                musicDir.mkdirs()

                val publicFiles = mutableListOf<File>()
                for ((i, audioFile) in files.withIndex()) {
                    val dest = File(musicDir, audioFile.name)
                    audioFile.copyTo(dest, overwrite = true)
                    publicFiles.add(dest)
                    val mime = if (dest.extension == "m4a") "audio/mp4" else "audio/mpeg"
                    android.media.MediaScannerConnection.scanFile(
                        app, arrayOf(dest.absolutePath), arrayOf(mime), null
                    )
                    val copyPct = 0.82f + (i.toFloat() / files.size) * 0.13f
                    _state.update { it.copy(
                        audiobookProgress = "📂 ${i+1}/${files.size}: ${audioFile.name}",
                        audiobookProgressPercent = copyPct,
                    ) }
                }

                File(musicDir, "playlist.m3u").writeText(buildString {
                    appendLine("#EXTM3U")
                    publicFiles.forEach {
                        appendLine("#EXTINF:-1,${it.nameWithoutExtension}")
                        appendLine(it.absolutePath)
                    }
                })

                cacheDir.deleteRecursively()

                _state.update {
                    it.copy(
                        isGeneratingAudiobook = false,
                        audiobookOutputDir = musicDir.absolutePath,
                        audiobookProgress = "✅ Gotowe! ${publicFiles.size} plików → Music/ReBook/${epubFile.nameWithoutExtension}/",
                        audiobookProgressPercent = 1f,
                    )
                }
            } catch (_: kotlinx.coroutines.CancellationException) {
                // Cancelled by user
            } catch (e: Exception) {
                _state.update {
                    it.copy(
                        isGeneratingAudiobook = false,
                        audiobookError = e.message ?: "Błąd generowania",
                        audiobookProgressPercent = -1f,
                    )
                }
            } finally {
                ConversionService.stop(app)
            }
        }
    }

    /** Simple plain-text extraction from EPUB zip */
    private fun extractEpubText(epubFile: File): String {
        val sb = StringBuilder()
        java.util.zip.ZipFile(epubFile).use { zip ->
            zip.entries().asSequence()
                .filter { !it.isDirectory && (it.name.endsWith(".xhtml") || it.name.endsWith(".html")) }
                .filter { !it.name.contains("nav", ignoreCase = true) }
                .sortedBy { it.name }
                .forEach { entry ->
                    val html = zip.getInputStream(entry).bufferedReader().readText()
                    val text = stripHtml(html)
                    if (text.length > 50) sb.append(text).append("\n\n")
                }
        }
        return sb.toString()
    }

    /** Extract chapter list with metadata for chapter selector UI */
    private fun extractEpubChapters(epubFile: File): List<ChapterInfo> {
        val chapters = mutableListOf<ChapterInfo>()
        java.util.zip.ZipFile(epubFile).use { zip ->
            val htmlFiles = zip.entries().asSequence()
                .filter { !it.isDirectory && (it.name.endsWith(".xhtml") || it.name.endsWith(".html")) }
                .filter { !it.name.contains("nav", ignoreCase = true) }
                .sortedBy { it.name }
                .toList()

            for ((idx, entry) in htmlFiles.withIndex()) {
                val html = zip.getInputStream(entry).bufferedReader().readText()
                // Extract title from h1/h2
                val titleMatch = Regex("<h[12][^>]*>(.*?)</h[12]>", RegexOption.IGNORE_CASE)
                    .find(html)
                val title = titleMatch?.groupValues?.get(1)
                    ?.replace(Regex("<[^>]+>"), "")
                    ?.trim()
                    ?.take(60)
                    ?: "Część ${idx + 1}"
                val text = stripHtml(html)
                if (text.length > 50) {
                    chapters.add(ChapterInfo(idx, title, text.split("\\s+".toRegex()).size))
                }
            }
        }
        return chapters
    }

    /** Extract text only from selected chapter indices */
    private fun extractEpubChapterTexts(epubFile: File, selectedIndices: Set<Int>): String {
        val sb = StringBuilder()
        java.util.zip.ZipFile(epubFile).use { zip ->
            val htmlFiles = zip.entries().asSequence()
                .filter { !it.isDirectory && (it.name.endsWith(".xhtml") || it.name.endsWith(".html")) }
                .filter { !it.name.contains("nav", ignoreCase = true) }
                .sortedBy { it.name }
                .toList()

            for ((idx, entry) in htmlFiles.withIndex()) {
                if (idx !in selectedIndices) continue
                val html = zip.getInputStream(entry).bufferedReader().readText()
                val text = stripHtml(html)
                if (text.length > 50) sb.append(text).append("\n\n")
            }
        }
        return sb.toString()
    }

    private fun stripHtml(html: String): String {
        return html
            .replace(Regex("<script[^>]*>.*?</script>", RegexOption.DOT_MATCHES_ALL), "")
            .replace(Regex("<style[^>]*>.*?</style>", RegexOption.DOT_MATCHES_ALL), "")
            .replace(Regex("<[^>]+>"), " ")
            .replace(Regex("\\s{2,}"), " ")
            .trim()
    }

    private fun mapStageProgress(stage: String, pct: Int): Float {
        val (lo, hi) = when (stage) {
            "ocr"          -> 0f    to 0.30f
            "correction"   -> 0.30f to 0.60f
            "verification" -> 0.60f to 0.85f
            "export"       -> 0.85f to 1f
            "translate_pdf"-> 0f    to 1f    // full range for PDF→PDF
            "done"         -> 1f    to 1f
            else           -> 0f    to 1f
        }
        return lo + (pct / 100f) * (hi - lo)
    }

    private fun formatSize(bytes: Long): String {
        val mb = bytes / (1024.0 * 1024.0)
        return if (mb >= 1) "%.1f MB".format(mb) else "%.0f KB".format(bytes / 1024.0)
    }
}
