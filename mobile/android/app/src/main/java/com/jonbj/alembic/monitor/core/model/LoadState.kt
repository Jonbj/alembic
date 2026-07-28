package com.jonbj.alembic.monitor.core.model

sealed class LoadState<out T> {
    data object Loading : LoadState<Nothing>()
    data class Success<T>(
        val data: T,
        val source: DataSource,
        val dataAgeSeconds: Int,
        val mode: ContentMode = if (source == DataSource.NETWORK) {
            ContentMode.LIVE
        } else {
            ContentMode.OFFLINE
        }
    ) : LoadState<T>()

    data class Error<T>(
        val message: String,
        val cached: T? = null,
        val source: DataSource? = null,
        val dataAgeSeconds: Int? = null,
        val retryable: Boolean = true,
        val mode: ContentMode = ContentMode.UNAVAILABLE
    ) : LoadState<T>()
}

enum class DataSource {
    NETWORK,
    CACHE,
    FALLBACK_EMPTY
}

enum class ContentMode {
    LIVE,
    OFFLINE,
    STALE,
    INCOMPATIBLE,
    UNAUTHENTICATED,
    UNAVAILABLE
}
