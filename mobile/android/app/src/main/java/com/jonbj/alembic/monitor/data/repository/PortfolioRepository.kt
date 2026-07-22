package com.jonbj.alembic.monitor.data.repository

import com.jonbj.alembic.monitor.core.database.CacheKey
import com.jonbj.alembic.monitor.core.database.CacheStore
import com.jonbj.alembic.monitor.core.model.LoadState
import com.jonbj.alembic.monitor.core.model.Positions
import com.jonbj.alembic.monitor.core.network.MobileApi
import com.jonbj.alembic.monitor.core.network.dto.PositionsResponse
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.json.Json

class PortfolioRepository(
    private val api: MobileApi,
    private val cache: CacheStore,
    private val json: Json,
    private val refresher: TokenRefresher
) {

    private val _positions = MutableStateFlow<LoadState<Positions>>(LoadState.Loading)
    val positions: StateFlow<LoadState<Positions>> = _positions.asStateFlow()

    suspend fun refresh(force: Boolean = false) {
        if (force || _positions.value !is LoadState.Success) {
            _positions.value = LoadState.Loading
        }

        val result = ApiCaller.execute(refresher) { api.positions() }

        result.fold(
            onSuccess = { dto ->
                cache.put(
                    CacheKey.POSITIONS,
                    dto,
                    PositionsResponse.serializer(),
                    dto.asOf,
                    dto.dataAgeSeconds
                )
                _positions.value = successFromNetwork(dto.toDomain(), dto.dataAgeSeconds)
            },
            onFailure = { error ->
                val cached = cache.get(CacheKey.POSITIONS, PositionsResponse.serializer())
                _positions.value = if (cached != null) {
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
