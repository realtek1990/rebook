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
)

object ConfigKeys {
    val LLM_PROVIDER = stringPreferencesKey("llm_provider")
    val MODEL_NAME = stringPreferencesKey("model_name")
    val API_KEY = stringPreferencesKey("api_key")
    val KINDLE_EMAIL = stringPreferencesKey("kindle_email")
}

class AppConfigStore(private val context: Context) {

    suspend fun load(): AppConfig {
        val prefs = context.dataStore.data.first()
        return AppConfig(
            llmProvider = prefs[ConfigKeys.LLM_PROVIDER] ?: "",
            modelName = prefs[ConfigKeys.MODEL_NAME] ?: "",
            apiKey = prefs[ConfigKeys.API_KEY] ?: "",
            kindleEmail = prefs[ConfigKeys.KINDLE_EMAIL] ?: "",
        )
    }

    suspend fun save(config: AppConfig) {
        context.dataStore.edit { prefs ->
            prefs[ConfigKeys.LLM_PROVIDER] = config.llmProvider
            prefs[ConfigKeys.MODEL_NAME] = config.modelName
            prefs[ConfigKeys.API_KEY] = config.apiKey
            prefs[ConfigKeys.KINDLE_EMAIL] = config.kindleEmail
        }
    }

    fun observe() = context.dataStore.data.map { prefs ->
        AppConfig(
            llmProvider = prefs[ConfigKeys.LLM_PROVIDER] ?: "",
            modelName = prefs[ConfigKeys.MODEL_NAME] ?: "",
            apiKey = prefs[ConfigKeys.API_KEY] ?: "",
            kindleEmail = prefs[ConfigKeys.KINDLE_EMAIL] ?: "",
        )
    }
}
