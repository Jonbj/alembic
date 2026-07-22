package com.jonbj.alembic.monitor.app.di

import android.content.Context
import com.jonbj.alembic.monitor.core.database.CacheStore
import com.jonbj.alembic.monitor.core.database.EncryptedCacheStore
import com.jonbj.alembic.monitor.core.database.MonitorDatabase
import com.jonbj.alembic.monitor.core.network.MobileApi
import com.jonbj.alembic.monitor.core.network.MobileApiClient
import com.jonbj.alembic.monitor.core.security.AndroidBiometricGate
import com.jonbj.alembic.monitor.core.security.AndroidKeystoreAesGcmCipher
import com.jonbj.alembic.monitor.core.security.AppLock
import com.jonbj.alembic.monitor.core.security.BiometricGate
import com.jonbj.alembic.monitor.core.security.EncryptedSessionVault
import com.jonbj.alembic.monitor.core.security.SessionVault
import com.jonbj.alembic.monitor.core.security.TimeoutAppLock
import com.jonbj.alembic.monitor.data.repository.AndroidDeviceInfoProvider
import com.jonbj.alembic.monitor.data.repository.AuthRepository
import com.jonbj.alembic.monitor.data.repository.DeviceInfoProvider
import com.jonbj.alembic.monitor.data.repository.EventsRepository
import com.jonbj.alembic.monitor.data.repository.PerformanceRepository
import com.jonbj.alembic.monitor.data.repository.PortfolioRepository
import com.jonbj.alembic.monitor.data.repository.StatusRepository
import kotlinx.serialization.json.Json

object AppModule {

    private lateinit var appContext: Context
    private lateinit var baseUrl: String
    private lateinit var appVersion: String

    private val json: Json by lazy {
        Json {
            ignoreUnknownKeys = true
            explicitNulls = false
            coerceInputValues = true
        }
    }

    private val database: MonitorDatabase by lazy {
        MonitorDatabase.create(appContext)
    }

    private val cipher by lazy {
        AndroidKeystoreAesGcmCipher()
    }

    val sessionVault: SessionVault by lazy {
        EncryptedSessionVault(appContext, cipher, json)
    }

    val deviceInfoProvider: DeviceInfoProvider by lazy {
        AndroidDeviceInfoProvider(appContext)
    }

    private val mobileApi: MobileApi by lazy {
        MobileApiClient.create(baseUrl, sessionVault, json)
    }

    private val cacheStore: CacheStore by lazy {
        EncryptedCacheStore(database.cacheEntryDao(), cipher, json)
    }

    val authRepository: AuthRepository by lazy {
        AuthRepository(mobileApi, sessionVault, baseUrl, appVersion)
    }

    val statusRepository: StatusRepository by lazy {
        StatusRepository(mobileApi, cacheStore, json, authRepository)
    }

    val performanceRepository: PerformanceRepository by lazy {
        PerformanceRepository(mobileApi, cacheStore, json, authRepository)
    }

    val portfolioRepository: PortfolioRepository by lazy {
        PortfolioRepository(mobileApi, cacheStore, json, authRepository)
    }

    val eventsRepository: EventsRepository by lazy {
        EventsRepository(mobileApi, cacheStore, json, authRepository)
    }

    val appLock: AppLock by lazy {
        TimeoutAppLock(sessionVault)
    }

    val biometricGate: BiometricGate by lazy {
        AndroidBiometricGate(appContext)
    }

    fun init(context: Context, baseUrl: String, appVersion: String) {
        appContext = context.applicationContext
        this.baseUrl = ensureTrailingSlash(baseUrl)
        this.appVersion = appVersion
    }

    private fun ensureTrailingSlash(url: String): String {
        return if (url.endsWith("/")) url else "$url/"
    }
}
