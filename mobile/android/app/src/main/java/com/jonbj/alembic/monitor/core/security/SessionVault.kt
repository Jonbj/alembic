package com.jonbj.alembic.monitor.core.security

import android.content.Context
import com.jonbj.alembic.monitor.core.model.Session
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import java.io.File

interface SessionVault {
    val sessionFlow: StateFlow<Session?>
    suspend fun save(session: Session)
    suspend fun get(): Session?
    fun getBlocking(): Session?
    suspend fun clear()
}

class EncryptedSessionVault(
    context: Context,
    private val cipher: AesGcmCipher,
    private val json: Json
) : SessionVault {

    private val vaultFile = File(context.filesDir, "session.vault")
    private val _sessionFlow = MutableStateFlow<Session?>(null)
    override val sessionFlow: StateFlow<Session?> = _sessionFlow.asStateFlow()

    init {
        _sessionFlow.value = getBlocking()
    }

    override suspend fun save(session: Session) {
        val plaintext = json.encodeToString(session)
        val ciphertext = cipher.encrypt(plaintext)
        vaultFile.writeBytes(ciphertext)
        _sessionFlow.value = session
    }

    override suspend fun get(): Session? = getBlocking()

    override fun getBlocking(): Session? {
        if (!vaultFile.exists() || vaultFile.length() == 0L) return null
        return try {
            val ciphertext = vaultFile.readBytes()
            val plaintext = cipher.decrypt(ciphertext)
            json.decodeFromString(Session.serializer(), plaintext)
        } catch (e: Exception) {
            null
        }
    }

    override suspend fun clear() {
        if (vaultFile.exists()) {
            vaultFile.delete()
        }
        _sessionFlow.value = null
    }
}
