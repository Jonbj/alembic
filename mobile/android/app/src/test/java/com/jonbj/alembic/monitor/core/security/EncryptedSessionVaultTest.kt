package com.jonbj.alembic.monitor.core.security

import com.jonbj.alembic.monitor.core.model.Session
import com.jonbj.alembic.monitor.core.model.UserInfo
import kotlinx.coroutines.test.runTest
import kotlinx.datetime.Clock
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment

@RunWith(RobolectricTestRunner::class)
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
}
