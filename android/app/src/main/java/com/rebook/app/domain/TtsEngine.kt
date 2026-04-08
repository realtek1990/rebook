package com.rebook.app.domain

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.*
import okio.ByteString
import java.io.File
import java.io.FileOutputStream
import java.security.MessageDigest
import java.util.UUID
import kotlin.coroutines.resume
import kotlinx.coroutines.suspendCancellableCoroutine

/**
 * TtsEngine — Audiobook generator for Android.
 *
 * Uses Microsoft Edge TTS endpoint (same as edge-tts Python library) via WebSocket.
 * Free, neural-quality voices, requires internet. Same quality as desktop.
 *
 * No extra dependencies — uses OkHttp (already in project).
 */
class TtsEngine {

    companion object {
        val VOICES: LinkedHashMap<String, String> = linkedMapOf(
            "pl-PL-MarekNeural"   to "Marek (PL, Męski)",
            "pl-PL-ZofiaNeural"   to "Zofia (PL, Żeński)",
            "en-US-GuyNeural"     to "Guy (EN, Male)",
            "en-US-JennyNeural"   to "Jenny (EN, Female)",
            "es-ES-AlvaroNeural"  to "Álvaro (ES, Male)",
            "es-ES-ElviraNeural"  to "Elvira (ES, Female)",
            "de-DE-ConradNeural"  to "Conrad (DE, Male)",
            "fr-FR-HenriNeural"   to "Henri (FR, Male)",
        )

        val SAMPLE_TEXTS: Map<String, String> = mapOf(
            "pl-PL-MarekNeural"  to "Witaj! Jestem Marek, Twój lektor audiobooków.",
            "pl-PL-ZofiaNeural"  to "Witaj! Jestem Zofia, Twój lektor audiobooków.",
            "en-US-GuyNeural"    to "Hello! I'm Guy, your audiobook narrator.",
            "en-US-JennyNeural"  to "Hello! I'm Jenny, your audiobook narrator.",
            "es-ES-AlvaroNeural" to "¡Hola! Soy Álvaro, tu narrador de audiolibros.",
            "es-ES-ElviraNeural" to "¡Hola! Soy Elvira, tu narradora de audiolibros.",
            "de-DE-ConradNeural" to "Hallo! Ich bin Conrad, Ihr Hörbuch-Erzähler.",
            "fr-FR-HenriNeural"  to "Bonjour! Je suis Henri, votre narrateur.",
        )

        private const val TRUSTED_CLIENT_TOKEN = "6A5AA1D4EAFF4E9FB37E23D68491D6F4"
        private const val WIN_EPOCH = 11_644_473_600L  // seconds from 1601 to 1970
        private const val CHROMIUM_VERSION = "143"
        private const val SEC_MS_GEC_VERSION = "1-143.0.3650.75"
        private const val BASE_WSS_URL =
            "wss://speech.platform.bing.com/consumer/speech/synthesize/readaloud/edge/v1"

        /**
         * Sec-MS-GEC token — required by Microsoft Edge TTS since ~2024.
         * Algorithm: round unix time to nearest 5 min, add WIN_EPOCH offset,
         * convert to 100ns Windows file time ticks, then SHA256(ticks+token).uppercase()
         */
        fun generateSecMsGec(): String {
            val unixSec = System.currentTimeMillis() / 1000.0
            var ticks = unixSec + WIN_EPOCH
            ticks -= ticks % 300
            ticks *= 1e9 / 100
            val input = "${ticks.toLong()}$TRUSTED_CLIENT_TOKEN"
            val digest = java.security.MessageDigest.getInstance("SHA-256")
                .digest(input.toByteArray(Charsets.US_ASCII))
            return digest.joinToString("") { "%02x".format(it) }.uppercase()
        }

        private const val MIN_CHAPTER_WORDS = 400
        private const val FALLBACK_WORDS_PER_CHUNK = 5000

        private val CHAPTER_PATTERNS = listOf(
            Regex("""^#{1,2}\s+.{1,80}""", RegexOption.MULTILINE),
            Regex("""^(Rozdział|Rozdzial|ROZDZIAŁ|Część|CZEŚĆ|Prolog|Epilog|Wstęp|Posłowie)\s*[\dIVXivx]*""", RegexOption.MULTILINE),
            Regex("""^(Chapter|CHAPTER|Part|PART|Prologue|Epilogue|Introduction)\s*[\dIVXivx]*""", RegexOption.MULTILINE),
            Regex("""^(Capítulo|Capitulo|CAPÍTULO|Parte|Kapitel|Chapitre)\s*[\dIVXivx]*""", RegexOption.MULTILINE),
        )
    }

    data class Chapter(val title: String, val text: String, val index: Int)

    private val client = OkHttpClient.Builder()
        .readTimeout(60, java.util.concurrent.TimeUnit.SECONDS)
        .build()

    // ── Edge TTS Synthesis ────────────────────────────────────────────────────

    /**
     * Synthesize text to an MP3 file using Microsoft Edge TTS (WebSocket).
     * Returns the output file path.
     */
    suspend fun synthesize(
        text: String,
        voice: String,
        outputFile: File,
    ): Result<File> = withContext(Dispatchers.IO) {
        runCatching {
            val connId = UUID.randomUUID().toString().replace("-", "")
            val secGec = generateSecMsGec()
            val url = "$BASE_WSS_URL" +
                "?TrustedClientToken=$TRUSTED_CLIENT_TOKEN" +
                "&Sec-MS-GEC=$secGec" +
                "&Sec-MS-GEC-Version=$SEC_MS_GEC_VERSION" +
                "&ConnectionId=$connId"

            suspendCancellableCoroutine { cont ->
                val audioBuffer = mutableListOf<ByteArray>()
                var receivingAudio = false

                val request = Request.Builder()
                    .url(url)
                    .header("Origin", "chrome-extension://jdiccldimpdaibmpdkjnbmckianbfold")
                    .header("User-Agent",
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
                        "(KHTML, like Gecko) Chrome/$CHROMIUM_VERSION.0.0.0 Safari/537.36 " +
                        "Edg/$CHROMIUM_VERSION.0.0.0")
                    .header("Pragma", "no-cache")
                    .header("Cache-Control", "no-cache")
                    .build()

                val listener = object : WebSocketListener() {

                    override fun onOpen(ws: WebSocket, response: Response) {
                        // 1. Send config message
                        val configMsg = buildConfigMessage()
                        ws.send(configMsg)

                        // 2. Send SSML message
                        val ssml = buildSsml(text, voice)
                        val ssmlMsg = buildSsmlMessage(ssml)
                        ws.send(ssmlMsg)
                    }

                    override fun onMessage(ws: WebSocket, text: String) {
                        when {
                            text.contains("Path:audio") -> receivingAudio = true
                            text.contains("Path:turn.end") -> {
                                // Done — flush audio to file
                                ws.close(1000, null)
                                if (audioBuffer.isEmpty()) {
                                    cont.resume(Result.failure(Exception("No audio received from Edge TTS")))
                                    return
                                }
                                outputFile.parentFile?.mkdirs()
                                FileOutputStream(outputFile).use { fos ->
                                    audioBuffer.forEach { fos.write(it) }
                                }
                                cont.resume(Result.success(outputFile))
                            }
                        }
                    }

                    override fun onMessage(ws: WebSocket, bytes: ByteString) {
                        if (!receivingAudio) return
                        // Binary audio chunk — strip the header (find 0x00 0x00 = end of header)
                        val raw = bytes.toByteArray()
                        val headerEnd = findAudioStart(raw)
                        if (headerEnd >= 0 && headerEnd < raw.size) {
                            audioBuffer.add(raw.copyOfRange(headerEnd, raw.size))
                        }
                    }

                    override fun onFailure(ws: WebSocket, t: Throwable, response: Response?) {
                        if (!cont.isCompleted) {
                            cont.resume(Result.failure(t))
                        }
                    }

                    override fun onClosed(ws: WebSocket, code: Int, reason: String) {
                        // already resumed in onMessage
                    }
                }

                val ws = client.newWebSocket(request, listener)
                cont.invokeOnCancellation { ws.close(1000, "Cancelled") }
            }
        }.getOrElse { Result.failure(it) }
    }

    /** Find the start of MP3 audio data after the binary WebSocket header */
    private fun findAudioStart(data: ByteArray): Int {
        // Edge TTS binary frames: text header + 0x00 0x00 separator + audio
        for (i in 0 until data.size - 1) {
            if (data[i] == 0x00.toByte() && data[i + 1] == 0x00.toByte()) {
                return i + 2
            }
        }
        return 0
    }

    private fun buildConfigMessage(): String {
        val timestamp = edgeTimestamp()
        return "X-Timestamp:$timestamp\r\n" +
                "Content-Type:application/json; charset=utf-8\r\n" +
                "Path:speech.config\r\n\r\n" +
                """{"context":{"synthesis":{"audio":{"metadataoptions":{"sentenceBoundaryEnabled":"false","wordBoundaryEnabled":"false"},"outputFormat":"audio-24khz-48kbitrate-mono-mp3"}}}}"""
    }

    private fun buildSsmlMessage(ssml: String): String {
        val timestamp = edgeTimestamp()
        return "X-RequestId:${UUID.randomUUID().toString().replace("-", "")}\r\n" +
                "Content-Type:application/ssml+xml\r\n" +
                "X-Timestamp:${timestamp}Z\r\n" +
                "Path:ssml\r\n\r\n" +
                ssml
    }

    private fun buildSsml(text: String, voice: String): String {
        val locale = voice.substringBeforeLast("-").replace("-", "-")
        val escaped = text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\"", "&quot;")
        return """<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='$locale'>""" +
                """<voice name='$voice'><prosody rate='0%'>$escaped</prosody></voice></speak>"""
    }

    private fun edgeTimestamp(): String {
        val sdf = java.text.SimpleDateFormat("EEE MMM dd yyyy HH:mm:ss 'GMT+0000 (Coordinated Universal Time)'", java.util.Locale.US)
        sdf.timeZone = java.util.TimeZone.getTimeZone("UTC")
        return sdf.format(java.util.Date())
    }

    // ── Sample playback ───────────────────────────────────────────────────────

    /**
     * Generate a short sample and return the temp file path.
     * Caller is responsible for playing and deleting the file.
     */
    suspend fun generateSample(voice: String): Result<File> {
        val text = SAMPLE_TEXTS[voice] ?: "Witaj! Jestem Twoim lektorem audiobooków."
        val tmp = File.createTempFile("tts_sample_", ".mp3")
        return synthesize(text, voice, tmp)
    }

    // ── Chapter detection ─────────────────────────────────────────────────────

    fun detectChapters(text: String): List<Chapter> {
        // 1. Markdown headings
        val mdSplit = text.split(Regex("""(?=^#{1,2}\s)""", RegexOption.MULTILINE))
            .map { it.trim() }.filter { it.isNotBlank() }
        if (mdSplit.size > 1) return buildChapters(mdSplit)

        // 2. Language-specific patterns
        for (pattern in CHAPTER_PATTERNS.drop(1)) {
            val positions = pattern.findAll(text).map { it.range.first }.toList()
            if (positions.size >= 2) {
                val parts = positions.mapIndexed { i, pos ->
                    val end = if (i + 1 < positions.size) positions[i + 1] else text.length
                    text.substring(pos, end).trim()
                }.filter { it.isNotBlank() }
                if (parts.size > 1) return buildChapters(parts)
            }
        }

        // 3. Fallback: word count
        return splitByWords(text, FALLBACK_WORDS_PER_CHUNK)
    }

    private fun buildChapters(parts: List<String>): List<Chapter> {
        val chapters = mutableListOf<Chapter>()
        var buffer = ""
        var bufferTitle = "Wstęp"

        for (part in parts) {
            val title = part.lines().firstOrNull()
                ?.replace(Regex("^#+\\s*"), "")?.take(80) ?: "Rozdział"
            val wordCount = part.trim().split(Regex("\\s+")).size

            if (wordCount < MIN_CHAPTER_WORDS && chapters.isNotEmpty()) {
                val last = chapters.removeLast()
                chapters.add(last.copy(text = last.text + "\n\n" + part))
            } else if (buffer.isNotBlank()) {
                chapters.add(Chapter(bufferTitle, buffer, chapters.size))
                buffer = part; bufferTitle = title
            } else {
                buffer = part; bufferTitle = title
            }
        }
        if (buffer.isNotBlank()) chapters.add(Chapter(bufferTitle, buffer, chapters.size))
        return chapters.ifEmpty { listOf(Chapter("Cała książka", parts.joinToString("\n\n"), 0)) }
    }

    private fun splitByWords(text: String, wordsPerChunk: Int): List<Chapter> =
        text.split(Regex("\\s+"))
            .chunked(wordsPerChunk)
            .mapIndexed { i, w -> Chapter("Część ${i + 1}", w.joinToString(" "), i) }

    // ── Text cleanup ──────────────────────────────────────────────────────────

    fun cleanTextForTts(text: String): String = text
        .replace(Regex("""^#{1,6}\s+""", RegexOption.MULTILINE), "")
        .replace(Regex("""\*{1,3}([^*]+)\*{1,3}"""), "$1")
        .replace(Regex("""_{1,2}([^_]+)_{1,2}"""), "$1")
        .replace(Regex("""\[([^\]]+)]\([^)]+\)"""), "$1")
        .replace(Regex("""```.*?```""", RegexOption.DOT_MATCHES_ALL), "")
        .replace(Regex("""`[^`]+`"""), "")
        .replace(Regex("""^[-*_]{3,}\s*$""", RegexOption.MULTILINE), "")
        .replace(Regex("""\n{3,}"""), "\n\n")
        .trim()

    // ── Full audiobook generation ─────────────────────────────────────────────

    suspend fun generateAudiobook(
        text: String,
        voice: String,
        outputDir: File,
        onProgress: (Int, Int, String) -> Unit = { _, _, _ -> },
    ): List<File> = withContext(Dispatchers.IO) {
        outputDir.mkdirs()
        val chapters = detectChapters(text)
        val total = chapters.size
        val generated = mutableListOf<File>()

        for ((i, chapter) in chapters.withIndex()) {
            onProgress(i, total, "Generuję: ${chapter.title.take(50)}…")
            val safeTitle = chapter.title
                .replace(Regex("[^\\wĄąĆćĘęŁłŃńÓóŚśŹźŻż\\s-]"), "")
                .trim().replace(Regex("\\s+"), "_").take(50)
            val outFile = File(outputDir, "%02d_%s.mp3".format(i + 1, safeTitle))
            val clean = cleanTextForTts(chapter.text)
            if (clean.isBlank()) continue

            // Chunk long chapters at sentence boundary (Edge TTS limit ~4500 chars)
            val chunks = chunkBySentence(clean, 4000)
            if (chunks.size == 1) {
                val r = synthesize(clean, voice, outFile)
                r.onSuccess { f -> generated.add(f) }
                r.onFailure { e -> onProgress(i, total, "⚠️ Błąd: ${e.message}") }
            } else {
                // Synthesize each chunk → concatenate raw MP3 bytes
                val parts = mutableListOf<ByteArray>()
                var chunkOk = true
                for (chunk in chunks) {
                    val tmp = File.createTempFile("chunk_", ".mp3", outputDir)
                    val r = synthesize(chunk, voice, tmp)
                    r.onSuccess { f -> parts.add(f.readBytes()); f.delete() }
                    r.onFailure { chunkOk = false; tmp.delete() }
                }
                if (chunkOk && parts.isNotEmpty()) {
                    FileOutputStream(outFile).use { fos -> parts.forEach(fos::write) }
                    generated.add(outFile)
                }
            }
        }

        // Playlist
        File(outputDir, "playlist.m3u").writeText(buildString {
            appendLine("#EXTM3U")
            generated.forEach {
                appendLine("#EXTINF:-1,${it.nameWithoutExtension}")
                appendLine(it.absolutePath)
            }
        })

        onProgress(total, total, "✅ Gotowe! ${generated.size} plików MP3")
        generated
    }

    private fun chunkBySentence(text: String, maxChars: Int): List<String> {
        if (text.length <= maxChars) return listOf(text)
        val sentences = text.split(Regex("""(?<=[.!?…])\s+"""))
        val chunks = mutableListOf<String>()
        var current = StringBuilder()
        for (s in sentences) {
            if (current.length + s.length + 1 > maxChars) {
                if (current.isNotEmpty()) { chunks.add(current.toString().trim()); current = StringBuilder() }
            }
            if (current.isNotEmpty()) current.append(' ')
            current.append(s)
        }
        if (current.isNotEmpty()) chunks.add(current.toString().trim())
        return chunks.ifEmpty { listOf(text) }
    }
}
