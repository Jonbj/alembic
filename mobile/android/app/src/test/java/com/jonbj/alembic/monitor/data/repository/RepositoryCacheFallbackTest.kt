package com.jonbj.alembic.monitor.data.repository

import com.jonbj.alembic.monitor.core.database.CacheKey
import com.jonbj.alembic.monitor.core.database.InMemoryCacheStore
import com.jonbj.alembic.monitor.core.model.DataSource
import com.jonbj.alembic.monitor.core.model.ContentMode
import com.jonbj.alembic.monitor.core.model.LoadState
import com.jonbj.alembic.monitor.core.network.FakeMobileApi
import com.jonbj.alembic.monitor.core.network.FixedMobileApiProvider
import com.jonbj.alembic.monitor.core.network.dto.OperationalDto
import com.jonbj.alembic.monitor.core.network.dto.PipelineComponentDto
import com.jonbj.alembic.monitor.core.network.dto.PortfolioDto
import com.jonbj.alembic.monitor.core.network.dto.SnapshotResponse
import kotlinx.coroutines.test.runTest
import kotlinx.datetime.Clock
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import retrofit2.Response

class RepositoryCacheFallbackTest {

    @Test
    fun `status repository falls back to cached snapshot when network fails`() = runTest {
        val api = FakeMobileApi()
        api.snapshotResponse = Response.error(503, "".toResponseBody())
        val cache = InMemoryCacheStore()
        val refresher = FakeTokenRefresher()

        val cachedDto = SnapshotResponse(
            contractVersion = 1,
            asOf = Clock.System.now(),
            dataAgeSeconds = 60,
            currency = "USD",
            minSupportedAppVersion = "1.0.0",
            latestAppVersion = "1.0.0",
            operational = OperationalDto(
                state = "paused",
                mode = "paper",
                marketPhase = "closed",
                pipelineExpected = false
            ),
            portfolio = PortfolioDto(nav = 98765.43, source = "alpaca_paper"),
            pipeline = mapOf("database" to PipelineComponentDto("not_expected", 0)),
            strategies = emptyList()
        )
        cache.put(CacheKey.SNAPSHOT, cachedDto, SnapshotResponse.serializer(), cachedDto.asOf, 60)

        val repository = StatusRepository(FixedMobileApiProvider(api), cache, refresher)
        repository.refresh(force = true)

        val state = repository.snapshot.value
        assertTrue(state is LoadState.Success)
        val success = state as LoadState.Success
        assertEquals(DataSource.CACHE, success.source)
        assertEquals(ContentMode.OFFLINE, success.mode)
        assertEquals(60, success.dataAgeSeconds)
        assertEquals(98765.43, success.data.portfolio.nav ?: 0.0, 0.001)
    }
}
