package com.jonbj.alembic.monitor.core.security

import com.jonbj.alembic.monitor.core.model.Session
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class InMemorySessionVault(initial: Session? = null) : SessionVault {

    private val _sessionFlow = MutableStateFlow(initial)
    override val sessionFlow: StateFlow<Session?> = _sessionFlow.asStateFlow()

    override suspend fun save(session: Session) {
        _sessionFlow.value = session
    }

    override suspend fun get(): Session? = _sessionFlow.value

    override fun getBlocking(): Session? = _sessionFlow.value

    override suspend fun clear() {
        _sessionFlow.value = null
    }
}
