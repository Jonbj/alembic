package com.jonbj.alembic.monitor

import android.app.Application
import android.os.StrictMode
import com.jonbj.alembic.monitor.app.di.AppContainer

class MonitorApplication : Application() {
    lateinit var container: AppContainer
        private set

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

        // BuildConfig supplies only the first-run suggestion. The validated server
        // selected during login is stored inside the encrypted session.
        val baseUrl = BuildConfig.BASE_URL.ifBlank { "https://alembic.lan" }
        container = AppContainer(this, baseUrl, BuildConfig.VERSION_NAME)
        com.jonbj.alembic.monitor.worker.CacheRefreshWorker.enqueue(this)
    }
}
