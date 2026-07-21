"""Domain contract models for the /api/mobile/v1 read-only monitor.

These Pydantic v2 models encode the approved payloads in
`docs/superpowers/specs/2026-07-21-android-monitoring-app-design.md`. They are
used by the API route layer and by the Android-facing fixture tests.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OperationalState(StrEnum):
    """Server-derived operational state, ordered by severity."""

    BLOCKED = "blocked"
    DEGRADED = "degraded"
    PAUSED = "paused"
    OPERATIONAL = "operational"


class MarketPhase(StrEnum):
    """Market calendar phase from the authoritative source."""

    OPEN = "open"
    PRE_MARKET = "pre_market"
    AFTER_HOURS = "after_hours"
    CLOSED = "closed"
    HOLIDAY = "holiday"


class Freshness(StrEnum):
    """Freshness classification returned by the server."""

    FRESH = "fresh"
    AGING = "aging"
    STALE = "stale"
    NOT_EXPECTED = "not_expected"
    UNKNOWN = "unknown"


class Severity(StrEnum):
    """Incident / degradation severity."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class EventStatus(StrEnum):
    """Lifecycle state of an operator event / alert incident."""

    OPEN = "open"
    ESCALATED = "escalated"
    RECOVERED = "recovered"
    CLOSED = "closed"


class EventCategory(StrEnum):
    """Filterable event category."""

    ALL = "all"
    CRITICAL = "critical"
    TRADING = "trading"
    SYSTEM = "system"


class EventKind(StrEnum):
    """Kind of operator event."""

    ALERT_INCIDENT = "alert_incident"
    ORDER = "order"
    POSITION = "position"
    DECISION = "decision"


class Period(StrEnum):
    """Performance period selector."""

    ONE_WEEK = "1w"
    ONE_MONTH = "1m"
    THREE_MONTHS = "3m"
    SIX_MONTHS = "6m"
    ONE_YEAR = "1y"
    ALL = "all"


class MobileReadResponse(BaseModel):
    """Fields present on every successful read response."""

    model_config = ConfigDict(extra="allow")

    contract_version: int = Field(default=1, ge=1)
    as_of: datetime
    data_age_seconds: int = Field(..., ge=0)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    min_supported_app_version: str
    latest_app_version: str


class PipelineComponent(BaseModel):
    """Health/freshness of one infrastructure component."""

    status: Freshness
    age_seconds: int = Field(..., ge=0)
    writeable: bool | None = None


class OperationalBlock(BaseModel):
    """Operational-state block of the monitoring snapshot."""

    state: OperationalState
    primary_reason: str | None = None
    mode: str
    market_phase: MarketPhase
    pipeline_expected: bool
    next_expected_activity_at: datetime | None = None
    active_incident_count: int = Field(..., ge=0)


class PortfolioBlock(BaseModel):
    """Portfolio block of the monitoring snapshot.

    All financial values stay nullable so the API never substitutes zero for
    unavailable broker data.
    """

    nav: Decimal | None = None
    nav_change_today: Decimal | None = None
    nav_return_today: float | None = None
    realized_pnl_today: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    cash: Decimal | None = None
    cash_pct: float | None = None
    gross_exposure: float | None = None
    gross_exposure_limit: float | None = None
    current_drawdown: float | None = None
    drawdown_limit: float | None = None
    open_positions: int | None = None
    source: str | None = None


class StrategyRow(BaseModel):
    """Read-only strategy summary in the snapshot."""

    id: str
    mode: str
    allocation_pct: float = Field(..., ge=0, le=1)
    approved: bool


class Degradation(BaseModel):
    """Named degradation attached to a read response."""

    component: str
    reason: str
    severity: Severity | None = None


class SnapshotResponse(MobileReadResponse):
    """GET /api/mobile/v1/snapshot response body."""

    operational: OperationalBlock
    portfolio: PortfolioBlock
    pipeline: dict[str, PipelineComponent]
    strategies: list[StrategyRow]
    degradations: list[Degradation]


class PerformanceSummary(BaseModel):
    """Period summary for the performance endpoint."""

    nav_start: Decimal | None = None
    nav_end: Decimal | None = None
    nav_change: Decimal | None = None
    portfolio_return: float | None = None
    realized_pnl: Decimal | None = None
    max_drawdown: float | None = None
    avg_gross_exposure: float | None = None
    spy_return: float | None = None
    benchmark_return: float | None = None
    alpha: float | None = None


class PerformancePoint(BaseModel):
    """One NAV / drawdown / benchmark point on the performance curve."""

    at: datetime
    nav: Decimal
    drawdown: float | None = None
    benchmark_nav: Decimal | None = None


class PerformanceResponse(MobileReadResponse):
    """GET /api/mobile/v1/performance response body."""

    period: str
    period_start: datetime
    period_end: datetime
    summary: PerformanceSummary
    points: list[PerformancePoint]


class PositionItem(BaseModel):
    """One open position as returned by the positions endpoint."""

    symbol: str
    qty: float
    avg_entry_price: Decimal | None = None
    current_price: Decimal | None = None
    market_value: Decimal | None = None
    position_weight: float | None = None
    unrealized_pnl: Decimal | None = None
    unrealized_return: float | None = None
    entry_time: datetime | None = None


class PositionsSummary(BaseModel):
    """Aggregate positions data."""

    count: int = Field(..., ge=0)
    market_value: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    gross_exposure: float | None = None


class PositionsResponse(MobileReadResponse):
    """GET /api/mobile/v1/positions response body."""

    summary: PositionsSummary
    items: list[PositionItem]


class EventEntity(BaseModel):
    """Entity referenced by an operator event (portfolio_cycle, order, ...)."""

    type: str
    id: str | None = None


class EventMeasure(BaseModel):
    """Numeric measure that triggered or quantifies an event."""

    value: float | None = None
    unit: str | None = None
    threshold: float | None = None


class EventHistoryEntry(BaseModel):
    """One state transition in an incident timeline."""

    state: str
    at: datetime


class EventItem(BaseModel):
    """One operator event / alert incident."""

    id: UUID
    kind: EventKind
    category: EventCategory
    severity: Severity
    status: EventStatus
    occurred_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None
    title: str
    summary: str | None = None
    entity: EventEntity | None = None
    measure: EventMeasure | None = None
    history: list[EventHistoryEntry]


class EventsResponse(MobileReadResponse):
    """GET /api/mobile/v1/events response body."""

    items: list[EventItem]
    next_cursor: str | None = None


class DeviceResponse(BaseModel):
    """Registered device representation."""

    id: UUID
    installation_id: str
    firebase_installation_id: str | None = None
    name: str
    app_version: str
    push_enabled: bool
    created_at: datetime | None = None
    last_seen_at: datetime | None = None


class MobileError(BaseModel):
    """Standard error envelope returned by /api/mobile/v1."""

    code: str
    message: str
    request_id: UUID | None = None
    retryable: bool = False
    details: dict[str, Any] | None = None


class MobileErrorResponse(BaseModel):
    """Top-level error response wrapper."""

    error: MobileError
