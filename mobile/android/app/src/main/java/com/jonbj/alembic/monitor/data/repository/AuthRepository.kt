package com.jonbj.alembic.monitor.data.repository

import com.jonbj.alembic.monitor.core.model.MobileError
import com.jonbj.alembic.monitor.core.model.Session
import com.jonbj.alembic.monitor.core.model.UserInfo
import com.jonbj.alembic.monitor.core.network.MobileApi
import com.jonbj.alembic.monitor.core.network.dto.DeviceInfoDto
import com.jonbj.alembic.monitor.core.network.dto.LoginRequest
import com.jonbj.alembic.monitor.core.network.dto.LogoutRequest
import com.jonbj.alembic.monitor.core.network.dto.RefreshRequest
import com.jonbj.alembic.monitor.core.security.SessionVault
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.datetime.Clock
import kotlinx.datetime.Instant
import kotlin.time.Duration.Companion.seconds

interface TokenRefresher {
    suspend fun refreshAccessToken(): Result<Unit>
}

class AuthRepository(
    private val api: MobileApi,
    private val vault: SessionVault,
    private val baseUrl: String,
    private val appVersion: String
) : TokenRefresher {

    private val refreshMutex = Mutex()

    suspend fun login(
        username: String,
        password: String,
        installationId: String,
        deviceName: String
    ): Result<Session> {
        val device = DeviceInfoDto(
            installationId = installationId,
            name = deviceName,
            appVersion = appVersion
        )
        return try {
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

    override suspend fun refreshAccessToken(): Result<Unit> = refreshMutex.withLock {
        val current = vault.get()
            ?: return Result.failure(MobileError.Auth("No session", requireRelogin = true))
        return try {
            val response = api.refresh(RefreshRequest(current.refreshToken))
            if (response.isSuccessful) {
                val body = response.body()
                    ?: return Result.failure(MobileError.Http(200, "Empty refresh response"))
                val updated = current.copy(
                    accessToken = body.accessToken,
                    refreshToken = body.refreshToken,
                    accessExpiresAt = Clock.System.now() + body.expiresIn.seconds
                )
                vault.save(updated)
                Result.success(Unit)
            } else {
                if (response.code() == 409) {
                    vault.clear()
                    Result.failure(MobileError.Auth("Session revoked", requireRelogin = true))
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
        return try {
            current?.let { api.logout(LogoutRequest(it.refreshToken)) }
            vault.clear()
            Result.success(Unit)
        } catch (e: Exception) {
            vault.clear()
            Result.success(Unit)
        }
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
