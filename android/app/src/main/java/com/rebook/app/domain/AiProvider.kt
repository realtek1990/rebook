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
        .readTimeout(180, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        // Allow up to MAX_PARALLEL simultaneous connections to the same AI host.
        // Default OkHttp limit is 5/host which serializes parallel coroutines.
        .connectionPool(okhttp3.ConnectionPool(20, 5, TimeUnit.MINUTES))
        .dispatcher(okhttp3.Dispatcher().also { it.maxRequestsPerHost = 20; it.maxRequests = 40 })
        .build()

    private val JSON_MEDIA = "application/json; charset=utf-8".toMediaType()

    data class ProviderInfo(
        val displayName: String,
        val key: String,
        val baseUrl: String,
        val models: List<String>,
    )

    val PROVIDERS = listOf(
        ProviderInfo("NVIDIA NIM", "nvidia", "https://integrate.api.nvidia.com/v1/",
            listOf(
                "mistralai/mistral-small-4-119b-2603",
                "qwen/qwen3.5-122b-a10b",
                "deepseek-ai/deepseek-v3.2",
                "meta/llama-3.3-70b-instruct",
                "google/gemma-3-27b-it",
            )),
        ProviderInfo("Google Gemini", "gemini", "https://generativelanguage.googleapis.com/v1beta/openai/",
            listOf("gemini-3-flash-preview", "gemini-2.5-flash", "gemini-2.5-pro")),
        ProviderInfo("OpenAI", "openai", "https://api.openai.com/v1/",
            listOf("gpt-5-preview", "gpt-4.5-preview", "gpt-4o", "gpt-4o-mini", "o3-mini", "o1", "o1-mini")),
        ProviderInfo("Anthropic", "anthropic", "https://api.anthropic.com/v1/",
            listOf("claude-4.6-opus", "claude-3-7-sonnet-latest", "claude-3-5-haiku-latest", "claude-3-opus-latest")),
        ProviderInfo("Mistral AI", "mistral", "https://api.mistral.ai/v1/",
            listOf("mistral-large-latest", "mistral-medium", "pixtral-large-latest", "ministral-8b-latest", "mistral-small-latest")),
        ProviderInfo("Groq", "groq", "https://api.groq.com/openai/v1/",
            listOf("llama-3.3-70b-versatile", "llama-3.1-8b-instant", "deepseek-r1-distill-llama-70b", "mixtral-8x7b-32768")),
        ProviderInfo("Zhipu AI", "zhipu", "https://open.bigmodel.cn/api/paas/v4/",
            listOf("glm-4-plus", "glm-4-flashx", "glm-4-long", "glm-4-airx", "glm-4-flash")),
        ProviderInfo("GLM / ZhipuAI", "zhipuai", "https://open.bigmodel.cn/api/coding/paas/v4/",
            listOf("glm-4-plus", "glm-4-flashx", "glm-4-long", "glm-4-airx", "glm-4-flash")),
        ProviderInfo("Kimi / Moonshot", "moonshot", "https://api.moonshot.cn/v1/",
            listOf("moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k")),
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
