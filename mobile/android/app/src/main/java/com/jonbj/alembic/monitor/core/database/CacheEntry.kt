package com.jonbj.alembic.monitor.core.database

import androidx.room.Dao
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query

@Entity(tableName = "cache_entries")
data class CacheEntry(
    @PrimaryKey val key: String,
    val encryptedBlob: ByteArray,
    val asOfEpochSeconds: Long,
    val dataAgeSeconds: Int
) {
    override fun equals(other: Any?): Boolean {
        if (this === other) return true
        if (javaClass != other?.javaClass) return false
        other as CacheEntry
        return key == other.key &&
            asOfEpochSeconds == other.asOfEpochSeconds &&
            dataAgeSeconds == other.dataAgeSeconds &&
            encryptedBlob.contentEquals(other.encryptedBlob)
    }

    override fun hashCode(): Int {
        var result = key.hashCode()
        result = 31 * result + encryptedBlob.contentHashCode()
        result = 31 * result + asOfEpochSeconds.hashCode()
        result = 31 * result + dataAgeSeconds
        return result
    }
}

@Dao
interface CacheEntryDao {
    @Query("SELECT * FROM cache_entries WHERE key = :key")
    suspend fun get(key: String): CacheEntry?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entry: CacheEntry)

    @Query("DELETE FROM cache_entries WHERE key = :key")
    suspend fun delete(key: String)

    @Query("DELETE FROM cache_entries")
    suspend fun clear()
}

object CacheKey {
    const val SNAPSHOT = "snapshot"
    const val PERFORMANCE = "performance"
    const val POSITIONS = "positions"
    const val EVENTS = "events"
}
