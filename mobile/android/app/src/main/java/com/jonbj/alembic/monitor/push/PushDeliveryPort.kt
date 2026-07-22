package com.jonbj.alembic.monitor.push

/**
 * Abstraction over push delivery. The server owns alert incidents; the payload is
 * only an opaque routing tuple. Implementations fetch details via the authenticated
 * mobile API after unlock, never from the push payload itself.
 */
interface PushDeliveryPort {
    fun isAvailable(): Boolean
    fun registerInstallationId(installationId: String)
    fun unregister()
}

class NoOpPushDelivery : PushDeliveryPort {
    override fun isAvailable(): Boolean = false
    override fun registerInstallationId(installationId: String) {}
    override fun unregister() {}
}
