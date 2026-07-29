package com.jonbj.alembic.monitor.push

import android.content.Intent
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class DeepLinkCoordinator {
    private val _pendingEventId = MutableStateFlow<OpaqueEventId?>(null)
    val pendingEventId: StateFlow<OpaqueEventId?> = _pendingEventId.asStateFlow()

    fun accept(intent: Intent?): Boolean {
        if (intent?.action != ACTION_OPEN_EVENT) return false
        val eventId = OpaqueEventId.parse(
            intent.getStringExtra(EXTRA_EVENT_ID)
        )
            ?: return false
        _pendingEventId.value = eventId
        return true
    }

    fun consume(eventId: OpaqueEventId) {
        if (_pendingEventId.value == eventId) _pendingEventId.value = null
    }

    companion object {
        const val ACTION_OPEN_EVENT =
            "com.jonbj.alembic.monitor.action.OPEN_EVENT"
        const val EXTRA_EVENT_ID = "event_id"
    }
}
