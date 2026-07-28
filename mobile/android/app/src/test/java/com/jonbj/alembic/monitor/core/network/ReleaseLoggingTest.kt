package com.jonbj.alembic.monitor.core.network

import com.jonbj.alembic.monitor.core.security.InMemorySessionVault
import okhttp3.logging.HttpLoggingInterceptor
import org.junit.Assert.assertTrue
import org.junit.Test

class ReleaseLoggingTest {

    @Test
    fun `release client has no HTTP logging interceptor`() {
        val client = MobileApiClient.createHttpClient(
            sessionVault = InMemorySessionVault(),
            enableDebugLogging = false
        )

        assertTrue(client.interceptors.none { it is HttpLoggingInterceptor })
        assertTrue(client.networkInterceptors.none { it is HttpLoggingInterceptor })
    }
}
