package com.rebook.app.domain

import android.media.MediaCodec
import android.media.MediaExtractor
import android.media.MediaFormat
import android.media.MediaMuxer
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.ShortBuffer

/**
 * Slows down an MP3 file by a given factor using Android's built-in
 * MediaCodec (decode/encode) and a simple WSOLA-inspired time-stretch.
 *
 * No external dependencies required (no ffmpeg, no Sonic library).
 *
 * Usage:
 *   AudioTimeStretcher.stretchFile(inputMp3, outputM4a, 0.6667f)
 *   // 0.6667 = slow down 1.5x audio back to 1.0x
 */
object AudioTimeStretcher {

    /**
     * Time-stretch [inputFile] (MP3) by [speed] factor and write to [outputFile] (M4A/AAC).
     * speed < 1.0 = slower (longer), speed > 1.0 = faster (shorter).
     * For converting +50% rate TTS back to normal: speed = 0.6667f
     */
    fun stretchFile(inputFile: File, outputFile: File, speed: Float = 0.6667f) {
        // 1. Decode MP3 to PCM
        val pcmResult = decodeToPcm(inputFile)

        // 2. Time-stretch PCM
        val stretched = timeStretchPcm(
            pcmResult.samples,
            pcmResult.sampleRate,
            pcmResult.channels,
            speed
        )

        // 3. Encode PCM to M4A (AAC)
        encodePcmToM4a(
            stretched,
            pcmResult.sampleRate,
            pcmResult.channels,
            outputFile
        )
    }

    private data class PcmResult(
        val samples: ShortArray,
        val sampleRate: Int,
        val channels: Int,
    )

    private fun decodeToPcm(inputFile: File): PcmResult {
        val extractor = MediaExtractor()
        extractor.setDataSource(inputFile.absolutePath)

        // Find audio track
        var trackIndex = -1
        var format: MediaFormat? = null
        for (i in 0 until extractor.trackCount) {
            val f = extractor.getTrackFormat(i)
            if (f.getString(MediaFormat.KEY_MIME)?.startsWith("audio/") == true) {
                trackIndex = i
                format = f
                break
            }
        }
        require(trackIndex >= 0 && format != null) { "No audio track found" }

        extractor.selectTrack(trackIndex)
        val mime = format.getString(MediaFormat.KEY_MIME)!!
        val sampleRate = format.getInteger(MediaFormat.KEY_SAMPLE_RATE)
        val channels = format.getInteger(MediaFormat.KEY_CHANNEL_COUNT)

        val decoder = MediaCodec.createDecoderByType(mime)
        decoder.configure(format, null, null, 0)
        decoder.start()

        val pcmChunks = mutableListOf<ShortArray>()
        val bufferInfo = MediaCodec.BufferInfo()
        var inputDone = false
        val timeoutUs = 10_000L

        while (true) {
            // Feed input
            if (!inputDone) {
                val inIdx = decoder.dequeueInputBuffer(timeoutUs)
                if (inIdx >= 0) {
                    val buf = decoder.getInputBuffer(inIdx)!!
                    val size = extractor.readSampleData(buf, 0)
                    if (size < 0) {
                        decoder.queueInputBuffer(inIdx, 0, 0, 0,
                            MediaCodec.BUFFER_FLAG_END_OF_STREAM)
                        inputDone = true
                    } else {
                        decoder.queueInputBuffer(inIdx, 0, size,
                            extractor.sampleTime, 0)
                        extractor.advance()
                    }
                }
            }

            // Drain output
            val outIdx = decoder.dequeueOutputBuffer(bufferInfo, timeoutUs)
            if (outIdx >= 0) {
                val outBuf = decoder.getOutputBuffer(outIdx)!!
                if (bufferInfo.size > 0) {
                    outBuf.position(bufferInfo.offset)
                    outBuf.limit(bufferInfo.offset + bufferInfo.size)
                    val shortBuf = outBuf.order(ByteOrder.LITTLE_ENDIAN).asShortBuffer()
                    val shorts = ShortArray(shortBuf.remaining())
                    shortBuf.get(shorts)
                    pcmChunks.add(shorts)
                }
                decoder.releaseOutputBuffer(outIdx, false)
                if (bufferInfo.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) break
            }
        }

        decoder.stop()
        decoder.release()
        extractor.release()

        // Flatten chunks
        val totalSamples = pcmChunks.sumOf { it.size }
        val allSamples = ShortArray(totalSamples)
        var offset = 0
        for (chunk in pcmChunks) {
            System.arraycopy(chunk, 0, allSamples, offset, chunk.size)
            offset += chunk.size
        }

        return PcmResult(allSamples, sampleRate, channels)
    }

    /**
     * Simple overlap-add time-stretch (WSOLA-like).
     * speed < 1.0 = slow down, speed > 1.0 = speed up.
     */
    private fun timeStretchPcm(
        input: ShortArray,
        sampleRate: Int,
        channels: Int,
        speed: Float
    ): ShortArray {
        val windowSize = (sampleRate * channels * 0.025f).toInt() and 0x7FFFFFFE // ~25ms, even
        val hopIn = (windowSize * speed).toInt().coerceAtLeast(1)
        val hopOut = windowSize

        // Estimate output size
        val outputSize = ((input.size / speed) * 1.1f).toInt()
        val output = ShortArray(outputSize)
        var outPos = 0
        var inPos = 0

        // Hann window
        val window = FloatArray(windowSize) { i ->
            (0.5 * (1.0 - Math.cos(2.0 * Math.PI * i / windowSize))).toFloat()
        }

        while (inPos + windowSize <= input.size && outPos + windowSize <= output.size) {
            for (i in 0 until windowSize) {
                val windowed = (input[inPos + i] * window[i]).toInt()
                output[outPos + i] = (output[outPos + i] + windowed).toShort()
            }
            inPos += hopIn
            outPos += hopOut
        }

        return output.copyOf(outPos.coerceAtMost(output.size))
    }

    private fun encodePcmToM4a(
        pcm: ShortArray,
        sampleRate: Int,
        channels: Int,
        outputFile: File
    ) {
        outputFile.parentFile?.mkdirs()

        val mime = MediaFormat.MIMETYPE_AUDIO_AAC
        val bitRate = 128_000
        val format = MediaFormat.createAudioFormat(mime, sampleRate, channels).apply {
            setInteger(MediaFormat.KEY_BIT_RATE, bitRate)
            setInteger(MediaFormat.KEY_AAC_PROFILE,
                android.media.MediaCodecInfo.CodecProfileLevel.AACObjectLC)
            setInteger(MediaFormat.KEY_MAX_INPUT_SIZE, 16384)
        }

        val encoder = MediaCodec.createEncoderByType(mime)
        encoder.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
        encoder.start()

        val muxer = MediaMuxer(outputFile.absolutePath, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4)
        var muxerTrackIdx = -1
        var muxerStarted = false

        val bufferInfo = MediaCodec.BufferInfo()
        val timeoutUs = 10_000L

        // Convert shorts to bytes (little-endian)
        val pcmBytes = ByteBuffer.allocate(pcm.size * 2)
            .order(ByteOrder.LITTLE_ENDIAN)
            .apply { asShortBuffer().put(pcm) }
            .array()

        var inputOffset = 0
        var inputDone = false
        var presentationTimeUs = 0L
        val frameDurationUs = 1_000_000L * 1024 / sampleRate  // AAC frame = 1024 samples

        while (true) {
            // Feed input
            if (!inputDone) {
                val inIdx = encoder.dequeueInputBuffer(timeoutUs)
                if (inIdx >= 0) {
                    val buf = encoder.getInputBuffer(inIdx)!!
                    val remaining = pcmBytes.size - inputOffset
                    if (remaining <= 0) {
                        encoder.queueInputBuffer(inIdx, 0, 0, 0,
                            MediaCodec.BUFFER_FLAG_END_OF_STREAM)
                        inputDone = true
                    } else {
                        val size = remaining.coerceAtMost(buf.capacity())
                        buf.clear()
                        buf.put(pcmBytes, inputOffset, size)
                        encoder.queueInputBuffer(inIdx, 0, size, presentationTimeUs, 0)
                        inputOffset += size
                        presentationTimeUs += frameDurationUs
                    }
                }
            }

            // Drain output
            val outIdx = encoder.dequeueOutputBuffer(bufferInfo, timeoutUs)
            when {
                outIdx == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED -> {
                    if (!muxerStarted) {
                        muxerTrackIdx = muxer.addTrack(encoder.outputFormat)
                        muxer.start()
                        muxerStarted = true
                    }
                }
                outIdx >= 0 -> {
                    val outBuf = encoder.getOutputBuffer(outIdx)!!
                    if (bufferInfo.size > 0 && muxerStarted) {
                        outBuf.position(bufferInfo.offset)
                        outBuf.limit(bufferInfo.offset + bufferInfo.size)
                        muxer.writeSampleData(muxerTrackIdx, outBuf, bufferInfo)
                    }
                    encoder.releaseOutputBuffer(outIdx, false)
                    if (bufferInfo.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) break
                }
            }
        }

        encoder.stop()
        encoder.release()
        if (muxerStarted) {
            muxer.stop()
            muxer.release()
        }
    }
}
