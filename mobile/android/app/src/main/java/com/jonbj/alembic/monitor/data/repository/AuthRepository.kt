package com.jonbj.alembic.monitor.data.repository

import com.jonbj.alembic.monitor.core.model.MobileError
import com.jonbj.alembic.monitor.core.model.Session
import com.jonbj.alembic.monitor.core.model.UserInfo
import com.jonbj.alembic.monitor.core.network.MobileApiProvider
import com.jonbj.alembic.monitor.core.network.ServerUrlPolicy
import com.jonbj.alembic.monitor.core.network.dto.DeviceInfoDto
import com.jonbj.alembic.monitor.core.network.dto.LoginRequest
import com.jonbj.alembic.monitor.core.network.dto.LogoutRequest
import com.jonbj.alembic.monitor.core.network.dto.RefreshRequest
import com.jonbj.alembic.monitor.core.security.SessionVault
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.datetime.Clock
import kotlin.time.Duration.Companion.seconds

interface TokenRefresher {
    fun currentAccessToken(): String?
    suspend fun refreshAccessToken(failedAccessToken: String?): Result<Unit>
    suspend fun invalidateSession()
}

class AuthRepository(
    private val apiProvider: MobileApiProvider,
    private val vault: SessionVault,
    private val serverUrlPolicy: ServerUrlPolicy,
    private val appVersion: String,
    private val clearLocalData: suspend () -> Unit
) : TokenRefresher {

    private val refreshMutex = Mutex()

    suspend fun login(
        serverUrl: String,
        username: String,
        password: String,
        installationId: String,
        deviceName: String
    ): Result<Session> {
        val baseUrl = serverUrlPolicy.normalize(serverUrl).getOrElse {
            return Result.failure(
                MobileError.Http(400, it.message ?: "Indirizzo server non valido")
            )
        }
        val device = DeviceInfoDto(
            installationId = installationId,
            name = deviceName,
            appVersion = appVersion
        )
        return try {
            val api = apiProvider.forBaseUrl(baseUrl)
            val response = api.login(LoginRequest(username, password, device))
            if (response.isSuccessful) {
                val body = response.body()
                    ?: return Result.failure(MobileError.Http(200, "Empty login response"))
                val session = body.toSession(baseUrl)
                vault.save(session)
                Result.success(session)
            } else {
                Result.failure(mapError(response))
            }
        } catch (e: Exception) {
            Result.failure(MobileError.Network(e.message ?: "Network error"))
        }
    }

    override fun currentAccessToken(): String? = vault.getBlocking()?.accessToken

    override suspend fun invalidateSession() {
        clearLocalData()
    }

    override suspend fun refreshAccessToken(failedAccessToken: String?): Result<Unit> =
        refreshMutex.withLock {
            val current = vault.get()
                ?: return@withLock Result.failure(
                    MobileError.Auth("No session", requireRelogin = true)
                )
            if (failedAccessToken != null && current.accessToken != failedAccessToken) {
                return@withLock Result.success(Unit)
            }
            try {
                val api = apiProvider.forBaseUrl(current.baseUrl)
                val response = api.refresh(RefreshRequest(current.refreshToken))
                if (response.isSuccessful) {
                    val body = response.body()
                        ?: return@withLock Result.failure(
                            MobileError.Http(200, "Empty refresh response")
                        )
                    val updated = current.copy(
                        accessToken = body.accessToken,
                        refreshToken = body.refreshToken,
                        accessExpiresAt = Clock.System.now() + body.expiresIn.seconds,
                        refreshExpiresAt = body.refreshExpiresAt
                    )
                    vault.save(updated)
                    Result.success(Unit)
                } else {
                    if (response.code() == 401 || response.code() == 409) {
                        clearLocalData()
                        Result.failure(
                            MobileError.Auth("Session revoked", requireRelogin = true)
                        )
                    } else {
                        Result.failure(mapError(response))
                    }
                }
            } catch (e: Exception) {
                Result.failure(MobileError.Network(e.message ?: "Network error"))
            }
        }

    suspend fun logout(): Result<Unit> {
        val current = vault.get()
        val result = try {
            if (current == null) {
                Result.success(Unit)
            } else {
                val response = apiProvider.forBaseUrl(current.baseUrl)
                    .logout(LogoutRequest(current.refreshToken))
                if (response.isSuccessful) Result.success(Unit)
                else Result.failure(mapError(response))
            }
        } catch (e: Exception) {
            Result.failure(MobileError.Network(e.message ?: "Network error"))
        } finally {
            clearLocalData()
        }
        return result
    }

    private fun mapError(response: retrofit2.Response<*>): MobileError {
        val code = response.code()
        val body = response.errorBody()?.string()
        return if (code == 401) {
            MobileError.Auth("Authentication required", requireRelogin = true)
        } else if (code == 426) {
            MobileError.Version("App update required")
        } else {
            MobileError.Http(code, body ?: "HTTP error", serverCode = null)
        }
    }

    private fun com.jonbj.alembic.monitor.core.network.dto.LoginResponse.toSession(baseUrl: String): Session {
        val now = Clock.System.now()
        return Session(
            accessToken = accessToken,
            refreshToken = refreshToken,
            deviceId = deviceId,
            user = UserInfo(user.id, user.username),
            baseUrl = baseUrl,
            accessExpiresAt = now + expiresIn.seconds,
            refreshExpiresAt = refreshExpiresAt
        )
    }
}
