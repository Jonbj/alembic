package com.jonbj.alembic.monitor.core.database

import android.app.Application
import com.jonbj.alembic.monitor.core.security.TestAesGcmCipher
import kotlinx.coroutines.test.runTest
import kotlinx.datetime.Instant
import kotlinx.datetime.Clock
import kotlinx.serialization.builtins.serializer
import kotlinx.serialization.json.Json
import org.junit.After
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(application = Application::class, sdk = [34])
class EncryptedCacheStoreTest {
    private val database = MonitorDatabase.createInMemory(RuntimeEnvironment.getApplication())
    private val dao = database.cacheEntryDao()
    private val store = EncryptedCacheStore(dao, TestAesGcmCipher(), Json)

    @After
    fun closeDatabase() {
        database.close()
    }

    @Test
    fun `sensitive payload is encrypted and purge removes every cached entry`() = runTest {
        val secret = "NAV=110307.36;MSFT"
        store.put(
            CacheKey.SNAPSHOT,
            secret,
            String.serializer(),
            Instant.parse("2026-07-28T10:00:00Z"),
            0
        )

        val rawBlob = dao.get(CacheKey.SNAPSHOT)!!.encryptedBlob
        assertFalse(rawBlob.toString(Charsets.UTF_8).contains(secret))
        assertTrue(store.get(CacheKey.SNAPSHOT, String.serializer())?.data == secret)

        store.clear()

        assertNull(dao.get(CacheKey.SNAPSHOT))
    }

    @Test
    fun `cached age advances while the device is offline`() = runTest {
        val asOf = Instant.parse("2026-07-28T10:00:00Z")
        val clock = object : Clock {
            override fun now(): Instant = Instant.parse("2026-07-28T10:10:00Z")
        }
        val agingStore = EncryptedCacheStore(dao, TestAesGcmCipher(), Json, clock)
        agingStore.put(CacheKey.SNAPSHOT, "payload", String.serializer(), asOf, 30)

        val cached = agingStore.get(CacheKey.SNAPSHOT, String.serializer())!!

        assertTrue(cached.dataAgeSeconds >= 600)
    }
}
