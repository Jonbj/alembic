package com.jonbj.alembic.monitor.core.model

sealed class MobileError(
    val code: String,
    message: String,
    val retryable: Boolean = true
) : Exception(message) {

    class Network(message: String) :
        MobileError("network_error", message, retryable = true)

    class Http(
        val statusCode: Int,
        message: String,
        val serverCode: String? = null
    ) : MobileError("http_$statusCode", message, retryable = statusCode in 500..599)

    class Auth(
        message: String,
        val requireRelogin: Boolean = false
    ) : MobileError("auth_error", message, retryable = false)

    class Version(message: String) :
        MobileError("version_update_required", message, retryable = false)

    class Unknown(message: String) :
        MobileError("unknown", message, retryable = true)
}
