package com.jonbj.alembic.monitor.data.repository

import com.jonbj.alembic.monitor.core.database.CacheKey
import com.jonbj.alembic.monitor.core.database.CacheStore
import com.jonbj.alembic.monitor.core.model.LoadState
import com.jonbj.alembic.monitor.core.model.Snapshot
import com.jonbj.alembic.monitor.core.network.MobileApi
import com.jonbj.alembic.monitor.core.network.dto.SnapshotResponse
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.json.Json

class StatusRepository(
    private val api: MobileApi,
    private val cache: CacheStore,
    private val json: Json,
    private val refresher: TokenRefresher
) {

    private val _snapshot = MutableStateFlow<LoadState<Snapshot>>(LoadState.Loading)
    val snapshot: StateFlow<LoadState<Snapshot>> = _snapshot.asStateFlow()

    suspend fun refresh(force: Boolean = false) {
        if (force || _snapshot.value !is LoadState.Success) {
            _snapshot.value = LoadState.Loading
        }

        val result = ApiCaller.execute(refresher) { api.snapshot() }

        result.fold(
            onSuccess = { dto ->
                cache.put(
                    CacheKey.SNAPSHOT,
                    dto,
                    SnapshotResponse.serializer(),
                    dto.asOf,
                    dto.dataAgeSeconds
                )
                _snapshot.value = successFromNetwork(dto.toDomain(), dto.dataAgeSeconds)
            },
            onFailure = { error ->
                val cached = cache.get(CacheKey.SNAPSHOT, SnapshotResponse.serializer())
                _snapshot.value = if (cached != null) {
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
