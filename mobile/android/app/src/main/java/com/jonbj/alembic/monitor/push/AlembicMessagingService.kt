package com.jonbj.alembic.monitor.push

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import com.jonbj.alembic.monitor.MonitorApplication
import com.jonbj.alembic.monitor.R
import com.jonbj.alembic.monitor.app.MainActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

class AlembicMessagingService : FirebaseMessagingService() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onRegistered(installationId: String) {
        val coordinator = (application as MonitorApplication).container.pushCoordinator
        scope.launch { coordinator.onRegistered(installationId) }
    }

    override fun onUnregistered(installationId: String) {
        // Server registration is disabled by the permission/logout path. The
        // identifier is intentionally never logged.
    }

    override fun onMessageReceived(message: RemoteMessage) {
        val payload = PushPayload.parse(message.data) ?: return
        val deduplicator = NotificationDeduplicator(
            SharedPreferencesDeliveryFingerprintStore(this)
        )
        if (!deduplicator.shouldNotify(payload)) return
        createChannel()
        showGenericNotification(payload)
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val channel = NotificationChannel(
            CHANNEL_ID,
            getString(R.string.notification_channel_name),
            NotificationManager.IMPORTANCE_HIGH
        ).apply {
            description = getString(R.string.notification_channel_description)
            lockscreenVisibility = Notification.VISIBILITY_PRIVATE
        }
        manager.createNotificationChannel(channel)
    }

    private fun showGenericNotification(payload: PushPayload) {
        val openIntent = Intent(this, MainActivity::class.java).apply {
            action = DeepLinkCoordinator.ACTION_OPEN_EVENT
            putExtra(DeepLinkCoordinator.EXTRA_EVENT_ID, payload.eventId.value)
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pendingIntent = PendingIntent.getActivity(
            this,
            payload.eventId.value.hashCode(),
            openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val title = getString(R.string.notification_generic_title)
        val body = getString(
            if (
                payload.transition == PushTransition.RECOVERED ||
                payload.transition == PushTransition.CLOSED
            ) {
                R.string.notification_recovered_body
            } else {
                R.string.notification_attention_body
            }
        )
        val publicNotification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(getString(R.string.notification_private_body))
            .build()
        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(title)
            .setContentText(body)
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setVisibility(NotificationCompat.VISIBILITY_PRIVATE)
            .setPublicVersion(publicNotification)
            .build()
        try {
            NotificationManagerCompat.from(this)
                .notify(payload.eventId.value.hashCode(), notification)
        } catch (_: SecurityException) {
            // Permission denial must never impact the monitoring UI.
        }
    }

    private companion object {
        const val CHANNEL_ID = "alembic_monitoring_alerts"
    }
}
