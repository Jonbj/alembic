package com.jonbj.alembic.monitor

import android.app.Application
import android.os.StrictMode
import com.jonbj.alembic.monitor.app.di.AppModule

class MonitorApplication : Application() {

    override fun onCreate() {
        super.onCreate()

        if (BuildConfig.DEBUG) {
            StrictMode.setThreadPolicy(
                StrictMode.ThreadPolicy.Builder()
                    .detectNetwork()
                    .penaltyLog()
                    .build()
            )
        }

        // Read base URL from BuildConfig; in production this is baked at build time or
        // supplied via a managed configuration. It is never hard-coded to real credentials.
        val baseUrl = BuildConfig.BASE_URL.ifBlank { "https://alembic.lan" }
        AppModule.init(this, baseUrl, BuildConfig.VERSION_NAME)
        com.jonbj.alembic.monitor.worker.CacheRefreshWorker.enqueue(this)
    }
}
