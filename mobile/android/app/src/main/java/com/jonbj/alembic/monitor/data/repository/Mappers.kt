package com.jonbj.alembic.monitor.data.repository

import com.jonbj.alembic.monitor.core.model.DataSource
import com.jonbj.alembic.monitor.core.model.ContentMode
import com.jonbj.alembic.monitor.core.model.MobileError
import com.jonbj.alembic.monitor.core.model.EventCategory
import com.jonbj.alembic.monitor.core.model.EventEntity
import com.jonbj.alembic.monitor.core.model.EventHistoryEntry
import com.jonbj.alembic.monitor.core.model.EventItem
import com.jonbj.alembic.monitor.core.model.EventKind
import com.jonbj.alembic.monitor.core.model.EventMeasure
import com.jonbj.alembic.monitor.core.model.EventSeverity
import com.jonbj.alembic.monitor.core.model.EventStatus
import com.jonbj.alembic.monitor.core.model.LoadState
import com.jonbj.alembic.monitor.core.model.MarketPhase
import com.jonbj.alembic.monitor.core.model.Mode
import com.jonbj.alembic.monitor.core.model.Operational
import com.jonbj.alembic.monitor.core.model.OperationalState
import com.jonbj.alembic.monitor.core.model.Performance
import com.jonbj.alembic.monitor.core.model.PerformancePoint
import com.jonbj.alembic.monitor.core.model.PerformanceSummary
import com.jonbj.alembic.monitor.core.model.PipelineComponent
import com.jonbj.alembic.monitor.core.model.PipelineStatus
import com.jonbj.alembic.monitor.core.model.Portfolio
import com.jonbj.alembic.monitor.core.model.Position
import com.jonbj.alembic.monitor.core.model.PositionSummary
import com.jonbj.alembic.monitor.core.model.Positions
import com.jonbj.alembic.monitor.core.model.Snapshot
import com.jonbj.alembic.monitor.core.model.StrategyRow
import com.jonbj.alembic.monitor.core.network.dto.EventItemDto
import com.jonbj.alembic.monitor.core.network.dto.OperationalDto
import com.jonbj.alembic.monitor.core.network.dto.PerformanceResponse
import com.jonbj.alembic.monitor.core.network.dto.PipelineComponentDto
import com.jonbj.alembic.monitor.core.network.dto.PortfolioDto
import com.jonbj.alembic.monitor.core.network.dto.PositionDto
import com.jonbj.alembic.monitor.core.network.dto.PositionsResponse
import com.jonbj.alembic.monitor.core.network.dto.SnapshotResponse
import com.jonbj.alembic.monitor.core.network.dto.StrategyDto

fun SnapshotResponse.toDomain(): Snapshot = Snapshot(
    contractVersion = contractVersion,
    asOf = asOf,
    dataAgeSeconds = dataAgeSeconds,
    currency = currency,
    minSupportedAppVersion = minSupportedAppVersion,
    latestAppVersion = latestAppVersion,
    operational = operational.toDomain(),
    portfolio = portfolio.toDomain(),
    pipeline = pipeline.map { (name, dto) -> dto.toDomain(name) },
    strategies = strategies.map { it.toDomain() },
    degradations = degradations.map { "${it.component}:${it.reason}" }
)

private fun OperationalDto.toDomain(): Operational = Operational(
    state = parseOperationalState(state),
    primaryReason = primaryReason,
    mode = parseMode(mode),
    marketPhase = parseMarketPhase(marketPhase),
    pipelineExpected = pipelineExpected,
    nextExpectedActivityAt = nextExpectedActivityAt,
    activeIncidentCount = activeIncidentCount
)

private fun PortfolioDto.toDomain(): Portfolio = Portfolio(
    nav = nav,
    navChangeToday = navChangeToday,
    navReturnToday = navReturnToday,
    realizedPnlToday = realizedPnlToday,
    unrealizedPnl = unrealizedPnl,
    cash = cash,
    cashPct = cashPct,
    grossExposure = grossExposure,
    grossExposureLimit = grossExposureLimit,
    currentDrawdown = currentDrawdown,
    drawdownLimit = drawdownLimit,
    openPositions = openPositions,
    source = source
)

private fun PipelineComponentDto.toDomain(name: String): PipelineComponent = PipelineComponent(
    name = name,
    status = parsePipelineStatus(status),
    ageSeconds = ageSeconds,
    writeable = writeable
)

private fun StrategyDto.toDomain(): StrategyRow = StrategyRow(
    id = id,
    mode = mode,
    allocationPct = allocationPct,
    approved = approved
)

fun PerformanceResponse.toDomain(): Performance = Performance(
    contractVersion = contractVersion,
    asOf = asOf,
    dataAgeSeconds = dataAgeSeconds,
    currency = currency,
    period = period,
    periodStart = periodStart,
    periodEnd = periodEnd,
    summary = PerformanceSummary(
        navStart = summary.navStart,
        navEnd = summary.navEnd,
        navChange = summary.navChange,
        portfolioReturn = summary.portfolioReturn,
        realizedPnl = summary.realizedPnl,
        maxDrawdown = summary.maxDrawdown,
        avgGrossExposure = summary.avgGrossExposure,
        spyReturn = summary.spyReturn,
        benchmarkReturn = summary.benchmarkReturn,
        alpha = summary.alpha
    ),
    points = points.map { PerformancePoint(it.at, it.nav, it.drawdown, it.benchmarkNav) },
    degradations = degradations.map { "${it.component}:${it.reason}" }
)

fun PositionsResponse.toDomain(): Positions = Positions(
    contractVersion = contractVersion,
    asOf = asOf,
    dataAgeSeconds = dataAgeSeconds,
    currency = currency,
    summary = PositionSummary(
        count = summary.count,
        marketValue = summary.marketValue,
        unrealizedPnl = summary.unrealizedPnl,
        grossExposure = summary.grossExposure
    ),
    items = items.map { it.toDomain() },
    degradations = degradations.map { "${it.component}:${it.reason}" }
)

private fun PositionDto.toDomain(): Position = Position(
    symbol = symbol,
    qty = qty,
    avgEntryPrice = avgEntryPrice,
    currentPrice = currentPrice,
    marketValue = marketValue,
    positionWeight = positionWeight,
    unrealizedPnl = unrealizedPnl,
    unrealizedReturn = unrealizedReturn,
    entryTime = entryTime
)

fun List<EventItemDto>.toEventsDomain(): List<EventItem> = map { it.toDomain() }

private fun EventItemDto.toDomain(): EventItem = EventItem(
    id = id,
    kind = parseEventKind(kind),
    category = parseEventCategory(category),
    severity = parseEventSeverity(severity),
    status = parseEventStatus(status),
    occurredAt = occurredAt,
    updatedAt = updatedAt,
    resolvedAt = resolvedAt,
    title = title,
    summary = summary,
    entity = entity?.let { EventEntity(it.type, it.id) },
    measure = measure?.let { EventMeasure(it.value, it.unit, it.threshold) },
    history = history.map { EventHistoryEntry(it.state, it.at) }
)

private fun parseOperationalState(value: String): OperationalState =
    OperationalState.entries.find { it.name.equals(value, ignoreCase = true) }
        ?: OperationalState.BLOCKED

private fun parseMode(value: String): Mode =
    Mode.entries.find { it.name.equals(value, ignoreCase = true) } ?: Mode.UNKNOWN

private fun parseMarketPhase(value: String): MarketPhase =
    MarketPhase.entries.find { it.name.equals(value, ignoreCase = true) } ?: MarketPhase.CLOSED

private fun parsePipelineStatus(value: String): PipelineStatus =
    PipelineStatus.entries.find { it.name.equals(value, ignoreCase = true) } ?: PipelineStatus.UNKNOWN

private fun parseEventKind(value: String): EventKind =
    EventKind.entries.find { it.name.equals(value, ignoreCase = true) } ?: EventKind.ALERT_INCIDENT

private fun parseEventCategory(value: String): EventCategory =
    EventCategory.entries.find { it.name.equals(value, ignoreCase = true) } ?: EventCategory.SYSTEM

private fun parseEventSeverity(value: String): EventSeverity =
    EventSeverity.entries.find { it.name.equals(value, ignoreCase = true) } ?: EventSeverity.INFO

private fun parseEventStatus(value: String): EventStatus =
    EventStatus.entries.find { it.name.equals(value, ignoreCase = true) } ?: EventStatus.OPEN

internal fun <T> successFromNetwork(data: T, dataAgeSeconds: Int): LoadState.Success<T> =
    LoadState.Success(data, DataSource.NETWORK, dataAgeSeconds)

internal fun <T> successFromCache(data: T, dataAgeSeconds: Int): LoadState.Success<T> =
    LoadState.Success(
        data,
        DataSource.CACHE,
        dataAgeSeconds,
        if (dataAgeSeconds > STALE_AFTER_SECONDS) ContentMode.STALE else ContentMode.OFFLINE
    )

internal fun <T> failureState(
    error: Throwable,
    cached: T? = null,
    cachedAgeSeconds: Int? = null
): LoadState<T> = when (error) {
    is MobileError.Version -> LoadState.Error(
        message = "Aggiornamento obbligatorio",
        cached = cached,
        source = cached?.let { DataSource.CACHE },
        dataAgeSeconds = cachedAgeSeconds,
        retryable = false,
        mode = ContentMode.INCOMPATIBLE
    )
    is MobileError.Auth -> LoadState.Error(
        message = "Sessione scaduta",
        retryable = false,
        mode = ContentMode.UNAUTHENTICATED
    )
    else -> if (cached != null && cachedAgeSeconds != null) {
        successFromCache(cached, cachedAgeSeconds)
    } else {
        LoadState.Error(
            message = error.message ?: "Errore imprevisto",
            retryable = (error as? MobileError)?.retryable ?: true,
            mode = ContentMode.UNAVAILABLE
        )
    }
}

internal const val STALE_AFTER_SECONDS = 5 * 60
