"""Coherent mobile monitoring snapshot builder.

The builder assembles the read-only mobile view from Alpaca, Redis, Postgres, and
the strategy registry. It keeps financial fields nullable when broker data is
unavailable and reports degradations rather than substituting zeros.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import asyncpg
from alpaca.trading.client import TradingClient

from src.api.deps import get_redis_store
from src.config import config
from src.mobile_monitoring.models import (
    Degradation,
    EventCategory,
    EventItem,
    Freshness,
    MarketPhase,
    OperationalState,
    OperationalBlock,
    PerformancePoint,
    PerformanceResponse,
    PerformanceSummary,
    PipelineComponent,
    PortfolioBlock,
    PositionItem,
    PositionsResponse,
    PositionsSummary,
    Severity,
    SnapshotResponse,
    StrategyRow,
)

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _classify_age(age_seconds: int | None, thresholds: tuple[int, int]) -> Freshness:
    if age_seconds is None:
        return Freshness.UNKNOWN
    fresh, aging = thresholds
    if age_seconds <= fresh:
        return Freshness.FRESH
    if age_seconds <= aging:
        return Freshness.AGING
    return Freshness.STALE


class MobileSnapshotBuilder:
    """Assemble a coherent monitoring snapshot for /api/mobile/v1/snapshot."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        alpaca: TradingClient | None = None,
        redis=None,
    ):
        self.pool = pool
        self.alpaca = alpaca or TradingClient(
            api_key=config.ALPACA_API_KEY,
            secret_key=config.ALPACA_SECRET_KEY,
            paper=config.ALPACA_PAPER_MODE,
        )
        self.redis = redis or get_redis_store()

    async def build_snapshot(self, as_of: datetime | None = None) -> SnapshotResponse:
        as_of = as_of or _now()
        degradations: list[Degradation] = []

        # --- operational state ------------------------------------------------
        operational, mode, market_phase, pipeline_expected, next_activity = await self._operational_state(
            as_of, degradations
        )

        # --- broker data ------------------------------------------------------
        account, positions, broker_age = await self._broker_snapshot(as_of, degradations)
        portfolio = self._build_portfolio(account, positions, broker_age, degradations)

        # --- pipeline health --------------------------------------------------
        pipeline = await self._build_pipeline(as_of, account, positions, degradations)

        # --- strategies -------------------------------------------------------
        strategies = self._build_strategies(degradations)

        return SnapshotResponse(
            as_of=as_of,
            data_age_seconds=0,
            currency="USD",
            min_supported_app_version=config.MIN_SUPPORTED_MOBILE_APP_VERSION,
            latest_app_version=config.LATEST_MOBILE_APP_VERSION,
            operational=operational,
            portfolio=portfolio,
            pipeline=pipeline,
            strategies=strategies,
            degradations=degradations,
        )

    async def build_positions(self, as_of: datetime | None = None) -> PositionsResponse:
        as_of = as_of or _now()
        _, positions, _ = await self._broker_snapshot(as_of, [])
        items: list[PositionItem] = []
        total_market_value = Decimal("0")
        total_unrealized = Decimal("0")
        for p in positions:
            qty = _to_float(getattr(p, "qty", None)) or 0.0
            market_value = _to_decimal(getattr(p, "market_value", None))
            unrealized = _to_decimal(getattr(p, "unrealized_pl", None))
            entry_price = _to_decimal(getattr(p, "avg_entry_price", None))
            current_price = _to_decimal(getattr(p, "current_price", None))
            if market_value is not None:
                total_market_value += market_value
            if unrealized is not None:
                total_unrealized += unrealized
            items.append(
                PositionItem(
                    symbol=str(getattr(p, "symbol", "")),
                    qty=qty,
                    avg_entry_price=entry_price,
                    current_price=current_price,
                    market_value=market_value,
                    position_weight=None,
                    unrealized_pnl=unrealized,
                    unrealized_return=None,
                    entry_time=None,
                )
            )
        account = await self._account()
        equity = _to_decimal(getattr(account, "equity", None)) or Decimal("0")
        gross_exposure = (
            float(total_market_value / equity) if equity and equity > 0 else None
        )
        for item in items:
            if gross_exposure is not None and gross_exposure > 0 and item.market_value is not None:
                item.position_weight = float(item.market_value / equity) if equity else None
        return PositionsResponse(
            as_of=as_of,
            data_age_seconds=0,
            currency="USD",
            min_supported_app_version=config.MIN_SUPPORTED_MOBILE_APP_VERSION,
            latest_app_version=config.LATEST_MOBILE_APP_VERSION,
            summary=PositionsSummary(
                count=len(items),
                market_value=total_market_value or None,
                unrealized_pnl=total_unrealized or None,
                gross_exposure=gross_exposure,
            ),
            items=items,
        )

    async def build_performance(
        self, period: str, as_of: datetime | None = None
    ) -> PerformanceResponse:
        as_of = as_of or _now()
        account = await self._account()
        nav_end = _to_decimal(getattr(account, "equity", None))
        summary = PerformanceSummary(nav_end=nav_end)
        return PerformanceResponse(
            as_of=as_of,
            data_age_seconds=0,
            currency="USD",
            min_supported_app_version=config.MIN_SUPPORTED_MOBILE_APP_VERSION,
            latest_app_version=config.LATEST_MOBILE_APP_VERSION,
            period=period,
            period_start=as_of - timedelta(days=30),
            period_end=as_of,
            summary=summary,
            points=[PerformancePoint(at=as_of, nav=nav_end or Decimal("0"))],
        )

    # --- internal helpers -------------------------------------------------

    async def _operational_state(
        self, as_of: datetime, degradations: list[Degradation]
    ) -> tuple[OperationalBlock, str, MarketPhase, bool, datetime | None]:
        mode = "paper" if config.ALPACA_PAPER_MODE else "live"
        market_phase = MarketPhase.CLOSED
        pipeline_expected = True
        next_activity: datetime | None = None
        active_incidents = 0

        try:
            clock = await asyncio.to_thread(self.alpaca.get_clock)
            if clock.is_open:
                market_phase = MarketPhase.OPEN
            else:
                # Heuristic: within 1h before next_open = pre-market, after last_close = after-hours.
                next_open = getattr(clock, "next_open", None)
                next_close = getattr(clock, "next_close", None)
                if next_open:
                    gap = (next_open - as_of).total_seconds()
                    if 0 < gap <= 3600:
                        market_phase = MarketPhase.PRE_MARKET
                    elif next_close and as_of > next_close:
                        market_phase = MarketPhase.AFTER_HOURS
                next_activity = next_open
        except Exception as exc:
            logger.warning("Mobile snapshot: could not read market clock: %s", exc)
            degradations.append(
                Degradation(
                    component="market_clock",
                    reason="Market clock unavailable",
                    severity=Severity.WARNING,
                )
            )

        # Killswitch state via Redis.
        killswitch_active = False
        try:
            killswitch_active = bool(self.redis.is_killswitch_active())
        except Exception as exc:
            logger.warning("Mobile snapshot: could not read killswitch: %s", exc)
            degradations.append(
                Degradation(
                    component="killswitch",
                    reason="Killswitch state unreadable",
                    severity=Severity.CRITICAL,
                )
            )

        if killswitch_active:
            return (
                OperationalBlock(
                    state=OperationalState.BLOCKED,
                    primary_reason="killswitch_active",
                    mode=mode,
                    market_phase=market_phase,
                    pipeline_expected=pipeline_expected,
                    next_expected_activity_at=next_activity,
                    active_incident_count=active_incidents,
                ),
                mode,
                market_phase,
                pipeline_expected,
                next_activity,
            )

        # Pipeline expected only during market hours.
        if market_phase == MarketPhase.CLOSED:
            pipeline_expected = False

        # Count active incidents from the event store.
        try:
            active_incidents = await self._count_active_incidents()
        except Exception:
            pass

        state = OperationalState.OPERATIONAL
        reason: str | None = None
        if active_incidents > 0:
            state = OperationalState.DEGRADED
            reason = "active_incidents"
        elif degradations:
            state = OperationalState.DEGRADED
            reason = "pipeline_degradation"

        return (
            OperationalBlock(
                state=state,
                primary_reason=reason,
                mode=mode,
                market_phase=market_phase,
                pipeline_expected=pipeline_expected,
                next_expected_activity_at=next_activity,
                active_incident_count=active_incidents,
            ),
            mode,
            market_phase,
            pipeline_expected,
            next_activity,
        )

    async def _broker_snapshot(
        self, as_of: datetime, degradations: list[Degradation]
    ) -> tuple[Any, list[Any], int]:
        try:
            account, positions = await asyncio.gather(
                asyncio.to_thread(self.alpaca.get_account),
                asyncio.to_thread(self.alpaca.get_all_positions),
            )
            # Treat as fresh because it was just read.
            return account, positions, 0
        except Exception as exc:
            logger.warning("Mobile snapshot: Alpaca broker read failed: %s", exc)
            degradations.append(
                Degradation(
                    component="broker",
                    reason="Broker snapshot unavailable",
                    severity=Severity.CRITICAL,
                )
            )
            return None, [], 300

    def _build_portfolio(
        self,
        account: Any,
        positions: list[Any],
        broker_age: int,
        degradations: list[Degradation],
    ) -> PortfolioBlock:
        if account is None:
            return PortfolioBlock()

        equity = _to_decimal(getattr(account, "equity", None))
        last_equity = _to_decimal(getattr(account, "last_equity", None))
        cash = _to_decimal(getattr(account, "cash", None))
        nav_change = (
            (equity - last_equity) if equity is not None and last_equity is not None else None
        )
        nav_return = (
            float(nav_change / last_equity)
            if nav_change is not None and last_equity and last_equity != 0
            else None
        )
        total_market_value = Decimal("0")
        total_unrealized = Decimal("0")
        for p in positions:
            mv = _to_decimal(getattr(p, "market_value", None))
            u = _to_decimal(getattr(p, "unrealized_pl", None))
            if mv is not None:
                total_market_value += mv
            if u is not None:
                total_unrealized += u

        gross_exposure = (
            float(total_market_value / equity)
            if equity is not None and equity != 0
            else None
        )
        cash_pct = (
            float((cash or Decimal("0")) / equity) if equity and equity != 0 else None
        )

        # Drawdown from Redis peak equity.
        current_drawdown: float | None = None
        try:
            raw_peak = self.redis._r.get("portfolio:peak_equity")
            peak = Decimal(str(raw_peak.decode())) if raw_peak else None
            if peak and equity and peak > 0:
                current_drawdown = float((peak - equity) / peak)
        except Exception:
            pass

        return PortfolioBlock(
            nav=equity,
            nav_change_today=nav_change,
            nav_return_today=nav_return,
            realized_pnl_today=None,
            unrealized_pnl=total_unrealized or None,
            cash=cash,
            cash_pct=cash_pct,
            gross_exposure=gross_exposure,
            gross_exposure_limit=_to_float(getattr(config, "GROSS_EXPOSURE_LIMIT", None))
            or 0.50,
            current_drawdown=current_drawdown,
            drawdown_limit=_to_float(getattr(config, "DRAWDOWN_LIMIT", None)) or 0.05,
            open_positions=len(positions) if positions is not None else None,
            source="alpaca_paper" if config.ALPACA_PAPER_MODE else "alpaca_live",
        )

    async def _build_pipeline(
        self,
        as_of: datetime,
        account: Any,
        positions: list[Any],
        degradations: list[Degradation],
    ) -> dict[str, PipelineComponent]:
        pipeline: dict[str, PipelineComponent] = {}

        # Database
        try:
            async with self.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            pipeline["database"] = PipelineComponent(status=Freshness.FRESH, age_seconds=0)
        except Exception as exc:
            logger.warning("Mobile snapshot: DB health check failed: %s", exc)
            pipeline["database"] = PipelineComponent(
                status=Freshness.STALE, age_seconds=300, writeable=False
            )
            degradations.append(
                Degradation(
                    component="database",
                    reason="Database health check failed",
                    severity=Severity.CRITICAL,
                )
            )

        # Redis
        try:
            self.redis._r.ping()
            pipeline["redis"] = PipelineComponent(
                status=Freshness.FRESH, age_seconds=0, writeable=True
            )
        except Exception as exc:
            logger.warning("Mobile snapshot: Redis ping failed: %s", exc)
            pipeline["redis"] = PipelineComponent(
                status=Freshness.STALE, age_seconds=300, writeable=False
            )
            degradations.append(
                Degradation(
                    component="redis",
                    reason="Redis ping failed",
                    severity=Severity.CRITICAL,
                )
            )

        # Broker
        broker_age = 0 if account is not None else 300
        pipeline["broker"] = PipelineComponent(
            status=_classify_age(broker_age, (30, 90)), age_seconds=broker_age
        )

        # Signal pipeline — last signal age from Redis if available.
        signal_age: int | None = None
        try:
            last_signal = self.redis._r.get("sentiment:last_signal_at")
            if last_signal:
                last_ts = datetime.fromisoformat(last_signal.decode())
                signal_age = int((as_of - last_ts).total_seconds())
        except Exception:
            pass
        pipeline["signal"] = PipelineComponent(
            status=_classify_age(signal_age, (600, 1800))
            if signal_age is not None
            else Freshness.UNKNOWN,
            age_seconds=signal_age or 0,
        )

        # Portfolio cycle — last completion timestamp from DB.
        cycle_age: int | None = None
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT MAX(completed_at) AS last_completed FROM portfolio_cycles"
                )
                if row and row["last_completed"]:
                    cycle_age = int((as_of - row["last_completed"]).total_seconds())
        except Exception:
            pass
        pipeline["portfolio_cycle"] = PipelineComponent(
            status=_classify_age(cycle_age, (300, 900))
            if cycle_age is not None
            else Freshness.UNKNOWN,
            age_seconds=cycle_age or 0,
        )

        return pipeline

    def _build_strategies(self, degradations: list[Degradation]) -> list[StrategyRow]:
        try:
            from src.strategies.registry import StrategyRegistry

            registry = StrategyRegistry()
            active = registry.get_active_strategies()
            return [
                StrategyRow(
                    id=e.strategy_id,
                    mode=getattr(e, "mode", "paper"),
                    allocation_pct=float(getattr(e, "allocation_pct", 0)),
                    approved=bool(getattr(e, "approved", False)),
                )
                for e in active
            ]
        except Exception as exc:
            logger.warning("Mobile snapshot: could not read strategy registry: %s", exc)
            degradations.append(
                Degradation(
                    component="strategies",
                    reason="Strategy registry unreadable",
                    severity=Severity.WARNING,
                )
            )
            return []

    async def _count_active_incidents(self) -> int:
        try:
            async with self.pool.acquire() as conn:
                return await conn.fetchval(
                    """
                    SELECT COUNT(*) FROM mobile_events
                    WHERE status IN ('open', 'escalated')
                    """
                ) or 0
        except Exception:
            return 0

    async def _account(self) -> Any:
        return await asyncio.to_thread(self.alpaca.get_account)


class MobileEventStore:
    """Read-side event store for /api/mobile/v1/events."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def list_events(
        self,
        *,
        category: EventCategory,
        days: int,
        cursor: str | None,
        limit: int,
    ) -> list[EventItem]:
        # Cursor encodes occurred_at and id as a signed opaque token.
        since = _now() - timedelta(days=days)
        cursor_at: datetime | None = None
        cursor_id: Any = None
        if cursor:
            try:
                cursor_at, cursor_id = self._decode_cursor(cursor)
            except Exception:
                cursor_at = None
                cursor_id = None

        statuses = ["open", "escalated", "recovered", "closed"]
        categories = [category.value] if category != EventCategory.ALL else ["critical", "trading", "system"]
        args: list[Any] = [since]
        where = "WHERE occurred_at >= $1"
        if category != EventCategory.ALL:
            args.append(categories)
            where += " AND category = ANY($2)"
            args.append(statuses)
            where += " AND status = ANY($3)"
        else:
            args.append(statuses)
            where += " AND status = ANY($2)"

        if cursor_at is not None:
            # Order is (occurred_at DESC, id DESC). The cursor condition selects rows
            # strictly older than the cursor tuple.
            param_idx = len(args) + 1
            args.extend([cursor_at, cursor_id])
            where += f" AND (occurred_at, id) < (${param_idx}, ${param_idx + 1})"

        sql = f"""
            SELECT id, kind, category, severity, status, occurred_at,
                   first_observed_at, last_observed_at, resolved_at, title,
                   summary, entity_type, entity_id, details
            FROM mobile_events
            {where}
            ORDER BY occurred_at DESC, id DESC
            LIMIT ${len(args) + 1}
        """
        args.append(limit + 1)

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)

        items: list[EventItem] = []
        for row in rows[:limit]:
            items.append(self._row_to_item(row))
        return items

    def _decode_cursor(self, cursor: str) -> tuple[datetime, Any]:
        """Opaque cursor: base64(json([iso, id]))."""
        import base64
        import json

        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        return datetime.fromisoformat(payload[0]), payload[1]

    def _row_to_item(self, row: asyncpg.Record) -> EventItem:
        from src.mobile_monitoring.models import EventEntity, EventHistoryEntry, EventMeasure

        entity = None
        if row["entity_type"]:
            entity = EventEntity(type=row["entity_type"], id=row["entity_id"])
        measure = None
        details = row["details"] or {}
        if isinstance(details, dict):
            if "measure_value" in details:
                measure = EventMeasure(
                    value=details.get("measure_value"),
                    unit=details.get("measure_unit"),
                    threshold=details.get("measure_threshold"),
                )
        history = [
            EventHistoryEntry(state=row["status"], at=row["last_observed_at"]),
        ]
        return EventItem(
            id=row["id"],
            kind=row["kind"],
            category=row["category"],
            severity=row["severity"],
            status=row["status"],
            occurred_at=row["occurred_at"],
            updated_at=row["last_observed_at"],
            resolved_at=row["resolved_at"],
            title=row["title"],
            summary=row["summary"],
            entity=entity,
            measure=measure,
            history=history,
        )
