package com.jonbj.alembic.monitor.data.repository

import com.jonbj.alembic.monitor.core.database.InMemoryCacheStore
import com.jonbj.alembic.monitor.core.network.FakeMobileApi
import com.jonbj.alembic.monitor.core.network.FixedMobileApiProvider
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.delay
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Test

class RepositoryRefreshSerializationTest {

    @Test
    fun concurrentStatusRefreshesNeverOverlap() = runTest {
        val api = FakeMobileApi()
        val response = api.snapshot()
        var activeCalls = 0
        var maxActiveCalls = 0
        var totalCalls = 0
        api.snapshotHandler = {
            totalCalls += 1
            activeCalls += 1
            maxActiveCalls = maxOf(maxActiveCalls, activeCalls)
            delay(100)
            activeCalls -= 1
            response
        }
        val repository = StatusRepository(
            apiProvider = FixedMobileApiProvider(api),
            cache = InMemoryCacheStore(),
            refresher = FakeTokenRefresher()
        )

        List(3) { async { repository.refresh(force = true) } }.awaitAll()

        assertEquals(3, totalCalls)
        assertEquals(1, maxActiveCalls)
    }
}
