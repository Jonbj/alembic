package com.jonbj.alembic.monitor.push

import com.jonbj.alembic.monitor.core.model.Session
import com.jonbj.alembic.monitor.core.model.UserInfo
import com.jonbj.alembic.monitor.core.network.FakeMobileApi
import com.jonbj.alembic.monitor.core.network.FixedMobileApiProvider
import com.jonbj.alembic.monitor.core.security.InMemorySessionVault
import com.jonbj.alembic.monitor.data.repository.DeviceInfoProvider
import com.jonbj.alembic.monitor.data.repository.FakeTokenRefresher
import kotlinx.coroutines.test.runTest
import kotlinx.datetime.Clock
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PushRegistrationRepositoryTest {

    @Test
    fun `registration and FID rotation update the authenticated device`() = runTest {
        val api = FakeMobileApi()
        val repository = repository(api)

        assertTrue(repository.register("fid-one").isSuccess)
        assertTrue(repository.register("fid-two").isSuccess)

        assertEquals(listOf("fid-one", "fid-two"), api.deviceRegistrations.map {
            it.firebaseInstallationId
        })
        assertTrue(api.deviceRegistrations.all { it.pushEnabled })
        assertEquals(PushStatus.ENABLED, repository.status.value)
    }

    @Test
    fun `permission denial clears the server push destination`() = runTest {
        val api = FakeMobileApi()
        val repository = repository(api)

        assertTrue(repository.disable().isSuccess)

        assertEquals(1, api.deviceRegistrations.size)
        assertNull(api.deviceRegistrations.single().firebaseInstallationId)
        assertEquals(false, api.deviceRegistrations.single().pushEnabled)
        assertEquals(PushStatus.DISABLED, repository.status.value)
    }

    private fun repository(api: FakeMobileApi): PushRegistrationRepository {
        val now = Clock.System.now()
        val session = Session(
            accessToken = "access",
            refreshToken = "refresh",
            deviceId = "server-device",
            user = UserInfo("user", "monitor"),
            baseUrl = "https://alembic.lan/api/mobile/v1/",
            accessExpiresAt = now,
            refreshExpiresAt = null
        )
        return PushRegistrationRepository(
            apiProvider = FixedMobileApiProvider(api),
            sessionVault = InMemorySessionVault(session),
            deviceInfoProvider = object : DeviceInfoProvider {
                override fun installationId() = "app-installation"
                override fun deviceName() = "Pixel test"
            },
            appVersion = "1.0.0",
            refresher = FakeTokenRefresher()
        )
    }
}
