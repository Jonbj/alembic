package com.jonbj.alembic.monitor.push

import android.app.Service
import android.content.Intent
import android.os.IBinder

/**
 * The backend already owns alert incidents and FCM delivery. MOB-07 replaces this
 * Android-only placeholder with FirebaseMessagingService while preserving the
 * opaque, privacy-safe payload boundary.
 */
class AlembicMessagingService : Service() {

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // Authenticated event detail is always fetched from Alembic, never from FCM payload.
        return START_NOT_STICKY
    }
}
