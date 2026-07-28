package com.jonbj.alembic.monitor.data.repository

import com.jonbj.alembic.monitor.core.database.CacheKey
import com.jonbj.alembic.monitor.core.database.CacheStore
import com.jonbj.alembic.monitor.core.model.EventsPage
import com.jonbj.alembic.monitor.core.model.LoadState
import com.jonbj.alembic.monitor.core.network.MobileApiProvider
import com.jonbj.alembic.monitor.core.network.dto.EventsResponse
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class EventsRepository(
    private val apiProvider: MobileApiProvider,
    private val cache: CacheStore,
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
        val result = ApiCaller.execute(refresher) {
            apiProvider.current().events(category, days, cursor)
        }

        result.fold(
            onSuccess = { dto ->
                cache.put(
                    cacheKey,
                    dto,
                    EventsResponse.serializer(),
                    dto.asOf,
                    dto.dataAgeSeconds
                )
                _events.value = LoadState.Success(
                    data = EventsPage(
                        contractVersion = dto.contractVersion,
                        asOf = dto.asOf,
                        items = dto.items.toEventsDomain(),
                        nextCursor = dto.nextCursor
                    ),
                    source = com.jonbj.alembic.monitor.core.model.DataSource.NETWORK,
                    dataAgeSeconds = dto.dataAgeSeconds
                )
            },
            onFailure = { error ->
                val cached = cache.get(cacheKey, EventsResponse.serializer())
                val cachedDomain = cached?.data?.let {
                    EventsPage(
                        contractVersion = it.contractVersion,
                        asOf = it.asOf,
                        items = it.items.toEventsDomain(),
                        nextCursor = it.nextCursor
                    )
                }
                _events.value = failureState(error, cachedDomain, cached?.dataAgeSeconds)
            }
        )
    }
}
