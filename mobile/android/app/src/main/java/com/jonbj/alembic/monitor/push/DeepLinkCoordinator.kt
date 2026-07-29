package com.jonbj.alembic.monitor.push

import android.content.Intent
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class DeepLinkCoordinator {
    private val _pendingEventId = MutableStateFlow<String?>(null)
    val pendingEventId: StateFlow<String?> = _pendingEventId.asStateFlow()

    fun accept(intent: Intent?): Boolean {
        if (intent?.action != ACTION_OPEN_EVENT) return false
        val eventId = intent.getStringExtra(EXTRA_EVENT_ID)
            ?.takeIf { EVENT_ID.matches(it) }
            ?: return false
        _pendingEventId.value = eventId
        return true
    }

    fun consume(eventId: String) {
        if (_pendingEventId.value == eventId) _pendingEventId.value = null
    }

    companion object {
        const val ACTION_OPEN_EVENT =
            "com.jonbj.alembic.monitor.action.OPEN_EVENT"
        const val EXTRA_EVENT_ID = "event_id"
        private val EVENT_ID = Regex("^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    }
}
