package com.rebook.app.domain

import kotlinx.serialization.json.*
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import com.rebook.app.data.AppConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.util.concurrent.TimeUnit

/**
 * Multi-provider AI client — replaces Python's LiteLLM.
 * Direct HTTP calls to each provider's chat completion endpoint.
 */
object AiProvider {

    private val client = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    private val JSON_MEDIA = "application/json; charset=utf-8".toMediaType()

    data class ProviderInfo(
        val displayName: String,
        val key: String,
        val baseUrl: String,
        val models: List<String>,
    )

    val PROVIDERS = listOf(
        ProviderInfo("Google Gemini", "gemini", "https://generativelanguage.googleapis.com/v1beta/openai/", listOf("gemini-2.5-flash", "gemini-2.5-pro")),
        ProviderInfo("OpenAI", "openai", "https://api.openai.com/v1/", listOf("gpt-4o", "gpt-4o-mini", "o3-mini")),
        ProviderInfo("Anthropic", "anthropic", "https://api.anthropic.com/v1/", listOf("claude-3-7-sonnet-latest")),
        ProviderInfo("Mistral AI", "mistral", "https://api.mistral.ai/v1/", listOf("mistral-large-latest")),
        ProviderInfo("Groq", "groq", "https://api.groq.com/openai/v1/", listOf("llama-3.3-70b-versatile")),
        ProviderInfo("ZhipuAI", "zhipuai", "https://open.bigmodel.cn/api/coding/paas/v4/", listOf("glm-4-flash", "glm-4-plus")),
        ProviderInfo("Kimi / Moonshot", "moonshot", "https://api.moonshot.cn/v1/", listOf("moonshot-v1-auto")),
    )

    fun findProvider(key: String): ProviderInfo? = PROVIDERS.find { it.key == key }

    /**
     * Send a chat completion request to the configured provider.
     * Most providers use OpenAI-compatible API format.
     * Anthropic uses its own format — handled separately.
     */
    suspend fun complete(
        systemPrompt: String,
        userText: String,
        config: AppConfig,
        temperature: Double = 0.1,
        maxTokens: Int = 16384,
    ): String = withContext(Dispatchers.IO) {
        val provider = findProvider(config.llmProvider)
            ?: throw IllegalArgumentException("Unknown provider: ${config.llmProvider}")

        if (provider.key == "anthropic") {
            return@withContext callAnthropic(systemPrompt, userText, config, provider, temperature, maxTokens)
        }

        // OpenAI-compatible format (works for Gemini, OpenAI, Mistral, Groq, ZhipuAI, Moonshot)
        val body = buildJsonObject {
            put("model", config.modelName)
            putJsonArray("messages") {
                addJsonObject {
                    put("role", "system")
                    put("content", systemPrompt)
                }
                addJsonObject {
                    put("role", "user")
                    put("content", userText)
                }
            }
            put("temperature", temperature)
            put("max_tokens", maxTokens)
        }

        val url = "${provider.baseUrl}chat/completions"
        val request = Request.Builder()
            .url(url)
            .addHeader("Authorization", "Bearer ${config.apiKey}")
            .addHeader("Content-Type", "application/json")
            .post(body.toString().toRequestBody(JSON_MEDIA))
            .build()

        val response = client.newCall(request).execute()
        if (!response.isSuccessful) {
            throw RuntimeException("AI API error ${response.code}: ${response.body?.string()?.take(500)}")
        }

        val json = Json.parseToJsonElement(response.body!!.string()).jsonObject
        val content = json["choices"]?.jsonArray
            ?.firstOrNull()?.jsonObject
            ?.get("message")?.jsonObject
            ?.get("content")?.jsonPrimitive?.contentOrNull

        content?.trim() ?: throw RuntimeException("AI returned empty response")
    }

    private suspend fun callAnthropic(
        systemPrompt: String,
        userText: String,
        config: AppConfig,
        provider: ProviderInfo,
        temperature: Double,
        maxTokens: Int,
    ): String {
        val body = buildJsonObject {
            put("model", config.modelName)
            put("max_tokens", maxTokens)
            put("temperature", temperature)
            put("system", systemPrompt)
            putJsonArray("messages") {
                addJsonObject {
                    put("role", "user")
                    put("content", userText)
                }
            }
        }

        val request = Request.Builder()
            .url("${provider.baseUrl}messages")
            .addHeader("x-api-key", config.apiKey)
            .addHeader("anthropic-version", "2023-06-01")
            .addHeader("Content-Type", "application/json")
            .post(body.toString().toRequestBody(JSON_MEDIA))
            .build()

        val response = client.newCall(request).execute()
        if (!response.isSuccessful) {
            throw RuntimeException("Anthropic error ${response.code}: ${response.body?.string()?.take(500)}")
        }

        val json = Json.parseToJsonElement(response.body!!.string()).jsonObject
        val content = json["content"]?.jsonArray
            ?.firstOrNull()?.jsonObject
            ?.get("text")?.jsonPrimitive?.contentOrNull

        return content?.trim() ?: throw RuntimeException("Anthropic returned empty response")
    }
}
