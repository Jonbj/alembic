package com.jonbj.alembic.monitor.core.network.dto

import kotlinx.datetime.Instant
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class DeviceInfoDto(
    @SerialName("installation_id") val installationId: String,
    val name: String,
    @SerialName("app_version") val appVersion: String
)

@Serializable
data class LoginRequest(
    val username: String,
    val password: String,
    val device: DeviceInfoDto
)

@Serializable
data class UserDto(
    val id: String,
    val username: String
)

@Serializable
data class LoginResponse(
    @SerialName("access_token") val accessToken: String,
    @SerialName("token_type") val tokenType: String,
    @SerialName("expires_in") val expiresIn: Long,
    @SerialName("refresh_token") val refreshToken: String,
    @SerialName("refresh_expires_at") val refreshExpiresAt: Instant?,
    val user: UserDto,
    @SerialName("device_id") val deviceId: String
)

@Serializable
data class RefreshRequest(
    @SerialName("refresh_token") val refreshToken: String
)

@Serializable
data class RefreshResponse(
    @SerialName("access_token") val accessToken: String,
    @SerialName("token_type") val tokenType: String,
    @SerialName("expires_in") val expiresIn: Long,
    @SerialName("refresh_token") val refreshToken: String,
    @SerialName("refresh_expires_at") val refreshExpiresAt: Instant?
)

@Serializable
data class LogoutRequest(
    @SerialName("refresh_token") val refreshToken: String? = null
)

@Serializable
data class DeviceRegistrationRequest(
    @SerialName("installation_id") val installationId: String,
    @SerialName("firebase_installation_id") val firebaseInstallationId: String? = null,
    val name: String,
    @SerialName("app_version") val appVersion: String,
    @SerialName("push_enabled") val pushEnabled: Boolean
)

@Serializable
data class DeviceRegistrationResponse(
    @SerialName("device_id") val deviceId: String,
    @SerialName("push_enabled") val pushEnabled: Boolean
)

@Serializable
data class SnapshotResponse(
    @SerialName("contract_version") val contractVersion: Int,
    @SerialName("as_of") val asOf: Instant,
    @SerialName("data_age_seconds") val dataAgeSeconds: Int,
    val currency: String,
    @SerialName("min_supported_app_version") val minSupportedAppVersion: String,
    @SerialName("latest_app_version") val latestAppVersion: String,
    val operational: OperationalDto,
    val portfolio: PortfolioDto,
    val pipeline: List<PipelineComponentDto>,
    val strategies: List<StrategyDto>,
    val degradations: List<String> = emptyList()
)

@Serializable
data class OperationalDto(
    val state: String,
    @SerialName("primary_reason") val primaryReason: String? = null,
    val mode: String,
    @SerialName("market_phase") val marketPhase: String,
    @SerialName("pipeline_expected") val pipelineExpected: Boolean,
    @SerialName("next_expected_activity_at") val nextExpectedActivityAt: Instant? = null,
    @SerialName("active_incident_count") val activeIncidentCount: Int = 0
)

@Serializable
data class PortfolioDto(
    val nav: Double? = null,
    @SerialName("nav_change_today") val navChangeToday: Double? = null,
    @SerialName("nav_return_today") val navReturnToday: Double? = null,
    @SerialName("realized_pnl_today") val realizedPnlToday: Double? = null,
    @SerialName("unrealized_pnl") val unrealizedPnl: Double? = null,
    val cash: Double? = null,
    @SerialName("cash_pct") val cashPct: Double? = null,
    @SerialName("gross_exposure") val grossExposure: Double? = null,
    @SerialName("gross_exposure_limit") val grossExposureLimit: Double? = null,
    @SerialName("current_drawdown") val currentDrawdown: Double? = null,
    @SerialName("drawdown_limit") val drawdownLimit: Double? = null,
    @SerialName("open_positions") val openPositions: Int = 0,
    val source: String
)

@Serializable
data class PipelineComponentDto(
    val status: String,
    @SerialName("age_seconds") val ageSeconds: Int = 0,
    val writeable: Boolean? = null
)

@Serializable
data class StrategyDto(
    val id: String,
    val mode: String,
    @SerialName("allocation_pct") val allocationPct: Double,
    val approved: Boolean = false
)

@Serializable
data class PerformanceResponse(
    @SerialName("contract_version") val contractVersion: Int,
    @SerialName("as_of") val asOf: Instant,
    @SerialName("data_age_seconds") val dataAgeSeconds: Int,
    val currency: String,
    val period: String,
    @SerialName("period_start") val periodStart: Instant,
    @SerialName("period_end") val periodEnd: Instant,
    val summary: PerformanceSummaryDto,
    val points: List<PerformancePointDto> = emptyList(),
    val degradations: List<String> = emptyList()
)

@Serializable
data class PerformanceSummaryDto(
    @SerialName("nav_start") val navStart: Double,
    @SerialName("nav_end") val navEnd: Double,
    @SerialName("nav_change") val navChange: Double,
    @SerialName("portfolio_return") val portfolioReturn: Double,
    @SerialName("realized_pnl") val realizedPnl: Double? = null,
    @SerialName("max_drawdown") val maxDrawdown: Double,
    @SerialName("avg_gross_exposure") val avgGrossExposure: Double? = null,
    @SerialName("spy_return") val spyReturn: Double? = null,
    @SerialName("benchmark_return") val benchmarkReturn: Double? = null,
    val alpha: Double? = null
)

@Serializable
data class PerformancePointDto(
    val at: Instant,
    val nav: Double,
    val drawdown: Double? = null,
    @SerialName("benchmark_nav") val benchmarkNav: Double? = null
)

@Serializable
data class PositionsResponse(
    @SerialName("contract_version") val contractVersion: Int,
    @SerialName("as_of") val asOf: Instant,
    @SerialName("data_age_seconds") val dataAgeSeconds: Int,
    val currency: String,
    val summary: PositionSummaryDto,
    val items: List<PositionDto> = emptyList(),
    val degradations: List<String> = emptyList()
)

@Serializable
data class PositionSummaryDto(
    val count: Int = 0,
    @SerialName("market_value") val marketValue: Double = 0.0,
    @SerialName("unrealized_pnl") val unrealizedPnl: Double = 0.0,
    @SerialName("gross_exposure") val grossExposure: Double? = null
)

@Serializable
data class PositionDto(
    val symbol: String,
    val qty: Double,
    @SerialName("avg_entry_price") val avgEntryPrice: Double,
    @SerialName("current_price") val currentPrice: Double,
    @SerialName("market_value") val marketValue: Double,
    @SerialName("position_weight") val positionWeight: Double? = null,
    @SerialName("unrealized_pnl") val unrealizedPnl: Double,
    @SerialName("unrealized_return") val unrealizedReturn: Double,
    @SerialName("entry_time") val entryTime: Instant
)

@Serializable
data class EventsResponse(
    @SerialName("contract_version") val contractVersion: Int,
    @SerialName("as_of") val asOf: Instant,
    val items: List<EventItemDto> = emptyList(),
    @SerialName("next_cursor") val nextCursor: String? = null
)

@Serializable
data class EventItemDto(
    val id: String,
    val kind: String,
    val category: String,
    val severity: String,
    val status: String,
    @SerialName("occurred_at") val occurredAt: Instant,
    @SerialName("updated_at") val updatedAt: Instant,
    @SerialName("resolved_at") val resolvedAt: Instant? = null,
    val title: String,
    val summary: String,
    val entity: EventEntityDto? = null,
    val measure: EventMeasureDto? = null,
    val history: List<EventHistoryEntryDto> = emptyList()
)

@Serializable
data class EventEntityDto(
    val type: String,
    val id: String? = null
)

@Serializable
data class EventMeasureDto(
    val value: Double,
    val unit: String,
    val threshold: Double? = null
)

@Serializable
data class EventHistoryEntryDto(
    val state: String,
    val at: Instant
)

@Serializable
data class ApiErrorResponse(
    val error: ApiErrorBody? = null
)

@Serializable
data class ApiErrorBody(
    val code: String,
    val message: String,
    @SerialName("request_id") val requestId: String? = null,
    val retryable: Boolean = true,
    val details: Map<String, String>? = null
)
