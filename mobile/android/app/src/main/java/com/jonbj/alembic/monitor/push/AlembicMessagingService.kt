package com.jonbj.alembic.monitor.push

import android.app.Service
import android.content.Intent
import android.os.IBinder

/**
 * FCM delivery is external-only in the MVP. The backend owns alert incidents and
 * pushes opaque routing data through Firebase Cloud Messaging. This stub keeps the
 * manifest entry and the delivery port in place; a future build can swap in the
 * real FirebaseMessagingService without changing incident semantics.
 */
class AlembicMessagingService : Service() {

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // Authenticated event detail is always fetched from Alembic, never from FCM payload.
        return START_NOT_STICKY
    }
}
