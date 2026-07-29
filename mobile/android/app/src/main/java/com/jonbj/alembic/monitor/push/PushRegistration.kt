package com.jonbj.alembic.monitor.push

import android.content.Context
import com.google.firebase.FirebaseApp
import com.google.firebase.messaging.FirebaseMessaging
import com.jonbj.alembic.monitor.core.network.MobileApiProvider
import com.jonbj.alembic.monitor.core.network.dto.DeviceRegistrationRequest
import com.jonbj.alembic.monitor.core.security.SessionVault
import com.jonbj.alembic.monitor.data.repository.ApiCaller
import com.jonbj.alembic.monitor.data.repository.DeviceInfoProvider
import com.jonbj.alembic.monitor.data.repository.TokenRefresher
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

enum class PushStatus {
    DISABLED,
    REGISTERING,
    ENABLED,
    UNAVAILABLE,
    ERROR
}

interface PushGateway {
    val isAvailable: Boolean
    fun register()
    fun unregister()
}

class FirebasePushGateway(context: Context) : PushGateway {
    private val appContext = context.applicationContext
    override val isAvailable: Boolean
        get() = FirebaseApp.getApps(appContext).isNotEmpty()

    override fun register() {
        if (!isAvailable) return
        FirebaseMessaging.getInstance().register()
    }

    override fun unregister() {
        if (!isAvailable) return
        FirebaseMessaging.getInstance().unregister()
    }
}

class PushPreferenceStore(context: Context) {
    private val prefs = context.getSharedPreferences(
        "alembic_push_preferences",
        Context.MODE_PRIVATE
    )

    var permissionAsked: Boolean
        get() = prefs.getBoolean(KEY_ASKED, false)
        set(value) {
            prefs.edit().putBoolean(KEY_ASKED, value).apply()
        }

    var permissionEnabled: Boolean
        get() = prefs.getBoolean(KEY_ENABLED, false)
        set(value) {
            prefs.edit().putBoolean(KEY_ENABLED, value).apply()
        }

    private companion object {
        const val KEY_ASKED = "permission_asked"
        const val KEY_ENABLED = "permission_enabled"
    }
}

class PushRegistrationRepository(
    private val apiProvider: MobileApiProvider,
    private val sessionVault: SessionVault,
    private val deviceInfoProvider: DeviceInfoProvider,
    private val appVersion: String,
    private val refresher: TokenRefresher
) {
    private val _status = MutableStateFlow(PushStatus.DISABLED)
    val status: StateFlow<PushStatus> = _status.asStateFlow()

    suspend fun register(firebaseInstallationId: String): Result<Unit> {
        if (sessionVault.get() == null) return Result.success(Unit)
        _status.value = PushStatus.REGISTERING
        val request = DeviceRegistrationRequest(
            installationId = deviceInfoProvider.installationId(),
            firebaseInstallationId = firebaseInstallationId,
            name = deviceInfoProvider.deviceName(),
            appVersion = appVersion,
            pushEnabled = true
        )
        val result = ApiCaller.execute(refresher) {
            apiProvider.current().registerDevice(request)
        }.map { Unit }
        _status.value = if (result.isSuccess) PushStatus.ENABLED else PushStatus.ERROR
        return result
    }

    suspend fun disable(): Result<Unit> {
        if (sessionVault.get() == null) {
            _status.value = PushStatus.DISABLED
            return Result.success(Unit)
        }
        val request = DeviceRegistrationRequest(
            installationId = deviceInfoProvider.installationId(),
            firebaseInstallationId = null,
            name = deviceInfoProvider.deviceName(),
            appVersion = appVersion,
            pushEnabled = false
        )
        val result = ApiCaller.execute(refresher) {
            apiProvider.current().registerDevice(request)
        }.map { Unit }
        _status.value = PushStatus.DISABLED
        return result
    }

    fun unavailable() {
        _status.value = PushStatus.UNAVAILABLE
    }

    fun registering() {
        _status.value = PushStatus.REGISTERING
    }

    fun loggedOut() {
        _status.value = PushStatus.DISABLED
    }
}
