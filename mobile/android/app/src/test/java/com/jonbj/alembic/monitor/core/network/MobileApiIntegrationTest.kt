package com.jonbj.alembic.monitor.core.network

import com.jonbj.alembic.monitor.core.security.InMemorySessionVault
import com.jonbj.alembic.monitor.data.repository.ApiCaller
import com.jonbj.alembic.monitor.data.repository.AuthRepository
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test

class MobileApiIntegrationTest {
    private lateinit var server: MockWebServer

    @Before
    fun startServer() {
        server = MockWebServer()
        server.dispatcher = MobileDispatcher()
        server.start()
    }

    @After
    fun stopServer() {
        server.shutdown()
    }

    @Test
    fun `real client logs in refreshes once and replays the protected request`() = runTest {
        val vault = InMemorySessionVault()
        val json = Json { ignoreUnknownKeys = true }
        val baseUrl = server.url("/api/mobile/v1/").toString()
        val provider = SessionMobileApiProvider(baseUrl, vault, json)
        val auth = AuthRepository(
            apiProvider = provider,
            vault = vault,
            serverUrlPolicy = ServerUrlPolicy(allowDebugCleartext = true),
            appVersion = "1.0.0",
            clearLocalData = { vault.clear() }
        )
        auth.login(
            serverUrl = baseUrl,
            username = "monitor",
            password = "secret",
            installationId = "ad08638e-3ed8-4ca8-a797-cb2f3afb3161",
            deviceName = "Pixel 9"
        ).getOrThrow()

        val snapshot = ApiCaller.execute(auth) { provider.current().snapshot() }.getOrThrow()

        assertEquals(1, snapshot.contractVersion)
        assertEquals("access-new", vault.get()!!.accessToken)
        val dispatcher = server.dispatcher as MobileDispatcher
        assertEquals(1, dispatcher.refreshRequests)
        assertEquals(2, dispatcher.snapshotRequests)
    }

    private class MobileDispatcher : Dispatcher() {
        var refreshRequests = 0
        var snapshotRequests = 0

        override fun dispatch(request: RecordedRequest): MockResponse = when (request.path) {
            "/api/mobile/v1/auth/login" -> json(LOGIN)
            "/api/mobile/v1/auth/refresh" -> {
                refreshRequests += 1
                json(REFRESH)
            }
            "/api/mobile/v1/snapshot" -> {
                snapshotRequests += 1
                if (request.getHeader("Authorization") == "Bearer access-new") {
                    json(SNAPSHOT)
                } else {
                    MockResponse().setResponseCode(401)
                }
            }
            else -> MockResponse().setResponseCode(404)
        }

        private fun json(body: String) = MockResponse()
            .setResponseCode(200)
            .setHeader("Content-Type", "application/json")
            .setBody(body)
    }

    companion object {
        private val LOGIN = """
            {
              "access_token":"access-old","token_type":"bearer","expires_in":1,
              "refresh_token":"refresh-old",
              "refresh_expires_at":"2026-08-28T10:00:00Z",
              "user":{"id":"user-1","username":"monitor"},"device_id":"device-1"
            }
        """.trimIndent()

        private val REFRESH = """
            {
              "access_token":"access-new","token_type":"bearer","expires_in":900,
              "refresh_token":"refresh-new",
              "refresh_expires_at":"2026-08-28T10:00:00Z",
              "user":{"id":"user-1","username":"monitor"},"device_id":"device-1"
            }
        """.trimIndent()

        private val SNAPSHOT = """
            {
              "contract_version":1,"as_of":"2026-07-28T10:00:00Z",
              "data_age_seconds":5,"currency":"USD",
              "min_supported_app_version":"1.0.0","latest_app_version":"1.0.0",
              "operational":{
                "state":"operational","mode":"paper","market_phase":"open",
                "pipeline_expected":true,"active_incident_count":0
              },
              "portfolio":{"nav":100000.0,"open_positions":0,"source":"alpaca_paper"},
              "pipeline":{"database":{"status":"fresh","age_seconds":0}},
              "strategies":[],"degradations":[]
            }
        """.trimIndent()
    }
}
