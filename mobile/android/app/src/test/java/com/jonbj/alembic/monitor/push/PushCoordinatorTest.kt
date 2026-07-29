package com.jonbj.alembic.monitor.push

import android.app.Application
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
import org.junit.Assert.assertFalse
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(application = Application::class)
class PushCoordinatorTest {
    private val context: Application
        get() = RuntimeEnvironment.getApplication()

    @Before
    fun clearPreferences() {
        context.getSharedPreferences(
            "alembic_push_preferences",
            Application.MODE_PRIVATE
        ).edit().clear().commit()
    }

    @Test
    fun `logout unregisters the local FID and clears push state`() = runTest {
        val api = FakeMobileApi()
        val gateway = FakePushGateway()
        val preferences = PushPreferenceStore(context)
        val repository = repository(api)
        val coordinator = PushCoordinator(gateway, preferences, repository)

        coordinator.onPermissionResult(granted = true)
        coordinator.onLogout()

        assertEquals(1, gateway.registerCalls)
        assertEquals(1, gateway.unregisterCalls)
        assertFalse(preferences.permissionEnabled)
        assertEquals(PushStatus.DISABLED, repository.status.value)
    }

    @Test
    fun `permission denial disables push without ending the monitor session`() = runTest {
        val api = FakeMobileApi()
        val gateway = FakePushGateway()
        val preferences = PushPreferenceStore(context)
        val repository = repository(api)
        val coordinator = PushCoordinator(gateway, preferences, repository)

        coordinator.onPermissionResult(granted = false)

        assertEquals(1, gateway.unregisterCalls)
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

private class FakePushGateway(
    override val isAvailable: Boolean = true
) : PushGateway {
    var registerCalls = 0
    var unregisterCalls = 0

    override fun register() {
        registerCalls += 1
    }

    override fun unregister() {
        unregisterCalls += 1
    }
}
