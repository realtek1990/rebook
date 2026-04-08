package com.rebook.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.IBinder
import androidx.core.app.NotificationCompat

/**
 * Foreground service that keeps conversion alive when the app is backgrounded.
 *
 * Android kills background processes aggressively (especially on Xiaomi, Samsung etc.).
 * Running as a ForegroundService with a persistent notification prevents this.
 *
 * Usage:
 *   ConversionService.start(context, "Converting book.pdf…")
 *   ConversionService.updateProgress(context, 42, "Translating: 5/12")
 *   ConversionService.stop(context)
 */
class ConversionService : Service() {

    companion object {
        const val CHANNEL_ID     = "rebook_conversion"
        const val NOTIF_ID       = 1001
        const val ACTION_START   = "com.rebook.app.CONVERSION_START"
        const val ACTION_UPDATE  = "com.rebook.app.CONVERSION_UPDATE"
        const val ACTION_STOP    = "com.rebook.app.CONVERSION_STOP"
        const val EXTRA_TITLE    = "title"
        const val EXTRA_PROGRESS = "progress"
        const val EXTRA_MSG      = "message"

        fun start(context: Context, title: String) {
            val intent = Intent(context, ConversionService::class.java).apply {
                action = ACTION_START
                putExtra(EXTRA_TITLE, title)
            }
            context.startForegroundService(intent)
        }

        fun updateProgress(context: Context, progress: Int, message: String) {
            val intent = Intent(context, ConversionService::class.java).apply {
                action = ACTION_UPDATE
                putExtra(EXTRA_PROGRESS, progress)
                putExtra(EXTRA_MSG, message)
            }
            context.startService(intent)
        }

        fun stop(context: Context) {
            val intent = Intent(context, ConversionService::class.java).apply {
                action = ACTION_STOP
            }
            context.startService(intent)
        }
    }

    private lateinit var notifManager: NotificationManager
    private var currentTitle = "ReBook — konwersja"
    private var currentProgress = 0
    private var currentMsg = ""

    override fun onCreate() {
        super.onCreate()
        notifManager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        createChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> {
                currentTitle = intent.getStringExtra(EXTRA_TITLE) ?: currentTitle
                startForeground(NOTIF_ID, buildNotification())
            }
            ACTION_UPDATE -> {
                currentProgress = intent.getIntExtra(EXTRA_PROGRESS, currentProgress)
                currentMsg = intent.getStringExtra(EXTRA_MSG) ?: currentMsg
                notifManager.notify(NOTIF_ID, buildNotification())
            }
            ACTION_STOP -> {
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf()
            }
        }
        return START_NOT_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun createChannel() {
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Konwersja e-booków",
            NotificationManager.IMPORTANCE_LOW,  // silent, no sound
        ).apply {
            description = "Postęp konwersji PDF/EPUB przez ReBook"
            setShowBadge(false)
        }
        notifManager.createNotificationChannel(channel)
    }

    private fun buildNotification(): Notification {
        // Tap notification → open app
        val tapIntent = PendingIntent.getActivity(
            this, 0,
            packageManager.getLaunchIntentForPackage(packageName),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle(currentTitle)
            .setContentText(currentMsg.ifBlank { "Trwa konwersja…" })
            .setProgress(100, currentProgress, currentProgress == 0)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setContentIntent(tapIntent)
            .build()
    }
}
