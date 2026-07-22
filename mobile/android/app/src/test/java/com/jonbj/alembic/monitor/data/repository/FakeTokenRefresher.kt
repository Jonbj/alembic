package com.jonbj.alembic.monitor.data.repository

class FakeTokenRefresher(private val succeed: Boolean = true) : TokenRefresher {
    var refreshCount = 0
        private set

    override suspend fun refreshAccessToken(): Result<Unit> {
        refreshCount++
        return if (succeed) Result.success(Unit) else Result.failure(RuntimeException("Refresh failed"))
    }
}
