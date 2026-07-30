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
import kotlinx.datetime.Clock
import retrofit2.Response

class FakeMobileApi : MobileApi {

    var snapshotResponse: Response<SnapshotResponse>? = null
    var performanceResponse: Response<PerformanceResponse>? = null
    var positionsResponse: Response<PositionsResponse>? = null
    var eventsResponse: Response<EventsResponse>? = null
    var loginResponse: Response<LoginResponse>? = null
    var refreshResponse: Response<RefreshResponse>? = null
    var logoutResponse: Response<Unit>? = null
    var deviceRegistrationResponse: Response<DeviceRegistrationResponse>? = null
    var snapshotHandler: (suspend () -> Response<SnapshotResponse>)? = null
    var eventsHandler: (suspend (String, Int, String?, Int) -> Response<EventsResponse>)? = null
    val deviceRegistrations = mutableListOf<DeviceRegistrationRequest>()
    val revokedDevices = mutableListOf<String>()

    override suspend fun login(request: LoginRequest): Response<LoginResponse> {
        return loginResponse ?: Response.success(
            LoginResponse(
                accessToken = "access",
                tokenType = "bearer",
                expiresIn = 900,
                refreshToken = "refresh",
                refreshExpiresAt = null,
                user = com.jonbj.alembic.monitor.core.network.dto.UserDto("u1", request.username),
                deviceId = "d1"
            )
        )
    }

    override suspend fun refresh(request: RefreshRequest): Response<RefreshResponse> {
        return refreshResponse ?: Response.success(
            RefreshResponse(
                accessToken = "new_access",
                tokenType = "bearer",
                expiresIn = 900,
                refreshToken = "new_refresh",
                refreshExpiresAt = null
            )
        )
    }

    override suspend fun logout(request: LogoutRequest?): Response<Unit> {
        return logoutResponse ?: Response.success(Unit)
    }

    override suspend fun snapshot(etag: String?): Response<SnapshotResponse> {
        snapshotHandler?.let { return it() }
        return snapshotResponse ?: Response.success(
            SnapshotResponse(
                contractVersion = 1,
                asOf = Clock.System.now(),
                dataAgeSeconds = 0,
                currency = "USD",
                minSupportedAppVersion = "1.0.0",
                latestAppVersion = "1.0.0",
                operational = com.jonbj.alembic.monitor.core.network.dto.OperationalDto(
                    state = "operational",
                    mode = "paper",
                    marketPhase = "open",
                    pipelineExpected = true
                ),
                portfolio = com.jonbj.alembic.monitor.core.network.dto.PortfolioDto(
                    nav = 100000.0,
                    source = "alpaca_paper"
                ),
                pipeline = mapOf(
                    "database" to
                        com.jonbj.alembic.monitor.core.network.dto.PipelineComponentDto("fresh", 0)
                ),
                strategies = emptyList()
            )
        )
    }

    override suspend fun performance(period: String, etag: String?): Response<PerformanceResponse> {
        return performanceResponse ?: Response.success(
            PerformanceResponse(
                contractVersion = 1,
                asOf = Clock.System.now(),
                dataAgeSeconds = 0,
                currency = "USD",
                period = period,
                periodStart = Clock.System.now(),
                periodEnd = Clock.System.now(),
                summary = com.jonbj.alembic.monitor.core.network.dto.PerformanceSummaryDto(
                    navStart = 100000.0,
                    navEnd = 100100.0,
                    navChange = 100.0,
                    portfolioReturn = 0.001,
                    maxDrawdown = 0.0
                )
            )
        )
    }

    override suspend fun positions(etag: String?): Response<PositionsResponse> {
        return positionsResponse ?: Response.success(
            PositionsResponse(
                contractVersion = 1,
                asOf = Clock.System.now(),
                dataAgeSeconds = 0,
                currency = "USD",
                summary = com.jonbj.alembic.monitor.core.network.dto.PositionSummaryDto(
                    count = 0,
                    marketValue = 0.0,
                    unrealizedPnl = 0.0
                )
            )
        )
    }

    override suspend fun events(
        category: String,
        days: Int,
        cursor: String?,
        limit: Int
    ): Response<EventsResponse> {
        eventsHandler?.let { return it(category, days, cursor, limit) }
        return eventsResponse ?: Response.success(
            EventsResponse(
                contractVersion = 1,
                asOf = Clock.System.now(),
                dataAgeSeconds = 0,
                currency = "USD",
                minSupportedAppVersion = "1.0.0",
                latestAppVersion = "1.0.0",
                items = emptyList()
            )
        )
    }

    override suspend fun registerDevice(request: DeviceRegistrationRequest): Response<DeviceRegistrationResponse> {
        deviceRegistrations += request
        deviceRegistrationResponse?.let { return it }
        return Response.success(
            DeviceRegistrationResponse(
                com.jonbj.alembic.monitor.core.network.dto.DeviceDto(
                    id = "d1",
                    installationId = request.installationId,
                    name = request.name,
                    appVersion = request.appVersion,
                    firebaseInstallationId = request.firebaseInstallationId,
                    pushEnabled = request.pushEnabled
                )
            )
        )
    }

    override suspend fun revokeDevice(deviceId: String): Response<Unit> {
        revokedDevices += deviceId
        return Response.success(Unit)
    }
}
