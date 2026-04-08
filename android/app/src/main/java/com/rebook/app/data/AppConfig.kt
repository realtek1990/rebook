package com.rebook.app.data

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "rebook_config")

data class AppConfig(
    val llmProvider: String = "",
    val modelName: String = "",
    val apiKey: String = "",
    val kindleEmail: String = "",
    // ── OCR provider (separate from LLM) ─────────────────────────────────
    val ocrProvider: String = "auto",   // "auto" | "mistral" | "gemini" | "marker"
    val ocrApiKey: String = "",         // if empty, falls back to apiKey
    val ocrModel: String = "",          // if empty, uses provider default
) {
    /** Effective API key for OCR (falls back to main key). */
    val effectiveOcrApiKey: String get() = ocrApiKey.ifBlank { apiKey }

    /** True when a cloud OCR provider is configured with a usable key. */
    val isCloudOcrAvailable: Boolean get() = when (ocrProvider) {
        "marker" -> false
        "mistral" -> effectiveOcrApiKey.isNotBlank()
        "gemini"  -> effectiveOcrApiKey.isNotBlank()
        else      -> effectiveOcrApiKey.isNotBlank() // "auto"
    }
}

object ConfigKeys {
    val LLM_PROVIDER = stringPreferencesKey("llm_provider")
    val MODEL_NAME   = stringPreferencesKey("model_name")
    val API_KEY      = stringPreferencesKey("api_key")
    val KINDLE_EMAIL = stringPreferencesKey("kindle_email")
    val OCR_PROVIDER = stringPreferencesKey("ocr_provider")
    val OCR_API_KEY  = stringPreferencesKey("ocr_api_key")
    val OCR_MODEL    = stringPreferencesKey("ocr_model")
}

class AppConfigStore(private val context: Context) {

    suspend fun load(): AppConfig {
        val prefs = context.dataStore.data.first()
        return AppConfig(
            llmProvider = prefs[ConfigKeys.LLM_PROVIDER] ?: "",
            modelName   = prefs[ConfigKeys.MODEL_NAME]   ?: "",
            apiKey      = prefs[ConfigKeys.API_KEY]      ?: "",
            kindleEmail = prefs[ConfigKeys.KINDLE_EMAIL] ?: "",
            ocrProvider = prefs[ConfigKeys.OCR_PROVIDER] ?: "auto",
            ocrApiKey   = prefs[ConfigKeys.OCR_API_KEY]  ?: "",
            ocrModel    = prefs[ConfigKeys.OCR_MODEL]    ?: "",
        )
    }

    suspend fun save(config: AppConfig) {
        context.dataStore.edit { prefs ->
            prefs[ConfigKeys.LLM_PROVIDER] = config.llmProvider
            prefs[ConfigKeys.MODEL_NAME]   = config.modelName
            prefs[ConfigKeys.API_KEY]      = config.apiKey
            prefs[ConfigKeys.KINDLE_EMAIL] = config.kindleEmail
            prefs[ConfigKeys.OCR_PROVIDER] = config.ocrProvider
            prefs[ConfigKeys.OCR_API_KEY]  = config.ocrApiKey
            prefs[ConfigKeys.OCR_MODEL]    = config.ocrModel
        }
    }

    fun observe() = context.dataStore.data.map { prefs ->
        AppConfig(
            llmProvider = prefs[ConfigKeys.LLM_PROVIDER] ?: "",
            modelName   = prefs[ConfigKeys.MODEL_NAME]   ?: "",
            apiKey      = prefs[ConfigKeys.API_KEY]      ?: "",
            kindleEmail = prefs[ConfigKeys.KINDLE_EMAIL] ?: "",
            ocrProvider = prefs[ConfigKeys.OCR_PROVIDER] ?: "auto",
            ocrApiKey   = prefs[ConfigKeys.OCR_API_KEY]  ?: "",
            ocrModel    = prefs[ConfigKeys.OCR_MODEL]    ?: "",
        )
    }
}
