package com.jonbj.alembic.monitor.core.network

import com.jonbj.alembic.monitor.core.network.dto.DeviceRegistrationRequest
import com.jonbj.alembic.monitor.core.network.dto.DeviceRegistrationResponse
import com.jonbj.alembic.monitor.core.network.dto.EventsResponse
import com.jonbj.alembic.monitor.core.network.dto.LoginRequest
import com.jonbj.alembic.monitor.core.network.dto.LoginResponse
import com.jonbj.alembic.monitor.core.network.dto.LogoutRequest
import com.jonbj.alembic.monitor.core.network.dto.PerformanceResponse
import com.jonbj.alembic.monitor.core.network.dto.PositionsResponse
import com.jonbj.alembic.monitor.core.network.dto.RefreshRequest
import com.jonbj.alembic.monitor.core.network.dto.RefreshResponse
import com.jonbj.alembic.monitor.core.network.dto.SnapshotResponse
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

interface MobileApi {

    @POST("auth/login")
    suspend fun login(@Body request: LoginRequest): Response<LoginResponse>

    @POST("auth/refresh")
    suspend fun refresh(@Body request: RefreshRequest): Response<RefreshResponse>

    @POST("auth/logout")
    suspend fun logout(@Body request: LogoutRequest? = null): Response<Unit>

    @GET("snapshot")
    suspend fun snapshot(
        @Header("If-None-Match") etag: String? = null
    ): Response<SnapshotResponse>

    @GET("performance")
    suspend fun performance(
        @Query("period") period: String,
        @Header("If-None-Match") etag: String? = null
    ): Response<PerformanceResponse>

    @GET("positions")
    suspend fun positions(
        @Header("If-None-Match") etag: String? = null
    ): Response<PositionsResponse>

    @GET("events")
    suspend fun events(
        @Query("category") category: String,
        @Query("days") days: Int,
        @Query("cursor") cursor: String? = null,
        @Query("limit") limit: Int = 50
    ): Response<EventsResponse>

    @POST("devices")
    suspend fun registerDevice(@Body request: DeviceRegistrationRequest): Response<DeviceRegistrationResponse>

    @DELETE("devices/{device_id}")
    suspend fun revokeDevice(@Path("device_id") deviceId: String): Response<Unit>
}
