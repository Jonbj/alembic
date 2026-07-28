package com.jonbj.alembic.monitor.core.network

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ServerUrlPolicyTest {

    private val releasePolicy = ServerUrlPolicy(allowDebugCleartext = false)
    private val debugPolicy = ServerUrlPolicy(allowDebugCleartext = true)

    @Test
    fun `release normalizes an HTTPS server origin to the mobile v1 base path`() {
        assertEquals(
            "https://alembic.lan/api/mobile/v1/",
            releasePolicy.normalize("  https://alembic.lan  ").getOrThrow()
        )
    }

    @Test
    fun `release accepts the canonical API path without duplicating it`() {
        assertEquals(
            "https://alembic.lan:8443/api/mobile/v1/",
            releasePolicy.normalize("https://alembic.lan:8443/api/mobile/v1").getOrThrow()
        )
    }

    @Test
    fun `release rejects cleartext credentials query fragments and unexpected paths`() {
        listOf(
            "http://alembic.lan",
            "https://user:secret@alembic.lan",
            "https://alembic.lan?token=secret",
            "https://alembic.lan/#fragment",
            "https://alembic.lan/admin"
        ).forEach { input ->
            assertTrue("$input should be rejected", releasePolicy.normalize(input).isFailure)
        }
    }

    @Test
    fun `debug cleartext is restricted to explicit emulator loopback hosts`() {
        assertEquals(
            "http://10.0.2.2:8001/api/mobile/v1/",
            debugPolicy.normalize("http://10.0.2.2:8001").getOrThrow()
        )
        assertTrue(debugPolicy.normalize("http://192.168.1.10:8001").isFailure)
        assertTrue(debugPolicy.normalize("http://alembic.lan:8001").isFailure)
    }
}
