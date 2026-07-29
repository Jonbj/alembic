package com.jonbj.alembic.monitor.push

import android.content.Context

interface DeliveryFingerprintStore {
    fun contains(fingerprint: String): Boolean
    fun add(fingerprint: String)
}

class NotificationDeduplicator(
    private val store: DeliveryFingerprintStore
) {
    fun shouldNotify(payload: PushPayload): Boolean {
        if (store.contains(payload.fingerprint)) return false
        store.add(payload.fingerprint)
        return true
    }
}

class SharedPreferencesDeliveryFingerprintStore(context: Context) :
    DeliveryFingerprintStore {
    private val prefs = context.getSharedPreferences(
        "alembic_push_delivery",
        Context.MODE_PRIVATE
    )

    override fun contains(fingerprint: String): Boolean =
        prefs.getStringSet(KEY_FINGERPRINTS, emptySet())
            ?.contains(fingerprint) == true

    override fun add(fingerprint: String) {
        val existing = prefs.getStringSet(KEY_FINGERPRINTS, emptySet())
            .orEmpty()
            .toMutableList()
        existing.remove(fingerprint)
        existing += fingerprint
        prefs.edit()
            .putStringSet(KEY_FINGERPRINTS, existing.takeLast(MAX_ENTRIES).toSet())
            .apply()
    }

    private companion object {
        const val KEY_FINGERPRINTS = "fingerprints"
        const val MAX_ENTRIES = 128
    }
}

class InMemoryDeliveryFingerprintStore : DeliveryFingerprintStore {
    private val fingerprints = mutableSetOf<String>()
    override fun contains(fingerprint: String) = fingerprint in fingerprints
    override fun add(fingerprint: String) {
        fingerprints += fingerprint
    }
}
