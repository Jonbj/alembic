package com.jonbj.alembic.monitor.core.security

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.jonbj.alembic.monitor.core.model.Session
import com.jonbj.alembic.monitor.core.model.UserInfo
import kotlinx.coroutines.runBlocking
import kotlinx.datetime.Clock
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class KeystoreSessionVaultInstrumentedTest {

    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private val json = Json { ignoreUnknownKeys = true }
    private val cipher = AndroidKeystoreAesGcmCipher(alias = "test_alembic_key")
    private val vault = EncryptedSessionVault(context, cipher, json)

    private val sampleSession = Session(
        accessToken = "access",
        refreshToken = "refresh",
        deviceId = "device",
        user = UserInfo("u1", "monitor"),
        baseUrl = "https://alembic.lan/",
        accessExpiresAt = Clock.System.now(),
        refreshExpiresAt = null
    )

    @Test
    fun encryptAndDecryptRoundTrip() = runBlocking {
        val plaintext = """{"key":"value"}"""
        val encrypted = cipher.encrypt(plaintext)
        val decrypted = cipher.decrypt(encrypted)
        assertEquals(plaintext, decrypted)
    }

    @Test
    fun saveAndLoadSession() = runBlocking {
        vault.save(sampleSession)
        assertEquals(sampleSession, vault.get())
        vault.clear()
    }
}
