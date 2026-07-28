package com.jonbj.alembic.monitor.core.network

import java.net.URI
import java.util.Locale

class ServerUrlPolicy(
    private val allowDebugCleartext: Boolean
) {
    fun normalize(input: String): Result<String> = runCatching {
        val uri = URI(input.trim())
        val scheme = uri.scheme?.lowercase(Locale.ROOT)
            ?: throw IllegalArgumentException("Inserisci un URL completo")
        val host = uri.host?.lowercase(Locale.ROOT)
            ?: throw IllegalArgumentException("Host server non valido")

        require(uri.rawUserInfo == null) { "L'URL non può contenere credenziali" }
        require(uri.rawQuery == null && uri.rawFragment == null) {
            "L'URL non può contenere query o frammenti"
        }
        require(uri.path.isNullOrEmpty() || uri.path == "/" ||
            uri.path == API_PATH.removeSuffix("/") || uri.path == API_PATH
        ) {
            "Usa l'origine del server o il percorso $API_PATH"
        }

        when (scheme) {
            "https" -> Unit
            "http" -> require(allowDebugCleartext && host in DEBUG_CLEARTEXT_HOSTS) {
                "HTTPS è obbligatorio"
            }
            else -> throw IllegalArgumentException("Sono supportati solo URL HTTPS")
        }

        URI(scheme, null, host, uri.port, API_PATH, null, null).toASCIIString()
    }

    companion object {
        private const val API_PATH = "/api/mobile/v1/"
        private val DEBUG_CLEARTEXT_HOSTS = setOf(
            "localhost",
            "127.0.0.1",
            "10.0.2.2",
            "10.0.3.2"
        )
    }
}
