package com.jonbj.alembic.monitor.core.database

import kotlinx.datetime.Instant
import kotlinx.serialization.KSerializer

class InMemoryCacheStore : CacheStore {

    private data class Stored(
        val blob: String,
        val asOf: Instant,
        val dataAgeSeconds: Int
    )

    private val entries = mutableMapOf<String, Stored>()

    override suspend fun <T> put(
        key: String,
        value: T,
        serializer: KSerializer<T>,
        asOf: Instant,
        dataAgeSeconds: Int
    ) {
        entries[key] = Stored(
            blob = kotlinx.serialization.json.Json.encodeToString(serializer, value),
            asOf = asOf,
            dataAgeSeconds = dataAgeSeconds
        )
    }

    override suspend fun <T> get(key: String, serializer: KSerializer<T>): Cached<T>? {
        val stored = entries[key] ?: return null
        return Cached(
            data = kotlinx.serialization.json.Json.decodeFromString(serializer, stored.blob),
            asOf = stored.asOf,
            dataAgeSeconds = stored.dataAgeSeconds
        )
    }

    override suspend fun clear() {
        entries.clear()
    }
}
