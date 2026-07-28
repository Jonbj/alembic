package com.jonbj.alembic.monitor.data.repository

import com.jonbj.alembic.monitor.core.database.CacheKey
import com.jonbj.alembic.monitor.core.database.CacheStore
import com.jonbj.alembic.monitor.core.model.LoadState
import com.jonbj.alembic.monitor.core.model.Positions
import com.jonbj.alembic.monitor.core.network.MobileApiProvider
import com.jonbj.alembic.monitor.core.network.dto.PositionsResponse
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class PortfolioRepository(
    private val apiProvider: MobileApiProvider,
    private val cache: CacheStore,
    private val refresher: TokenRefresher
) {

    private val _positions = MutableStateFlow<LoadState<Positions>>(LoadState.Loading)
    val positions: StateFlow<LoadState<Positions>> = _positions.asStateFlow()

    suspend fun refresh(force: Boolean = false) {
        if (force || _positions.value !is LoadState.Success) {
            _positions.value = LoadState.Loading
        }

        val result = ApiCaller.execute(refresher) { apiProvider.current().positions() }

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
                _positions.value = failureState(
                    error,
                    cached?.data?.toDomain(),
                    cached?.dataAgeSeconds
                )
            }
        )
    }
}
