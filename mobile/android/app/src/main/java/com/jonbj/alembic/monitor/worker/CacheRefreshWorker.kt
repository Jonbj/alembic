package com.jonbj.alembic.monitor.worker

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.jonbj.alembic.monitor.app.di.AppModule
import java.util.concurrent.TimeUnit

class CacheRefreshWorker(
    context: Context,
    params: WorkerParameters
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        return try {
            if (AppModule.sessionVault.get() == null) {
                return Result.success()
            }
            AppModule.statusRepository.refresh(force = false)
            AppModule.portfolioRepository.refresh(force = false)
            Result.success()
        } catch (e: Exception) {
            Result.retry()
        }
    }

    companion object {
        private const val WORK_NAME = "cache_refresh"

        fun enqueue(context: Context) {
            val request = PeriodicWorkRequestBuilder<CacheRefreshWorker>(15, TimeUnit.MINUTES)
                .setConstraints(
                    androidx.work.Constraints.Builder()
                        .setRequiresBatteryNotLow(true)
                        .build()
                )
                .build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                WORK_NAME,
                ExistingPeriodicWorkPolicy.KEEP,
                request
            )
        }
    }
}
