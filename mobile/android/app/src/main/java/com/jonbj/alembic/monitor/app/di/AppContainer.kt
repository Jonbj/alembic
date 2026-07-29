package com.jonbj.alembic.monitor.app.di

import android.content.Context
import com.jonbj.alembic.monitor.BuildConfig
import com.jonbj.alembic.monitor.core.database.CacheStore
import com.jonbj.alembic.monitor.core.database.EncryptedCacheStore
import com.jonbj.alembic.monitor.core.database.MonitorDatabase
import com.jonbj.alembic.monitor.core.network.ServerUrlPolicy
import com.jonbj.alembic.monitor.core.network.SessionMobileApiProvider
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
import com.jonbj.alembic.monitor.data.repository.ForegroundRefreshCoordinator
import com.jonbj.alembic.monitor.data.repository.PerformanceRepository
import com.jonbj.alembic.monitor.data.repository.PortfolioRepository
import com.jonbj.alembic.monitor.data.repository.StatusRepository
import com.jonbj.alembic.monitor.push.DeepLinkCoordinator
import com.jonbj.alembic.monitor.push.FirebasePushGateway
import com.jonbj.alembic.monitor.push.PushCoordinator
import com.jonbj.alembic.monitor.push.PushPreferenceStore
import com.jonbj.alembic.monitor.push.PushRegistrationRepository
import kotlinx.serialization.json.Json

class AppContainer(
    context: Context,
    defaultBaseUrl: String,
    private val appVersion: String
) {
    private val appContext = context.applicationContext

    private val json: Json by lazy {
        Json {
            ignoreUnknownKeys = true
            coerceInputValues = true
        }
    }

    private val database: MonitorDatabase by lazy {
        MonitorDatabase.create(appContext)
    }

    private val sessionCipher by lazy {
        AndroidKeystoreAesGcmCipher(alias = "alembic_session_key")
    }

    private val cacheCipher by lazy {
        AndroidKeystoreAesGcmCipher(alias = "alembic_cache_key")
    }

    val sessionVault: SessionVault by lazy {
        EncryptedSessionVault(appContext, sessionCipher, json)
    }

    val deviceInfoProvider: DeviceInfoProvider by lazy {
        AndroidDeviceInfoProvider(appContext)
    }

    private val apiProvider by lazy {
        SessionMobileApiProvider(defaultBaseUrl, sessionVault, json)
    }

    private val cacheStore: CacheStore by lazy {
        EncryptedCacheStore(database.cacheEntryDao(), cacheCipher, json)
    }

    val authRepository: AuthRepository by lazy {
        AuthRepository(
            apiProvider = apiProvider,
            vault = sessionVault,
            serverUrlPolicy = ServerUrlPolicy(allowDebugCleartext = BuildConfig.DEBUG),
            appVersion = appVersion,
            clearLocalData = {
                try {
                    sessionVault.clear()
                } finally {
                    cacheStore.clear()
                }
            }
        )
    }

    val statusRepository: StatusRepository by lazy {
        StatusRepository(apiProvider, cacheStore, authRepository)
    }

    val performanceRepository: PerformanceRepository by lazy {
        PerformanceRepository(apiProvider, cacheStore, authRepository)
    }

    val portfolioRepository: PortfolioRepository by lazy {
        PortfolioRepository(apiProvider, cacheStore, authRepository)
    }

    val eventsRepository: EventsRepository by lazy {
        EventsRepository(apiProvider, cacheStore, authRepository)
    }

    val foregroundRefreshCoordinator: ForegroundRefreshCoordinator by lazy {
        ForegroundRefreshCoordinator(statusRepository, portfolioRepository)
    }

    val appLock: AppLock by lazy {
        TimeoutAppLock(sessionVault)
    }

    val biometricGate: BiometricGate by lazy {
        AndroidBiometricGate(appContext)
    }

    val deepLinkCoordinator by lazy {
        DeepLinkCoordinator(appLock)
    }

    val pushRegistrationRepository by lazy {
        PushRegistrationRepository(
            apiProvider = apiProvider,
            sessionVault = sessionVault,
            deviceInfoProvider = deviceInfoProvider,
            appVersion = appVersion,
            refresher = authRepository
        )
    }

    val pushCoordinator by lazy {
        PushCoordinator(
            gateway = FirebasePushGateway(appContext),
            preferences = PushPreferenceStore(appContext),
            repository = pushRegistrationRepository
        )
    }

    suspend fun logout(): Result<Unit> {
        pushCoordinator.onLogout()
        return authRepository.logout()
    }
}
