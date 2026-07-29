package com.jonbj.alembic.monitor.data.repository

import com.jonbj.alembic.monitor.core.database.InMemoryCacheStore
import com.jonbj.alembic.monitor.core.model.LoadState
import com.jonbj.alembic.monitor.core.network.FakeMobileApi
import com.jonbj.alembic.monitor.core.network.FixedMobileApiProvider
import com.jonbj.alembic.monitor.core.network.dto.EventItemDto
import com.jonbj.alembic.monitor.core.network.dto.EventsResponse
import kotlinx.coroutines.test.runTest
import kotlinx.datetime.Clock
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test
import retrofit2.Response

class EventsPaginationTest {

    @Test
    fun `next page uses opaque cursor and de-duplicates events`() = runTest {
        val api = FakeMobileApi()
        val cursors = mutableListOf<String?>()
        api.eventsHandler = { _, days, cursor, _ ->
            assertEquals(7, days)
            cursors += cursor
            Response.success(
                page(
                    ids = if (cursor == null) listOf("one", "two") else listOf("two", "three"),
                    nextCursor = if (cursor == null) "opaque:cursor" else null
                )
            )
        }
        val repository = EventsRepository(
            FixedMobileApiProvider(api),
            InMemoryCacheStore(),
            FakeTokenRefresher()
        )

        repository.refresh(force = true)
        repository.loadNext()

        val success = repository.events.value as LoadState.Success
        assertEquals(listOf(null, "opaque:cursor"), cursors)
        assertEquals(listOf("one", "two", "three"), success.data.items.map { it.id })
        assertFalse(success.data.nextCursor != null)
    }

    @Test
    fun `event look-up walks at most the selected thirty-day window`() = runTest {
        val api = FakeMobileApi()
        val requestedDays = mutableListOf<Int>()
        api.eventsHandler = { _, days, cursor, _ ->
            requestedDays += days
            Response.success(
                page(
                    ids = if (cursor == null) listOf("one") else listOf("target"),
                    nextCursor = if (cursor == null) "next" else null
                )
            )
        }
        val repository = EventsRepository(
            FixedMobileApiProvider(api),
            InMemoryCacheStore(),
            FakeTokenRefresher()
        )

        val event = repository.findById("target")

        assertEquals("target", event?.id)
        assertEquals(listOf(30, 30), requestedDays)
    }

    private fun page(ids: List<String>, nextCursor: String?): EventsResponse {
        val now = Clock.System.now()
        return EventsResponse(
            contractVersion = 1,
            asOf = now,
            dataAgeSeconds = 0,
            currency = "USD",
            minSupportedAppVersion = "1.0.0",
            latestAppVersion = "1.0.0",
            items = ids.map {
                EventItemDto(
                    id = it,
                    kind = "alert_incident",
                    category = "system",
                    severity = "warning",
                    status = "open",
                    occurredAt = now,
                    updatedAt = now,
                    title = "Evento $it"
                )
            },
            nextCursor = nextCursor
        )
    }
}
