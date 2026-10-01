package app.tradingagents.android

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder
import android.os.PowerManager

/**
 * Keeps the process and the CPU awake while an analysis runs, so it finishes
 * with the screen off or the app in the background. It watches the engine and
 * stops itself when the run ends, whether or not the activity is still there.
 */
class RunService : Service() {
    private lateinit var thread: HandlerThread
    private lateinit var handler: Handler
    private var wakeLock: PowerManager.WakeLock? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        createChannel()
        val notification = notification(getString(R.string.run_in_progress), ongoing = true)
        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(ONGOING_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            startForeground(ONGOING_ID, notification)
        }
        wakeLock = getSystemService(PowerManager::class.java)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "TradingAgents:run")
            .apply { acquire(MAX_RUN_MILLIS) }

        thread = HandlerThread("run-watch").apply { start() }
        handler = Handler(thread.looper)
        handler.postDelayed(::check, POLL_MILLIS)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_NOT_STICKY

    private fun check() {
        if (Engine.isRunning()) {
            handler.postDelayed(::check, POLL_MILLIS)
            return
        }
        getSystemService(NotificationManager::class.java)
            .notify(FINISHED_ID, notification(getString(R.string.run_finished), ongoing = false))
        stopSelf()
    }

    override fun onDestroy() {
        thread.quitSafely()
        wakeLock?.takeIf { it.isHeld }?.release()
        super.onDestroy()
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT >= 26) {
            getSystemService(NotificationManager::class.java).createNotificationChannel(
                NotificationChannel(CHANNEL, getString(R.string.channel_name), NotificationManager.IMPORTANCE_LOW)
            )
        }
    }

    private fun notification(text: String, ongoing: Boolean): Notification {
        val open = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE
        )
        val builder =
            if (Build.VERSION.SDK_INT >= 26) Notification.Builder(this, CHANNEL)
            else @Suppress("DEPRECATION") Notification.Builder(this)
        return builder
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(text)
            .setContentIntent(open)
            .setOngoing(ongoing)
            .setAutoCancel(!ongoing)
            .build()
    }

    companion object {
        private const val CHANNEL = "runs"
        private const val ONGOING_ID = 1
        private const val FINISHED_ID = 2
        private const val POLL_MILLIS = 5_000L
        // Longer than any run should take; the lock is released when the run ends.
        private const val MAX_RUN_MILLIS = 3 * 60 * 60 * 1000L

        fun start(context: Context) {
            val intent = Intent(context, RunService::class.java)
            if (Build.VERSION.SDK_INT >= 26) context.startForegroundService(intent) else context.startService(intent)
        }
    }
}
