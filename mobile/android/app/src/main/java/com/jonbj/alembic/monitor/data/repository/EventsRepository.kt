package com.jonbj.alembic.monitor.data.repository

import com.jonbj.alembic.monitor.core.database.CacheKey
import com.jonbj.alembic.monitor.core.database.CacheStore
import com.jonbj.alembic.monitor.core.model.DataSource
import com.jonbj.alembic.monitor.core.model.EventItem
import com.jonbj.alembic.monitor.core.model.EventsPage
import com.jonbj.alembic.monitor.core.model.LoadState
import com.jonbj.alembic.monitor.core.network.MobileApiProvider
import com.jonbj.alembic.monitor.core.network.dto.EventsResponse
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

class EventsRepository(
    private val apiProvider: MobileApiProvider,
    private val cache: CacheStore,
    private val refresher: TokenRefresher
) {

    private val requestMutex = Mutex()
    private val _events = MutableStateFlow<LoadState<EventsPage>>(LoadState.Loading)
    val events: StateFlow<LoadState<EventsPage>> = _events.asStateFlow()

    private var currentCategory = DEFAULT_CATEGORY
    private var currentDays = DEFAULT_DAYS
    private var currentDto: EventsResponse? = null

    suspend fun refresh(
        category: String = DEFAULT_CATEGORY,
        days: Int = DEFAULT_DAYS,
        cursor: String? = null,
        force: Boolean = false
    ) = requestMutex.withLock {
        val safeDays = days.coerceIn(1, MAX_DAYS)
        if (cursor != null) {
            loadPage(category, safeDays, cursor, append = true)
            return@withLock
        }
        currentCategory = category
        currentDays = safeDays
        currentDto = null
        if (force || _events.value !is LoadState.Success) {
            _events.value = LoadState.Loading
        }
        loadPage(category, safeDays, cursor = null, append = false)
    }

    suspend fun loadNext() = requestMutex.withLock {
        val cursor = currentDto?.nextCursor ?: return@withLock
        loadPage(currentCategory, currentDays, cursor, append = true)
    }

    /**
     * Notification detail lookup always comes from the authenticated API. It
     * searches the complete supported window and never trusts notification text.
     */
    suspend fun findById(eventId: String): EventItem? = requestMutex.withLock {
        var cursor: String? = null
        var pageCount = 0
        do {
            val result = ApiCaller.execute(refresher) {
                apiProvider.current().events(
                    category = DEFAULT_CATEGORY,
                    days = MAX_DAYS,
                    cursor = cursor
                )
            }
            val page = result.getOrNull() ?: return@withLock null
            page.items.firstOrNull { it.id == eventId }?.let {
                return@withLock it.toDomain()
            }
            cursor = page.nextCursor
            pageCount += 1
        } while (cursor != null && pageCount < MAX_DETAIL_PAGES)
        null
    }

    private suspend fun loadPage(
        category: String,
        days: Int,
        cursor: String?,
        append: Boolean
    ) {
        val cacheKey = cacheKey(category, days)
        val result = ApiCaller.execute(refresher) {
            apiProvider.current().events(category, days, cursor)
        }

        result.fold(
            onSuccess = { incoming ->
                val merged = if (append) merge(currentDto, incoming) else incoming
                currentDto = merged
                cache.put(
                    cacheKey,
                    merged,
                    EventsResponse.serializer(),
                    merged.asOf,
                    merged.dataAgeSeconds
                )
                _events.value = LoadState.Success(
                    data = merged.toDomain(),
                    source = DataSource.NETWORK,
                    dataAgeSeconds = merged.dataAgeSeconds
                )
            },
            onFailure = { error ->
                val existing = currentDto
                if (append && existing != null) {
                    _events.value = LoadState.Success(
                        data = existing.toDomain(),
                        source = DataSource.NETWORK,
                        dataAgeSeconds = existing.dataAgeSeconds
                    )
                    return@fold
                }
                val cached = cache.get(cacheKey, EventsResponse.serializer())
                _events.value = failureState(
                    error,
                    cached?.data?.toDomain(),
                    cached?.dataAgeSeconds
                )
            }
        )
    }

    private fun merge(current: EventsResponse?, incoming: EventsResponse): EventsResponse {
        if (current == null) return incoming
        val mergedItems = (current.items + incoming.items)
            .distinctBy { it.id }
        return incoming.copy(items = mergedItems)
    }

    private fun EventsResponse.toDomain() = EventsPage(
        contractVersion = contractVersion,
        asOf = asOf,
        items = items.toEventsDomain(),
        nextCursor = nextCursor
    )

    private fun cacheKey(category: String, days: Int) =
        "${CacheKey.EVENTS}_${category}_$days"

    companion object {
        const val DEFAULT_DAYS = 7
        const val MAX_DAYS = 30
        private const val DEFAULT_CATEGORY = "all"
        private const val MAX_DETAIL_PAGES = 100
    }
}
