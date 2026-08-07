package com.jonbj.alembic.monitor.core.model

import kotlinx.datetime.Instant
import kotlinx.serialization.Serializable

enum class OperationalState {
    BLOCKED,
    DEGRADED,
    PAUSED,
    OPERATIONAL
}

enum class Mode {
    PAPER,
    LIVE,
    UNKNOWN
}

enum class MarketPhase {
    OPEN,
    PRE_MARKET,
    AFTER_HOURS,
    CLOSED,
    HOLIDAY
}

enum class PipelineStatus {
    FRESH,
    AGING,
    STALE,
    NOT_EXPECTED,
    UNKNOWN
}

enum class EventKind {
    ALERT_INCIDENT,
    ORDER,
    POSITION,
    DECISION
}

enum class EventCategory {
    CRITICAL,
    TRADING,
    SYSTEM
}

enum class EventSeverity {
    CRITICAL,
    WARNING,
    INFO
}

enum class EventStatus {
    OPEN,
    ESCALATED,
    RECOVERED,
    CLOSED
}

@Serializable
data class UserInfo(
    val id: String,
    val username: String
)

@Serializable
data class Session(
    val accessToken: String,
    val refreshToken: String,
    val deviceId: String,
    val user: UserInfo,
    val baseUrl: String,
    val accessExpiresAt: Instant,
    val refreshExpiresAt: Instant?
)

data class Snapshot(
    val contractVersion: Int,
    val asOf: Instant,
    val dataAgeSeconds: Int,
    val currency: String,
    val minSupportedAppVersion: String,
    val latestAppVersion: String,
    val operational: Operational,
    val portfolio: Portfolio,
    val pipeline: List<PipelineComponent>,
    val strategies: List<StrategyRow>,
    val degradations: List<String>
)

data class Operational(
    val state: OperationalState,
    val primaryReason: String?,
    val mode: Mode,
    val marketPhase: MarketPhase,
    val pipelineExpected: Boolean,
    val nextExpectedActivityAt: Instant?,
    val activeIncidentCount: Int
)

data class Portfolio(
    val nav: Double?,
    val navChangeToday: Double?,
    val navReturnToday: Double?,
    val realizedPnlToday: Double?,
    val unrealizedPnl: Double?,
    val cash: Double?,
    val cashPct: Double?,
    val grossExposure: Double?,
    val grossExposureLimit: Double?,
    val currentDrawdown: Double?,
    val drawdownLimit: Double?,
    val openPositions: Int?,
    val source: String?
)

data class PipelineComponent(
    val name: String,
    val status: PipelineStatus,
    val ageSeconds: Int,
    val writeable: Boolean? = null
)

data class StrategyRow(
    val id: String,
    val mode: Mode,
    val allocationPct: Double,
    val approved: Boolean
)

data class Performance(
    val contractVersion: Int,
    val asOf: Instant,
    val dataAgeSeconds: Int,
    val currency: String,
    val period: String,
    val periodStart: Instant,
    val periodEnd: Instant,
    val summary: PerformanceSummary,
    val points: List<PerformancePoint>,
    val degradations: List<String>
)

data class PerformanceSummary(
    val navStart: Double?,
    val navEnd: Double?,
    val navChange: Double?,
    val portfolioReturn: Double?,
    val realizedPnl: Double?,
    val maxDrawdown: Double?,
    val avgGrossExposure: Double?,
    val spyReturn: Double?,
    val benchmarkReturn: Double?,
    val alpha: Double?
)

data class PerformancePoint(
    val at: Instant,
    val nav: Double,
    val drawdown: Double?,
    val benchmarkNav: Double?
)

data class Positions(
    val contractVersion: Int,
    val asOf: Instant,
    val dataAgeSeconds: Int,
    val currency: String,
    val summary: PositionSummary,
    val items: List<Position>,
    val degradations: List<String>
)

data class PositionSummary(
    val count: Int,
    val marketValue: Double?,
    val unrealizedPnl: Double?,
    val grossExposure: Double?
)

data class Position(
    val symbol: String,
    val qty: Double,
    val avgEntryPrice: Double?,
    val currentPrice: Double?,
    val marketValue: Double?,
    val positionWeight: Double?,
    val unrealizedPnl: Double?,
    val unrealizedReturn: Double?,
    val entryTime: Instant?
)

data class EventsPage(
    val contractVersion: Int,
    val asOf: Instant,
    val items: List<EventItem>,
    val nextCursor: String?
)

data class EventItem(
    val id: String,
    val kind: EventKind,
    val category: EventCategory,
    val severity: EventSeverity,
    val status: EventStatus,
    val occurredAt: Instant,
    val updatedAt: Instant,
    val resolvedAt: Instant?,
    val title: String,
    val summary: String?,
    val entity: EventEntity?,
    val measure: EventMeasure?,
    val history: List<EventHistoryEntry>
)

data class EventEntity(
    val type: String,
    val id: String?
)

data class EventMeasure(
    val value: Double?,
    val unit: String?,
    val threshold: Double?
)

data class EventHistoryEntry(
    val state: String,
    val at: Instant
)
