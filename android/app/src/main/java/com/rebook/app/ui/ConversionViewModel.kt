package com.rebook.app.ui

import android.app.Application
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.rebook.app.data.AppConfig
import com.rebook.app.data.AppConfigStore
import com.rebook.app.domain.Converter
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch

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
                }

                _state.update {
                    it.copy(
                        isConverting = false,
                        outputPath = result,
                        progressPercent = 1f,
                        progressMessage = "✅ Gotowe!",
                    )
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
            }
        }
    }

    fun stopConversion() {
        _state.update { it.copy(isCancelled = true) }
    }

    private fun mapStageProgress(stage: String, pct: Int): Float {
        val (lo, hi) = when (stage) {
            "ocr" -> 0f to 0.35f
            "correction" -> 0.35f to 0.85f
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
