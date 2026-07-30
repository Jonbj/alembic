package com.jonbj.alembic.monitor.data.repository

import com.jonbj.alembic.monitor.core.database.InMemoryCacheStore
import com.jonbj.alembic.monitor.core.model.LoadState
import com.jonbj.alembic.monitor.core.network.FakeMobileApi
import com.jonbj.alembic.monitor.core.network.FixedMobileApiProvider
import com.jonbj.alembic.monitor.core.network.dto.EventItemDto
import com.jonbj.alembic.monitor.core.network.dto.EventsResponse
import kotlinx.coroutines.test.runTest
import kotlinx.datetime.Clock
import okhttp3.ResponseBody.Companion.toResponseBody
import com.jonbj.alembic.monitor.push.OpaqueEventId
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
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

        val event = repository.findById(requireNotNull(OpaqueEventId.parse("target")))

        assertEquals("target", event?.id)
        assertEquals(listOf(30, 30), requestedDays)
    }

    @Test
    fun `empty event window is a successful page`() = runTest {
        val api = FakeMobileApi().apply {
            eventsHandler = { _, _, _, _ ->
                Response.success(page(ids = emptyList(), nextCursor = null))
            }
        }
        val repository = EventsRepository(
            FixedMobileApiProvider(api),
            InMemoryCacheStore(),
            FakeTokenRefresher()
        )

        repository.refresh(force = true)

        val success = repository.events.value as LoadState.Success
        assertTrue(success.data.items.isEmpty())
        assertEquals(null, success.data.nextCursor)
    }

    @Test
    fun `failed next page preserves the already loaded events`() = runTest {
        val api = FakeMobileApi().apply {
            eventsHandler = { _, _, cursor, _ ->
                if (cursor == null) {
                    Response.success(page(listOf("one"), "next"))
                } else {
                    Response.error(503, "offline".toResponseBody())
                }
            }
        }
        val repository = EventsRepository(
            FixedMobileApiProvider(api),
            InMemoryCacheStore(),
            FakeTokenRefresher()
        )

        repository.refresh(force = true)
        repository.loadNext()

        val success = repository.events.value as LoadState.Success
        assertEquals(listOf("one"), success.data.items.map { it.id })
        assertEquals("next", success.data.nextCursor)
    }

    @Test
    fun `missing notification event returns a safe absent result`() = runTest {
        val api = FakeMobileApi().apply {
            eventsHandler = { _, days, _, _ ->
                assertEquals(30, days)
                Response.success(page(listOf("other"), nextCursor = null))
            }
        }
        val repository = EventsRepository(
            FixedMobileApiProvider(api),
            InMemoryCacheStore(),
            FakeTokenRefresher()
        )

        assertNull(
            repository.findById(requireNotNull(OpaqueEventId.parse("missing")))
        )
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
