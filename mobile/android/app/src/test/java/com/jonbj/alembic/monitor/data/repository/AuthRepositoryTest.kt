package com.jonbj.alembic.monitor.data.repository

import com.jonbj.alembic.monitor.core.network.FakeMobileApi
import com.jonbj.alembic.monitor.core.network.FixedMobileApiProvider
import com.jonbj.alembic.monitor.core.network.ServerUrlPolicy
import com.jonbj.alembic.monitor.core.security.InMemorySessionVault
import kotlinx.coroutines.test.runTest
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import retrofit2.Response

class AuthRepositoryTest {

    @Test
    fun `login stores the normalized server URL in the encrypted session`() = runTest {
        val vault = InMemorySessionVault()
        val api = FakeMobileApi()
        val repository = repository(api, vault)

        val session = repository.login(
            serverUrl = "https://alembic.lan",
            username = "monitor",
            password = "secret",
            installationId = "ad08638e-3ed8-4ca8-a797-cb2f3afb3161",
            deviceName = "Pixel 9"
        ).getOrThrow()

        assertEquals("https://alembic.lan/api/mobile/v1/", session.baseUrl)
        assertEquals(session, vault.get())
    }

    @Test
    fun `logout purges local session even when server revocation fails`() = runTest {
        val vault = InMemorySessionVault()
        val api = FakeMobileApi()
        var purgeCount = 0
        val repository = repository(api, vault) {
            purgeCount += 1
            vault.clear()
        }
        repository.login(
            serverUrl = "https://alembic.lan",
            username = "monitor",
            password = "secret",
            installationId = "ad08638e-3ed8-4ca8-a797-cb2f3afb3161",
            deviceName = "Pixel 9"
        ).getOrThrow()
        api.logoutResponse = Response.error(503, "unavailable".toResponseBody())

        val result = repository.logout()

        assertTrue(result.isFailure)
        assertNull(vault.get())
        assertEquals(1, purgeCount)
    }

    private fun repository(
        api: FakeMobileApi,
        vault: InMemorySessionVault,
        clearLocalData: suspend () -> Unit = { vault.clear() }
    ) = AuthRepository(
        apiProvider = FixedMobileApiProvider(api),
        vault = vault,
        serverUrlPolicy = ServerUrlPolicy(allowDebugCleartext = false),
        appVersion = "1.0.0",
        clearLocalData = clearLocalData
    )
}
