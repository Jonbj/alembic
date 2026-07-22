package com.jonbj.alembic.monitor.data.repository

import android.content.Context
import android.os.Build
import java.util.UUID

interface DeviceInfoProvider {
    fun installationId(): String
    fun deviceName(): String
}

class AndroidDeviceInfoProvider(context: Context) : DeviceInfoProvider {

    private val prefs = context.getSharedPreferences("alembic_device", Context.MODE_PRIVATE)

    override fun installationId(): String {
        val existing = prefs.getString(KEY_INSTALLATION_ID, null)
        if (existing != null) return existing
        val generated = UUID.randomUUID().toString()
        prefs.edit().putString(KEY_INSTALLATION_ID, generated).apply()
        return generated
    }

    override fun deviceName(): String = Build.MODEL ?: "Android"

    companion object {
        private const val KEY_INSTALLATION_ID = "installation_id"
    }
}
