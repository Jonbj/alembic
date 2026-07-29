package com.jonbj.alembic.monitor.push

import android.app.Application
import android.content.Intent
import com.jonbj.alembic.monitor.core.model.Session
import com.jonbj.alembic.monitor.core.model.UserInfo
import com.jonbj.alembic.monitor.core.security.InMemorySessionVault
import com.jonbj.alembic.monitor.core.security.TimeoutAppLock
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest
import kotlinx.datetime.Clock
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(application = Application::class)
@OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
class NotificationDeepLinkGateTest {

    @Test
    fun `cold warm and process-dead notification intents remain pending behind app lock`() = runTest {
        val eventId = "15af48e4-2be5-4ea0-969f-a59ca154bf79"
        val opaqueEventId = requireNotNull(OpaqueEventId.parse(eventId))

        val coldVault = InMemorySessionVault(null)
        val coldLock = lock(coldVault)
        val coldCoordinator = DeepLinkCoordinator(coldLock)
        assertTrue(coldCoordinator.accept(intent(eventId)))
        coldVault.save(session())
        assertTrue(coldLock.isLocked.value)
        assertEquals(opaqueEventId, coldCoordinator.pendingEventId.value)
        assertEquals(null, coldCoordinator.authenticatedEventId())
        coldLock.unlock()
        assertEquals(opaqueEventId, coldCoordinator.authenticatedEventId())

        val warmVault = InMemorySessionVault(session())
        val warmLock = lock(warmVault).apply { unlock() }
        val warmCoordinator = DeepLinkCoordinator(warmLock)
        assertTrue(warmCoordinator.accept(intent(eventId)))
        assertTrue(warmLock.isLocked.value)
        assertEquals(opaqueEventId, warmCoordinator.pendingEventId.value)
        assertEquals(null, warmCoordinator.authenticatedEventId())
        warmLock.unlock()
        assertEquals(opaqueEventId, warmCoordinator.authenticatedEventId())

        val restoredVault = InMemorySessionVault(session())
        val restoredLock = lock(restoredVault)
        val restoredCoordinator = DeepLinkCoordinator(restoredLock)
        assertTrue(restoredCoordinator.accept(intent(eventId)))
        assertTrue(restoredLock.isLocked.value)
        assertEquals(opaqueEventId, restoredCoordinator.pendingEventId.value)
        assertEquals(null, restoredCoordinator.authenticatedEventId())
        restoredLock.unlock()
        assertEquals(opaqueEventId, restoredCoordinator.authenticatedEventId())
    }

    private fun lock(vault: InMemorySessionVault) = TimeoutAppLock(
        vault,
        clock = { 0L },
        dispatcher = UnconfinedTestDispatcher()
    )

    private fun intent(eventId: String) = Intent().apply {
        action = DeepLinkCoordinator.ACTION_OPEN_EVENT
        putExtra(DeepLinkCoordinator.EXTRA_EVENT_ID, eventId)
    }

    private fun session(): Session {
        val now = Clock.System.now()
        return Session(
            accessToken = "access",
            refreshToken = "refresh",
            deviceId = "device",
            user = UserInfo("user", "monitor"),
            baseUrl = "https://alembic.lan/api/mobile/v1/",
            accessExpiresAt = now,
            refreshExpiresAt = null
        )
    }
}
