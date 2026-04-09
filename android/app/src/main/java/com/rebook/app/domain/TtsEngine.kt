package com.rebook.app.domain

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withContext
import okhttp3.*
import okio.ByteString
import java.io.File
import java.io.FileOutputStream
import java.security.MessageDigest
import java.util.UUID
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.suspendCancellableCoroutine
import java.util.concurrent.atomic.AtomicInteger

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
        rate: String = "0%",
    ): Result<File> = withContext(Dispatchers.IO) {
        runCatching {
            val connId = UUID.randomUUID().toString().replace("-", "")
            val secGec = generateSecMsGec()
            val url = "$BASE_WSS_URL" +
                "?TrustedClientToken=$TRUSTED_CLIENT_TOKEN" +
                "&Sec-MS-GEC=$secGec" +
                "&Sec-MS-GEC-Version=$SEC_MS_GEC_VERSION" +
                "&ConnectionId=$connId"

            suspendCancellableCoroutine<File> { cont ->
                val audioBuffer = mutableListOf<ByteArray>()

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
                        val configMsg = buildConfigMessage()
                        ws.send(configMsg)
                        val ssml = buildSsml(text, voice, rate)
                        val ssmlMsg = buildSsmlMessage(ssml)
                        ws.send(ssmlMsg)
                    }

                    override fun onMessage(ws: WebSocket, text: String) {
                        if (text.contains("Path:turn.end")) {
                            ws.close(1000, null)
                            if (!cont.isCompleted) {
                                if (audioBuffer.isEmpty()) {
                                    cont.resumeWithException(Exception("No audio received from Edge TTS"))
                                    return
                                }
                                outputFile.parentFile?.mkdirs()
                                FileOutputStream(outputFile).use { fos ->
                                    audioBuffer.forEach { fos.write(it) }
                                }
                                cont.resume(outputFile)
                            }
                        }
                    }

                    override fun onMessage(ws: WebSocket, bytes: ByteString) {
                        // Edge TTS binary frame format:
                        //   bytes[0..1] = header length (big-endian uint16)
                        //   bytes[2..2+headerLen-1] = ASCII header text
                        //   bytes[2+headerLen..] = MP3 audio data
                        val raw = bytes.toByteArray()
                        if (raw.size < 2) return
                        val headerLen = ((raw[0].toInt() and 0xFF) shl 8) or (raw[1].toInt() and 0xFF)
                        val audioStart = 2 + headerLen
                        if (audioStart >= raw.size) return  // metadata-only frame, no audio
                        val header = String(raw, 2, headerLen, Charsets.US_ASCII)
                        if (!header.contains("Path:audio")) return
                        audioBuffer.add(raw.copyOfRange(audioStart, raw.size))
                    }

                    override fun onFailure(ws: WebSocket, t: Throwable, response: Response?) {
                        if (!cont.isCompleted) {
                            cont.resumeWithException(t)
                        }
                    }

                    override fun onClosed(ws: WebSocket, code: Int, reason: String) {
                        // If we get here without turn.end, audio might still be empty
                        if (!cont.isCompleted) {
                            if (audioBuffer.isNotEmpty()) {
                                outputFile.parentFile?.mkdirs()
                                FileOutputStream(outputFile).use { fos ->
                                    audioBuffer.forEach { fos.write(it) }
                                }
                                cont.resume(outputFile)
                            } else {
                                cont.resumeWithException(Exception("WebSocket closed without audio"))
                            }
                        }
                    }
                }

                val ws = client.newWebSocket(request, listener)
                cont.invokeOnCancellation { ws.close(1000, "Cancelled") }
            }
        }
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

    private fun buildSsml(text: String, voice: String, rate: String = "0%"): String {
        val locale = voice.substringBeforeLast("-").replace("-", "-")
        val escaped = text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\"", "&quot;")
        return """<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='$locale'>""" +
                """<voice name='$voice'><prosody rate='$rate'>$escaped</prosody></voice></speak>"""
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

    // ── Full audiobook generation (parallel) ──────────────────────────────────

    /** Max concurrent Edge TTS WebSocket connections */
    private val ttsSemaphore = Semaphore(8)

    suspend fun generateAudiobook(
        text: String,
        voice: String,
        outputDir: File,
        rate: String = "0%",
        onProgress: (Int, Int, String) -> Unit = { _, _, _ -> },
    ): List<File> = withContext(Dispatchers.IO) {
        outputDir.mkdirs()
        val chapters = detectChapters(text)
        val total = chapters.size
        val completedCount = AtomicInteger(0)

        // Prepare output files up-front (indexed names)
        data class ChapterJob(val index: Int, val title: String, val cleanText: String, val outFile: File)
        val jobs = chapters.mapIndexedNotNull { i, chapter ->
            val clean = cleanTextForTts(chapter.text)
            if (clean.isBlank()) return@mapIndexedNotNull null
            val safeTitle = chapter.title
                .replace(Regex("[^\\wĄąĆćĘęŁłŃńÓóŚśŹźŻż\\s-]"), "")
                .trim().replace(Regex("\\s+"), "_").take(50)
            val outFile = File(outputDir, "%02d_%s.mp3".format(i + 1, safeTitle))
            ChapterJob(i, chapter.title, clean, outFile)
        }

        onProgress(0, total, "Generuję ${jobs.size} rozdziałów (×8 równolegle)…")

        // Launch all chapters in parallel, limited by semaphore
        val results = jobs.map { job ->
            async {
                ttsSemaphore.withPermit {
                    val chunks = chunkBySentence(job.cleanText, 4000)
                    val result: File? = if (chunks.size == 1) {
                        synthesize(job.cleanText, voice, job.outFile, rate).getOrNull()
                    } else {
                        // Multi-chunk: synthesize each → concatenate
                        val parts = mutableListOf<ByteArray>()
                        var ok = true
                        for (chunk in chunks) {
                            val tmp = File.createTempFile("chunk_", ".mp3", outputDir)
                            val r = synthesize(chunk, voice, tmp, rate)
                            r.onSuccess { f -> parts.add(f.readBytes()); f.delete() }
                            r.onFailure { ok = false; tmp.delete() }
                        }
                        if (ok && parts.isNotEmpty()) {
                            FileOutputStream(job.outFile).use { fos -> parts.forEach(fos::write) }
                            job.outFile
                        } else null
                    }
                    val done = completedCount.incrementAndGet()
                    onProgress(done, total, "${done}/${total}: ${job.title.take(40)}…")
                    result
                }
            }
        }.awaitAll()

        var generated = results.filterNotNull().sortedBy { it.name }

        // Post-process: if fast generation was used, slow audio back to normal speed
        if (rate != "0%" && generated.isNotEmpty()) {
            onProgress(0, generated.size, "🔄 Normalizuję prędkość audio…")
            // rate="+50%" → audio is 1.5x → slow down by 0.6667 to get 1.0x
            val speedFactor = 1.0f / 1.5f  // 0.6667
            val normalized = mutableListOf<File>()
            for ((i, mp3) in generated.withIndex()) {
                try {
                    val m4a = File(mp3.parent, mp3.nameWithoutExtension + ".m4a")
                    AudioTimeStretcher.stretchFile(mp3, m4a, speedFactor)
                    mp3.delete()  // Remove fast MP3
                    normalized.add(m4a)
                    onProgress(i + 1, generated.size, "🔄 ${i + 1}/${generated.size}: ${mp3.nameWithoutExtension}")
                } catch (e: Exception) {
                    // Keep original MP3 if stretch fails
                    normalized.add(mp3)
                    onProgress(i + 1, generated.size, "⚠️ Stretch error: ${e.message?.take(40)}")
                }
            }
            generated = normalized.sortedBy { it.name }
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
