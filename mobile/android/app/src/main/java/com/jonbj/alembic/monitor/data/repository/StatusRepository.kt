package com.jonbj.alembic.monitor.data.repository

import com.jonbj.alembic.monitor.core.database.CacheKey
import com.jonbj.alembic.monitor.core.database.CacheStore
import com.jonbj.alembic.monitor.core.model.LoadState
import com.jonbj.alembic.monitor.core.model.Snapshot
import com.jonbj.alembic.monitor.core.network.MobileApiProvider
import com.jonbj.alembic.monitor.core.network.dto.SnapshotResponse
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class StatusRepository(
    private val apiProvider: MobileApiProvider,
    private val cache: CacheStore,
    private val refresher: TokenRefresher
) {

    private val _snapshot = MutableStateFlow<LoadState<Snapshot>>(LoadState.Loading)
    val snapshot: StateFlow<LoadState<Snapshot>> = _snapshot.asStateFlow()

    suspend fun refresh(force: Boolean = false) {
        if (force || _snapshot.value !is LoadState.Success) {
            _snapshot.value = LoadState.Loading
        }

        val result = ApiCaller.execute(refresher) { apiProvider.current().snapshot() }

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
                _snapshot.value = failureState(
                    error,
                    cached?.data?.toDomain(),
                    cached?.dataAgeSeconds
                )
            }
        )
    }
}
