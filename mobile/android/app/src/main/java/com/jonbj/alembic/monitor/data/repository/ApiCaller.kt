package com.jonbj.alembic.monitor.data.repository

import com.jonbj.alembic.monitor.core.model.MobileError
import retrofit2.Response

object ApiCaller {

    suspend fun <T> execute(
        refresher: TokenRefresher,
        call: suspend () -> Response<T>
    ): Result<T> {
        val failedAccessToken = refresher.currentAccessToken()
        val first = executeOnce(call)
        if (first.isSuccess || first.exceptionOrNull()?.isAuth() != true) {
            return first
        }

        val refreshResult = refresher.refreshAccessToken(failedAccessToken)
        if (refreshResult.isFailure) {
            return Result.failure(refreshResult.exceptionOrNull() ?: MobileError.Auth("Refresh failed"))
        }
        val retried = executeOnce(call)
        if (retried.exceptionOrNull()?.isAuth() == true) {
            refresher.invalidateSession()
        }
        return retried
    }

    private suspend fun <T> executeOnce(call: suspend () -> Response<T>): Result<T> {
        return try {
            val response = call()
            when {
                response.isSuccessful -> {
                    @Suppress("UNCHECKED_CAST")
                    Result.success(response.body() as T)
                }
                response.code() == 401 -> Result.failure(MobileError.Auth("Unauthorized", requireRelogin = true))
                response.code() == 426 -> Result.failure(MobileError.Version("Application update required"))
                response.code() in 500..599 -> Result.failure(
                    MobileError.Http(response.code(), response.errorBody()?.string() ?: "Server error")
                )
                else -> Result.failure(
                    MobileError.Http(response.code(), response.errorBody()?.string() ?: "HTTP error")
                )
            }
        } catch (e: Exception) {
            Result.failure(MobileError.Network(e.message ?: "Network error"))
        }
    }

    private fun Throwable.isAuth(): Boolean = this is MobileError.Auth
}
