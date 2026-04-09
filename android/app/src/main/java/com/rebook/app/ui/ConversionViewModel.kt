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
    // ── Pipeline ─────────────────────────────────────────────────────
    val pipelineAutoAudiobook: Boolean = false,   // auto-generate audiobook after conversion
    val pipelineAudiobookVoice: String = "pl-PL-MarekNeural",
)

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
        _state.update {
            it.copy(
                selectedFileUri = uri,
                selectedFileName = name,
                selectedFileSize = formatSize(size),
                outputPath = null,
                error = null,
            )
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
    fun setTranslateImages(v: Boolean) { _state.update { it.copy(translateImages = v) } }
    fun setLangFrom(v: String) { _state.update { it.copy(langFrom = v) } }
    fun setLangTo(v: String) { _state.update { it.copy(langTo = v) } }
    fun setVerify(v: Boolean) { _state.update { it.copy(verify = v) } }
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
                    langFrom = _state.value.langFrom,
                    langTo = _state.value.langTo,
                    verify = _state.value.verify,
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

    fun startAudiobook() {
        if (_state.value.isGeneratingAudiobook) return

        // Priority: 1) explicitly picked EPUB, 2) conversion output, 3) loaded input EPUB
        val explicitUri = _state.value.audiobookEpubUri
        val epubPath: String? = if (explicitUri == null)
            _state.value.outputPath?.takeIf { it.endsWith(".epub") } else null
        val epubUri: Uri? = explicitUri
            ?: if (epubPath == null &&
                _state.value.selectedFileName.endsWith(".epub", ignoreCase = true))
                _state.value.selectedFileUri else null

        if (epubPath == null && epubUri == null) return

        _state.update {
            it.copy(
                isGeneratingAudiobook = true,
                audiobookProgress = "📖 Czytam EPUB…",
                audiobookProgressPercent = -1f,
                audiobookOutputDir = null,
                audiobookError = null,
            )
        }

        val app = getApplication<android.app.Application>()
        ConversionService.start(app, "🎧 Audiobook — generuję…")

        audiobookJob = viewModelScope.launch {
            try {
                val epubFile: File = if (epubPath != null) {
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

                val cacheDir = File(app.cacheDir, "${epubFile.nameWithoutExtension}_audiobook")
                cacheDir.mkdirs()

                _state.update { it.copy(
                    audiobookProgress = "📝 Wyciągam tekst z EPUB…",
                    audiobookProgressPercent = 0.02f,
                ) }
                val text = extractEpubText(epubFile)

                val files = ttsEngine.generateAudiobook(
                    text = text,
                    voice = _state.value.ttsVoice,
                    outputDir = cacheDir,
                    rate = "+50%",
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
                    // Basic HTML strip
                    val text = html
                        .replace(Regex("<script[^>]*>.*?</script>", RegexOption.DOT_MATCHES_ALL), "")
                        .replace(Regex("<style[^>]*>.*?</style>", RegexOption.DOT_MATCHES_ALL), "")
                        .replace(Regex("<[^>]+>"), " ")
                        .replace(Regex("\\s{2,}"), " ")
                        .trim()
                    if (text.length > 50) sb.append(text).append("\n\n")
                }
        }
        return sb.toString()
    }

    private fun mapStageProgress(stage: String, pct: Int): Float {
        val (lo, hi) = when (stage) {
            "ocr" -> 0f to 0.30f
            "correction" -> 0.30f to 0.60f
            "verification" -> 0.60f to 0.85f
            "export" -> 0.85f to 1f
            "done" -> 1f to 1f
            else -> 0f to 1f
        }
        return lo + (pct / 100f) * (hi - lo)
    }

    private fun formatSize(bytes: Long): String {
        val mb = bytes / (1024.0 * 1024.0)
        return if (mb >= 1) "%.1f MB".format(mb) else "%.0f KB".format(bytes / 1024.0)
    }
}
