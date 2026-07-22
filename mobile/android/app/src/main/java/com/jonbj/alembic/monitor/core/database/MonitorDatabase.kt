package com.jonbj.alembic.monitor.core.database

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase

@Database(entities = [CacheEntry::class], version = 1, exportSchema = false)
abstract class MonitorDatabase : RoomDatabase() {
    abstract fun cacheEntryDao(): CacheEntryDao

    companion object {
        private const val NAME = "alembic_monitor_cache.db"

        fun create(context: Context): MonitorDatabase {
            return Room.databaseBuilder(context, MonitorDatabase::class.java, NAME)
                .fallbackToDestructiveMigration()
                .build()
        }

        fun createInMemory(context: Context): MonitorDatabase {
            return Room.inMemoryDatabaseBuilder(context, MonitorDatabase::class.java)
                .fallbackToDestructiveMigration()
                .build()
        }
    }
}
