package com.jonbj.alembic.monitor.core.database

import com.jonbj.alembic.monitor.core.security.AesGcmCipher
import kotlinx.datetime.Instant
import kotlinx.datetime.Clock
import kotlinx.serialization.KSerializer
import kotlinx.serialization.json.Json

interface CacheStore {
    suspend fun <T> put(
        key: String,
        value: T,
        serializer: KSerializer<T>,
        asOf: Instant,
        dataAgeSeconds: Int
    )

    suspend fun <T> get(
        key: String,
        serializer: KSerializer<T>
    ): Cached<T>?

    suspend fun clear()
}

data class Cached<T>(
    val data: T,
    val asOf: Instant,
    val dataAgeSeconds: Int
)

class EncryptedCacheStore(
    private val dao: CacheEntryDao,
    private val cipher: AesGcmCipher,
    private val json: Json,
    private val clock: Clock = Clock.System
) : CacheStore {

    override suspend fun <T> put(
        key: String,
        value: T,
        serializer: KSerializer<T>,
        asOf: Instant,
        dataAgeSeconds: Int
    ) {
        val plaintext = json.encodeToString(serializer, value)
        val encrypted = cipher.encrypt(plaintext)
        dao.upsert(
            CacheEntry(
                key = key,
                encryptedBlob = encrypted,
                asOfEpochSeconds = asOf.epochSeconds,
                dataAgeSeconds = dataAgeSeconds
            )
        )
    }

    override suspend fun <T> get(
        key: String,
        serializer: KSerializer<T>
    ): Cached<T>? {
        val entry = dao.get(key) ?: return null
        return try {
            val plaintext = cipher.decrypt(entry.encryptedBlob)
            val asOf = Instant.fromEpochSeconds(entry.asOfEpochSeconds)
            val wallAgeSeconds = (clock.now() - asOf).inWholeSeconds
                .coerceAtLeast(0)
                .coerceAtMost(Int.MAX_VALUE.toLong())
                .toInt()
            Cached(
                data = json.decodeFromString(serializer, plaintext),
                asOf = asOf,
                dataAgeSeconds = maxOf(entry.dataAgeSeconds, wallAgeSeconds)
            )
        } catch (e: Exception) {
            dao.delete(key)
            null
        }
    }

    override suspend fun clear() {
        dao.clear()
    }
}
