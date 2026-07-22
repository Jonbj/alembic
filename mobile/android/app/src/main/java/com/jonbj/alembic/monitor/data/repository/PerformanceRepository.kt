package com.jonbj.alembic.monitor.data.repository

import com.jonbj.alembic.monitor.core.database.CacheKey
import com.jonbj.alembic.monitor.core.database.CacheStore
import com.jonbj.alembic.monitor.core.model.LoadState
import com.jonbj.alembic.monitor.core.model.Performance
import com.jonbj.alembic.monitor.core.network.MobileApi
import com.jonbj.alembic.monitor.core.network.dto.PerformanceResponse
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.json.Json

class PerformanceRepository(
    private val api: MobileApi,
    private val cache: CacheStore,
    private val json: Json,
    private val refresher: TokenRefresher
) {

    private val _performance = MutableStateFlow<LoadState<Performance>>(LoadState.Loading)
    val performance: StateFlow<LoadState<Performance>> = _performance.asStateFlow()

    suspend fun refresh(period: String, force: Boolean = false) {
        if (force || _performance.value !is LoadState.Success) {
            _performance.value = LoadState.Loading
        }

        val cacheKey = "${CacheKey.PERFORMANCE}_$period"
        val result = ApiCaller.execute(refresher) { api.performance(period) }

        result.fold(
            onSuccess = { dto ->
                cache.put(cacheKey, dto, PerformanceResponse.serializer(), dto.asOf, dto.dataAgeSeconds)
                _performance.value = successFromNetwork(dto.toDomain(), dto.dataAgeSeconds)
            },
            onFailure = { error ->
                val cached = cache.get(cacheKey, PerformanceResponse.serializer())
                _performance.value = if (cached != null) {
                    successFromCache(cached.data.toDomain(), cached.dataAgeSeconds)
                } else {
                    LoadState.Error(
                        message = error.message ?: "Errore imprevisto",
                        retryable = (error as? com.jonbj.alembic.monitor.core.model.MobileError)?.retryable
                            ?: true
                    )
                }
            }
        )
    }
}
