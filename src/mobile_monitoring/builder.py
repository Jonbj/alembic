"""Coherent mobile monitoring snapshot builder.

The builder assembles the read-only mobile view from Alpaca, Redis, Postgres, and
the strategy registry. It keeps financial fields nullable when broker data is
unavailable and reports degradations rather than substituting zeros.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, cast
from uuid import uuid4
from zoneinfo import ZoneInfo

import asyncpg
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetCalendarRequest
from redis import Redis

from src.config import config
from src.mobile_monitoring.models import (
    Degradation,
    Freshness,
    MarketPhase,
    OperationalState,
    OperationalBlock,
    PipelineComponent,
    PortfolioBlock,
    PositionItem,
    PositionsResponse,
    PositionsSummary,
    Severity,
    SnapshotResponse,
    StrategyRow,
)
from src.mobile_monitoring.read_model import MobileReadBundle
from src.mobile_monitoring.state import MARKET_TIMEZONE, resolve_market_context
from src.store.redis_store import RedisStore

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
        redis: RedisStore | None = None,
    ) -> None:
        self.pool = pool
        self.alpaca = alpaca or TradingClient(
            api_key=config.ALPACA_API_KEY,
            secret_key=config.ALPACA_SECRET_KEY,
            paper=config.ALPACA_PAPER_MODE,
        )
        # Workers own their Redis connection. FastAPI lifespan dependencies are
        # intentionally not used here because Celery has no API lifespan.
        self.redis = redis or RedisStore()

    async def build_snapshot(self, as_of: datetime | None = None) -> SnapshotResponse:
        """Build and return the snapshot half of one coherent read bundle."""
        return (await self.build_bundle(as_of=as_of)).snapshot

    async def build_bundle(self, as_of: datetime | None = None) -> MobileReadBundle:
        """Read broker state once and derive snapshot and positions atomically."""
        as_of = as_of or _now()
        snapshot_id = uuid4()
        degradations: list[Degradation] = []

        # --- operational state ------------------------------------------------
        operational, mode, market_phase, pipeline_expected, next_activity = await self._operational_state(
            as_of, degradations
        )

        # --- broker data ------------------------------------------------------
        account, positions, broker_age = await self._broker_snapshot(as_of, degradations)
        portfolio = self._build_portfolio(account, positions, broker_age, degradations)

        # --- pipeline health --------------------------------------------------
        pipeline = await self._build_pipeline(
            as_of,
            account,
            positions,
            degradations,
            pipeline_expected=pipeline_expected,
        )

        # --- strategies -------------------------------------------------------
        strategies = self._build_strategies(degradations)

        critical = next(
            (
                degradation
                for degradation in degradations
                if degradation.severity == Severity.CRITICAL
            ),
            None,
        )
        if critical is not None:
            operational.state = OperationalState.BLOCKED
            operational.primary_reason = f"{critical.component}_unavailable"
        elif degradations:
            operational.state = OperationalState.DEGRADED
            operational.primary_reason = "pipeline_degradation"
        elif not operational.pipeline_expected:
            operational.state = OperationalState.PAUSED
            operational.primary_reason = "pipeline_not_expected"

        snapshot = SnapshotResponse(
            snapshot_id=snapshot_id,
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
        positions_response = self._build_positions_response(
            as_of=as_of,
            snapshot_id=snapshot_id,
            account=account,
            positions=positions,
            degradations=degradations,
        )
        return MobileReadBundle(snapshot=snapshot, positions=positions_response)

    async def build_positions(self, as_of: datetime | None = None) -> PositionsResponse:
        """Build positions through the same coherent broker-read path."""
        return (await self.build_bundle(as_of=as_of)).positions

    def _build_positions_response(
        self,
        *,
        as_of: datetime,
        snapshot_id: Any,
        account: Any,
        positions: list[Any],
        degradations: list[Degradation],
    ) -> PositionsResponse:
        """Derive positions without another broker call."""
        as_of = as_of or _now()
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
                    unrealized_return=_to_float(
                        getattr(p, "unrealized_plpc", None)
                    ),
                    entry_time=None,
                )
            )
        equity = _to_decimal(getattr(account, "equity", None))
        gross_exposure = (
            float(
                sum(
                    abs(item.market_value)
                    for item in items
                    if item.market_value is not None
                )
                / equity
            )
            if equity is not None and equity > 0
            else None
        )
        for item in items:
            if equity is not None and equity > 0 and item.market_value is not None:
                item.position_weight = float(abs(item.market_value) / equity)
        items.sort(
            key=lambda item: (
                item.unrealized_return is None,
                item.unrealized_return or 0,
                -(abs(item.market_value) if item.market_value is not None else 0),
            )
        )
        broker_available = account is not None
        return PositionsResponse(
            snapshot_id=snapshot_id,
            as_of=as_of,
            data_age_seconds=0,
            currency="USD",
            min_supported_app_version=config.MIN_SUPPORTED_MOBILE_APP_VERSION,
            latest_app_version=config.LATEST_MOBILE_APP_VERSION,
            summary=PositionsSummary(
                count=len(items),
                market_value=total_market_value if broker_available else None,
                unrealized_pnl=total_unrealized if broker_available else None,
                gross_exposure=gross_exposure,
            ),
            items=items,
            degradations=[
                degradation
                for degradation in degradations
                if degradation.component == "broker"
            ],
        )

    # --- internal helpers -------------------------------------------------

    async def _operational_state(
        self, as_of: datetime, degradations: list[Degradation]
    ) -> tuple[OperationalBlock, str, MarketPhase, bool, datetime | None]:
        mode = "paper" if config.ALPACA_PAPER_MODE else "live"
        market_phase = MarketPhase.CLOSED
        pipeline_expected = False
        next_activity: datetime | None = None
        active_incidents = 0

        try:
            clock = await asyncio.to_thread(self.alpaca.get_clock)
            sessions: list[Any] = []
            try:
                market_date = as_of.astimezone(ZoneInfo(MARKET_TIMEZONE)).date()
                sessions = list(
                    await asyncio.to_thread(
                        self.alpaca.get_calendar,
                        GetCalendarRequest(start=market_date, end=market_date),
                    )
                )
            except Exception as exc:
                logger.warning(
                    "Mobile snapshot: could not read market calendar: %s",
                    exc,
                )
                degradations.append(
                    Degradation(
                        component="market_calendar",
                        reason="Market calendar unavailable",
                        severity=Severity.WARNING,
                    )
                )
            context = resolve_market_context(
                as_of=as_of,
                clock=clock,
                sessions=sessions,
            )
            market_phase = context.phase
            pipeline_expected = context.pipeline_expected
            next_activity = context.next_activity_at
        except Exception as exc:
            logger.warning("Mobile snapshot: could not read market clock: %s", exc)
            degradations.append(
                Degradation(
                    component="market_clock",
                    reason="Market clock unavailable",
                    severity=Severity.CRITICAL,
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
            return account, cast(list[Any], positions), 0
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
            redis_client = cast(Redis, self.redis._r)
            raw_peak = cast(
                bytes | str | None,
                redis_client.get("portfolio:peak_equity"),
            )
            decoded_peak = (
                raw_peak.decode() if isinstance(raw_peak, bytes) else raw_peak
            )
            peak = Decimal(decoded_peak) if decoded_peak else None
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
        *,
        pipeline_expected: bool,
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
            cast(Redis, self.redis._r).ping()
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
            last_signal = cast(
                bytes | str | None,
                cast(Redis, self.redis._r).get("sentiment:last_signal_at"),
            )
            if last_signal:
                encoded_timestamp = (
                    last_signal.decode()
                    if isinstance(last_signal, bytes)
                    else last_signal
                )
                last_ts = datetime.fromisoformat(encoded_timestamp)
                signal_age = int((as_of - last_ts).total_seconds())
        except Exception:
            pass
        pipeline["signal"] = PipelineComponent(
            status=(
                _classify_age(signal_age, (600, 1800))
                if signal_age is not None
                else Freshness.UNKNOWN
            )
            if pipeline_expected
            else Freshness.NOT_EXPECTED,
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
            status=(
                _classify_age(cycle_age, (300, 900))
                if cycle_age is not None
                else Freshness.UNKNOWN
            )
            if pipeline_expected
            else Freshness.NOT_EXPECTED,
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
