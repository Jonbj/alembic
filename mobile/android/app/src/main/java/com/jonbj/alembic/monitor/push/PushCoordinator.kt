package com.jonbj.alembic.monitor.push

class PushCoordinator(
    private val gateway: PushGateway,
    private val preferences: PushPreferenceStore,
    private val repository: PushRegistrationRepository
) {
    val shouldExplainPermission: Boolean
        get() = gateway.isAvailable && !preferences.permissionAsked

    suspend fun onPermissionResult(granted: Boolean) {
        preferences.permissionAsked = true
        preferences.permissionEnabled = granted
        if (!gateway.isAvailable) {
            repository.unavailable()
            return
        }
        if (granted) {
            repository.registering()
            gateway.register(repository::unavailable)
        } else {
            gateway.unregister()
            repository.disable()
        }
    }

    suspend fun onPermissionDeferred() {
        preferences.permissionEnabled = false
        if (gateway.isAvailable) gateway.unregister()
        repository.disable()
    }

    suspend fun onRegistered(firebaseInstallationId: String) {
        if (preferences.permissionEnabled) {
            repository.register(firebaseInstallationId)
        }
    }

    fun onLogout() {
        preferences.permissionEnabled = false
        gateway.unregister()
        repository.loggedOut()
    }
}
