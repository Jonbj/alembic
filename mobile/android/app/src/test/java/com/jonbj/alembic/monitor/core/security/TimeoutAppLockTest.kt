package com.jonbj.alembic.monitor.core.security

import com.jonbj.alembic.monitor.core.model.Session
import com.jonbj.alembic.monitor.core.model.UserInfo
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest
import kotlinx.datetime.Clock
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class TimeoutAppLockTest {

    private val session = Session(
        accessToken = "a",
        refreshToken = "r",
        deviceId = "d",
        user = UserInfo("u", "n"),
        baseUrl = "https://alembic.lan/",
        accessExpiresAt = Clock.System.now(),
        refreshExpiresAt = null
    )

    @Test
    fun `existing session is locked on cold startup`() = runTest {
        val vault = InMemorySessionVault(session)
        val lock = TimeoutAppLock(
            vault,
            clock = { 0L },
            dispatcher = UnconfinedTestDispatcher(testScheduler)
        )

        assertTrue(lock.isLocked.value)
    }

    @Test
    fun `session token rotation does not relock an unlocked app`() = runTest {
        val vault = InMemorySessionVault(session)
        val lock = TimeoutAppLock(
            vault,
            clock = { 0L },
            dispatcher = UnconfinedTestDispatcher(testScheduler)
        )
        lock.unlock()

        vault.save(session.copy(accessToken = "rotated"))

        assertFalse(lock.isLocked.value)
    }

    @Test
    fun `lock triggers after five minutes in background`() = runTest {
        var now = 0L
        val vault = InMemorySessionVault(session)
        val lock = TimeoutAppLock(
            vault,
            timeoutMillis = 5L * 60L * 1000L,
            clock = { now },
            dispatcher = UnconfinedTestDispatcher(testScheduler)
        )

        lock.unlock()
        assertFalse(lock.isLocked.value)

        lock.onAppBackground()
        now += 5L * 60L * 1000L + 1L
        lock.onAppForeground()

        assertTrue(lock.isLocked.value)
    }

    @Test
    fun `short background does not lock`() = runTest {
        var now = 0L
        val vault = InMemorySessionVault(session)
        val lock = TimeoutAppLock(
            vault,
            timeoutMillis = 5L * 60L * 1000L,
            clock = { now },
            dispatcher = UnconfinedTestDispatcher(testScheduler)
        )

        lock.unlock()
        lock.onAppBackground()
        now += 60L * 1000L
        lock.onAppForeground()

        assertFalse(lock.isLocked.value)
    }

    @Test
    fun `no session means no lock`() = runTest {
        var now = 0L
        val vault = InMemorySessionVault(null)
        val lock = TimeoutAppLock(
            vault,
            timeoutMillis = 5L * 60L * 1000L,
            clock = { now },
            dispatcher = UnconfinedTestDispatcher(testScheduler)
        )

        lock.unlock()
        lock.onAppBackground()
        now += 10L * 60L * 1000L
        lock.onAppForeground()

        assertFalse(lock.isLocked.value)
    }

    @Test
    fun `unlock resets locked state`() = runTest {
        var now = 0L
        val vault = InMemorySessionVault(session)
        val lock = TimeoutAppLock(
            vault,
            timeoutMillis = 5L * 60L * 1000L,
            clock = { now },
            dispatcher = UnconfinedTestDispatcher(testScheduler)
        )

        lock.unlock()
        lock.onAppBackground()
        now += 6L * 60L * 1000L
        lock.onAppForeground()
        assertTrue(lock.isLocked.value)

        lock.unlock()
        assertFalse(lock.isLocked.value)
    }

    @Test
    fun `notification force lock survives login until biometric unlock`() = runTest {
        val vault = InMemorySessionVault(null)
        val lock = TimeoutAppLock(
            vault,
            clock = { 0L },
            dispatcher = UnconfinedTestDispatcher(testScheduler)
        )

        lock.lock()
        vault.save(session)

        assertTrue(lock.isLocked.value)
        lock.unlock()
        assertFalse(lock.isLocked.value)
    }
}
