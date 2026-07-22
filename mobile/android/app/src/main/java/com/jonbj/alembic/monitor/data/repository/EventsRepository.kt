package com.jonbj.alembic.monitor.data.repository

import com.jonbj.alembic.monitor.core.database.CacheKey
import com.jonbj.alembic.monitor.core.database.CacheStore
import com.jonbj.alembic.monitor.core.model.EventsPage
import com.jonbj.alembic.monitor.core.model.LoadState
import com.jonbj.alembic.monitor.core.network.MobileApi
import com.jonbj.alembic.monitor.core.network.dto.EventsResponse
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.json.Json

class EventsRepository(
    private val api: MobileApi,
    private val cache: CacheStore,
    private val json: Json,
    private val refresher: TokenRefresher
) {

    private val _events = MutableStateFlow<LoadState<EventsPage>>(LoadState.Loading)
    val events: StateFlow<LoadState<EventsPage>> = _events.asStateFlow()

    suspend fun refresh(
        category: String = "all",
        days: Int = 7,
        cursor: String? = null,
        force: Boolean = false
    ) {
        if (force || _events.value !is LoadState.Success) {
            _events.value = LoadState.Loading
        }

        val cacheKey = "${CacheKey.EVENTS}_$category"
        val result = ApiCaller.execute(refresher) { api.events(category, days, cursor) }

        result.fold(
            onSuccess = { dto ->
                cache.put(cacheKey, dto, EventsResponse.serializer(), dto.asOf, 0)
                _events.value = LoadState.Success(
                    data = EventsPage(
                        contractVersion = dto.contractVersion,
                        asOf = dto.asOf,
                        items = dto.items.toEventsDomain(),
                        nextCursor = dto.nextCursor
                    ),
                    source = com.jonbj.alembic.monitor.core.model.DataSource.NETWORK,
                    dataAgeSeconds = 0
                )
            },
            onFailure = { error ->
                val cached = cache.get(cacheKey, EventsResponse.serializer())
                _events.value = if (cached != null) {
                    LoadState.Success(
                        data = EventsPage(
                            contractVersion = cached.data.contractVersion,
                            asOf = cached.data.asOf,
                            items = cached.data.items.toEventsDomain(),
                            nextCursor = cached.data.nextCursor
                        ),
                        source = com.jonbj.alembic.monitor.core.model.DataSource.CACHE,
                        dataAgeSeconds = cached.dataAgeSeconds
                    )
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
