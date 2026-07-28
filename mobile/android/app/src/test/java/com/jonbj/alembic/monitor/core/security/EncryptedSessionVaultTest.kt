package com.jonbj.alembic.monitor.core.security

import android.app.Application
import com.jonbj.alembic.monitor.core.model.Session
import com.jonbj.alembic.monitor.core.model.UserInfo
import kotlinx.coroutines.test.runTest
import kotlinx.datetime.Clock
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertFalse
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import java.io.File

@RunWith(RobolectricTestRunner::class)
@Config(application = Application::class, sdk = [34])
class EncryptedSessionVaultTest {

    private val json = Json { ignoreUnknownKeys = true }
    private val context = RuntimeEnvironment.getApplication()
    private val vault = EncryptedSessionVault(context, TestAesGcmCipher(), json)

    private val sampleSession = Session(
        accessToken = "access_token_123",
        refreshToken = "refresh_token_456",
        deviceId = "device_789",
        user = UserInfo("user_1", "monitor-stefano"),
        baseUrl = "https://alembic.lan/",
        accessExpiresAt = Clock.System.now(),
        refreshExpiresAt = null
    )

    @Test
    fun saveAndRetrieveSession() = runTest {
        vault.save(sampleSession)
        val retrieved = vault.get()
        assertEquals(sampleSession, retrieved)
    }

    @Test
    fun clearRemovesSession() = runTest {
        vault.save(sampleSession)
        vault.clear()
        assertNull(vault.get())
    }

    @Test
    fun sessionFlowReflectsChanges() = runTest {
        vault.save(sampleSession)
        assertEquals(sampleSession, vault.sessionFlow.value)
        vault.clear()
        assertNull(vault.sessionFlow.value)
    }

    @Test
    fun repeatedSaveAtomicallyReplacesThePreviousSession() = runTest {
        vault.save(sampleSession)
        val rotated = sampleSession.copy(
            accessToken = "access_rotated",
            refreshToken = "refresh_rotated"
        )

        vault.save(rotated)

        assertEquals(rotated, vault.get())
    }

    @Test
    fun corruptVaultFailsClosedAndDeletesUnreadableMaterial() {
        val file = File(context.filesDir, "session.vault")
        file.writeBytes(byteArrayOf(1, 2, 3, 4))

        val reopened = EncryptedSessionVault(context, TestAesGcmCipher(), json)

        assertNull(reopened.getBlocking())
        assertFalse(file.exists())
    }
}
