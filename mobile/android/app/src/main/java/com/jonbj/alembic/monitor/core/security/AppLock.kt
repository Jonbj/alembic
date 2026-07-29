package com.jonbj.alembic.monitor.core.security

import android.os.SystemClock
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.launchIn
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob

interface AppLock {
    val isLocked: StateFlow<Boolean>
    fun onAppForeground()
    fun onAppBackground()
    fun lock()
    fun unlock()
}

class TimeoutAppLock(
    private val sessionVault: SessionVault,
    private val timeoutMillis: Long = DEFAULT_TIMEOUT_MS,
    private val clock: () -> Long = { SystemClock.elapsedRealtime() },
    dispatcher: kotlinx.coroutines.CoroutineDispatcher = Dispatchers.Main.immediate
) : AppLock {

    private val scope = CoroutineScope(SupervisorJob() + dispatcher)
    private val _isLocked = MutableStateFlow(sessionVault.sessionFlow.value != null)
    override val isLocked: StateFlow<Boolean> = _isLocked.asStateFlow()

    private var backgroundAt: Long? = null
    private var hasSession = sessionVault.sessionFlow.value != null
    private var forceLocked = false

    init {
        sessionVault.sessionFlow
            .onEach { session ->
                val alreadyAuthenticated = hasSession
                hasSession = session != null
                if (session == null) {
                    _isLocked.value = forceLocked
                } else if (!alreadyAuthenticated) {
                    // The interactive server login is sufficient for this first entry.
                    _isLocked.value = forceLocked
                }
            }
            .launchIn(scope)
    }

    override fun onAppForeground() {
        val wasBackgroundAt = backgroundAt
        backgroundAt = null
        if (!hasSession) {
            _isLocked.value = false
            return
        }
        if (wasBackgroundAt != null) {
            val elapsed = clock() - wasBackgroundAt
            if (elapsed >= timeoutMillis) {
                _isLocked.value = true
            }
        }
    }

    override fun onAppBackground() {
        if (hasSession) {
            backgroundAt = clock()
        }
    }

    override fun lock() {
        forceLocked = true
        _isLocked.value = true
    }

    override fun unlock() {
        forceLocked = false
        _isLocked.value = false
        backgroundAt = null
    }

    companion object {
        private const val DEFAULT_TIMEOUT_MS = 5L * 60L * 1000L
    }
}
