package com.jonbj.alembic.monitor.data.repository

import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.test.runTest
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import retrofit2.Response

class ApiCallerConcurrencyTest {

    @Test
    fun `concurrent unauthorized calls rotate a failed access token only once`() = runTest {
        val refresher = RotatingRefresher()

        val results = coroutineScope {
            List(20) {
                async {
                    ApiCaller.execute(refresher) {
                        if (refresher.currentAccessToken() == "access-old") {
                            Response.error(401, "".toResponseBody())
                        } else {
                            Response.success("ok")
                        }
                    }
                }
            }.awaitAll()
        }

        assertTrue(results.all { it.getOrNull() == "ok" })
        assertEquals(1, refresher.rotations)
    }

    private class RotatingRefresher : TokenRefresher {
        private val mutex = Mutex()
        private var accessToken = "access-old"
        var rotations = 0
            private set

        override fun currentAccessToken(): String = accessToken

        override suspend fun refreshAccessToken(failedAccessToken: String?): Result<Unit> =
            mutex.withLock {
                if (accessToken != failedAccessToken) {
                    return@withLock Result.success(Unit)
                }
                delay(10)
                rotations += 1
                accessToken = "access-new"
                Result.success(Unit)
            }

        override suspend fun invalidateSession() = Unit
    }
}
