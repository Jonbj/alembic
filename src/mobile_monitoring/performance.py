"""NAV-based mobile performance projection."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Iterable
from zoneinfo import ZoneInfo

import asyncpg
from starlette.concurrency import run_in_threadpool

from src.config import config
from src.mobile_monitoring.models import (
    Degradation,
    PerformancePoint,
    PerformanceResponse,
    PerformanceSummary,
    Severity,
)
from src.mobile_monitoring.read_model import (
    MobileReadModelSource,
    bundle_age_seconds,
    ensure_bundle_safe,
    load_mobile_read_model,
)
from src.portfolio.benchmark import compute_period_benchmark, spy_on_or_before

logger = logging.getLogger(__name__)

_PERIOD_DAYS = {
    "1w": 7,
    "1m": 30,
    "3m": 90,
    "6m": 180,
    "1y": 365,
}


@dataclass(frozen=True)
class NavSample:
    """One ordered historical NAV/exposure observation."""

    at: datetime
    nav: Decimal
    gross_exposure: float | None


def period_start(
    period: str, end: datetime, earliest: datetime | None = None
) -> datetime:
    """Resolve the inclusive period boundary."""
    if period == "all":
        return earliest or end
    return end - timedelta(days=_PERIOD_DAYS[period])


def performance_summary(
    samples: list[NavSample],
    *,
    realized_pnl: Decimal | None,
    benchmark: dict[str, float | None] | None = None,
) -> PerformanceSummary:
    """Compute approved period formulas from an anchored ordered NAV series."""
    if not samples:
        return PerformanceSummary(realized_pnl=realized_pnl)
    if len(samples) == 1:
        return PerformanceSummary(
            nav_end=samples[0].nav,
            realized_pnl=realized_pnl,
        )
    nav_start = samples[0].nav
    nav_end = samples[-1].nav
    nav_change = nav_end - nav_start
    portfolio_return = (
        round(float(nav_end / nav_start - 1), 6) if nav_start > 0 else None
    )

    peak = samples[0].nav
    max_drawdown = Decimal("0")
    for sample in samples:
        peak = max(peak, sample.nav)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - sample.nav) / peak)

    benchmark = benchmark or {}
    return PerformanceSummary(
        nav_start=nav_start,
        nav_end=nav_end,
        nav_change=nav_change,
        portfolio_return=portfolio_return,
        realized_pnl=realized_pnl,
        max_drawdown=float(max_drawdown),
        avg_gross_exposure=benchmark.get("avg_exposure"),
        spy_return=benchmark.get("spy_return"),
        benchmark_return=benchmark.get("benchmark_return"),
        alpha=benchmark.get("alpha"),
    )


def downsample(samples: list[NavSample], limit: int = 500) -> list[NavSample]:
    """Deterministically retain endpoints, extrema, and an even time sample."""
    if len(samples) <= limit:
        return samples
    required = {0, len(samples) - 1}
    required.add(min(range(len(samples)), key=lambda index: samples[index].nav))
    required.add(max(range(len(samples)), key=lambda index: samples[index].nav))
    remaining = limit - len(required)
    if remaining > 0:
        step = (len(samples) - 1) / (remaining + 1)
        required.update(round(step * index) for index in range(1, remaining + 1))
    indexes = sorted(required)
    if len(indexes) > limit:
        indexes = indexes[: limit - 1] + [len(samples) - 1]
    return [samples[index] for index in indexes]


class MobilePerformanceService:
    """Build performance from persisted NAV history plus the coherent current bundle."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        read_model: MobileReadModelSource,
        spy_loader: Callable[[str, str], dict[str, float] | None] | None = None,
    ) -> None:
        self._pool = pool
        self._read_model = read_model
        self._spy_loader = spy_loader

    async def build(self, period: str) -> PerformanceResponse:
        """Build one safe NAV projection without contacting the trading broker."""
        bundle = await load_mobile_read_model(self._read_model)
        if bundle is None:
            raise RuntimeError("mobile read model unavailable")
        ensure_bundle_safe(bundle)
        end = bundle.snapshot.as_of
        requested_start = period_start(period, end)
        rows = await self._load_nav_rows(requested_start, end, period == "all")
        history_age_seconds = (
            max(0, int((end - rows[-1]["as_of"]).total_seconds())) if rows else None
        )
        samples = [
            NavSample(
                at=row["as_of"],
                nav=Decimal(str(row["nav"])),
                gross_exposure=(
                    float(row["gross_exposure"])
                    if row["gross_exposure"] is not None
                    else None
                ),
            )
            for row in rows
            if row["nav"] is not None
        ]
        current_nav = bundle.snapshot.portfolio.nav
        if current_nav is not None and (
            not samples or bundle.snapshot.as_of > samples[-1].at
        ):
            samples.append(
                NavSample(
                    at=bundle.snapshot.as_of,
                    nav=current_nav,
                    gross_exposure=bundle.snapshot.portfolio.gross_exposure,
                )
            )
        samples.sort(key=lambda sample: sample.at)
        start = period_start(
            period,
            end,
            earliest=samples[0].at if samples else end,
        )
        realized = await self._realized_pnl(start, end)
        spy_closes = await self._load_spy_closes(start, end)
        benchmark = compute_period_benchmark(
            [
                {
                    "date": sample.at.date().isoformat(),
                    "nav": float(sample.nav),
                    "exposure": sample.gross_exposure,
                }
                for sample in samples
            ],
            spy_closes,
            start.date().isoformat(),
            end.date().isoformat(),
        )
        summary = performance_summary(
            samples,
            realized_pnl=realized,
            benchmark=benchmark,
        )
        degradations: list[Degradation] = []
        if len(samples) < 2:
            degradations.append(
                Degradation(
                    component="history",
                    reason="NAV history unavailable for the selected period",
                    severity=Severity.WARNING,
                )
            )
        if realized is None:
            degradations.append(
                Degradation(
                    component="trades",
                    reason="Realized trade P&L unavailable",
                    severity=Severity.WARNING,
                )
            )
        if (
            summary.spy_return is None
            or summary.avg_gross_exposure is None
            or summary.benchmark_return is None
            or summary.alpha is None
        ):
            summary.spy_return = None
            summary.benchmark_return = None
            summary.alpha = None
            degradations.append(
                Degradation(
                    component="benchmark",
                    reason="SPY or exposure history unavailable",
                    severity=Severity.WARNING,
                )
            )
        points = self._points(
            downsample(samples),
            spy_closes=spy_closes,
            avg_exposure=summary.avg_gross_exposure,
        )
        return PerformanceResponse(
            snapshot_id=bundle.snapshot.snapshot_id,
            as_of=end,
            data_age_seconds=bundle_age_seconds(bundle),
            currency=bundle.snapshot.currency,
            min_supported_app_version=config.MIN_SUPPORTED_MOBILE_APP_VERSION,
            latest_app_version=config.LATEST_MOBILE_APP_VERSION,
            period=period,
            period_start=start,
            period_end=end,
            history_data_age_seconds=history_age_seconds,
            benchmark_data_age_seconds=self._benchmark_age_seconds(
                spy_closes,
                end,
            ),
            summary=summary,
            points=points,
            degradations=degradations,
        )

    async def _load_spy_closes(
        self,
        start: datetime,
        end: datetime,
    ) -> dict[str, float] | None:
        if self._spy_loader is None:
            return None
        try:
            return await run_in_threadpool(
                self._spy_loader,
                start.date().isoformat(),
                end.date().isoformat(),
            )
        except Exception as exc:
            logger.warning("Mobile SPY history load failed: %s", exc)
            return None

    async def _load_nav_rows(
        self,
        start: datetime,
        end: datetime,
        all_history: bool,
    ) -> list[asyncpg.Record]:
        async with self._pool.acquire() as conn:
            if all_history:
                return list(
                    await conn.fetch(
                        """
                        SELECT as_of, nav, gross_exposure
                        FROM portfolio_monitor_snapshots
                        WHERE as_of <= $1 AND nav IS NOT NULL
                        ORDER BY as_of
                        """,
                        end,
                    )
                )
            return list(
                await conn.fetch(
                    """
                    SELECT as_of, nav, gross_exposure
                    FROM portfolio_monitor_snapshots
                    WHERE nav IS NOT NULL
                      AND as_of <= $2
                      AND (
                        as_of >= $1
                        OR as_of = (
                          SELECT MAX(as_of)
                          FROM portfolio_monitor_snapshots
                          WHERE nav IS NOT NULL AND as_of < $1
                        )
                      )
                    ORDER BY as_of
                    """,
                    start,
                    end,
                )
            )

    async def _realized_pnl(
        self,
        start: datetime,
        end: datetime,
    ) -> Decimal | None:
        try:
            async with self._pool.acquire() as conn:
                value = await conn.fetchval(
                    """
                    SELECT SUM(net_pnl)
                    FROM trades
                    WHERE exit_time >= $1 AND exit_time <= $2
                      AND net_pnl IS NOT NULL
                    """,
                    start,
                    end,
                )
            return Decimal(str(value)) if value is not None else Decimal("0")
        except Exception as exc:
            logger.warning("Mobile realized P&L query failed: %s", exc)
            return None

    @staticmethod
    def _benchmark_age_seconds(
        spy_closes: dict[str, float] | None,
        end: datetime,
    ) -> int | None:
        if not spy_closes:
            return None
        latest_date = date.fromisoformat(max(spy_closes))
        close_at = datetime.combine(
            latest_date,
            time(16),
            tzinfo=ZoneInfo("America/New_York"),
        )
        return max(0, int((end - close_at.astimezone(timezone.utc)).total_seconds()))

    @staticmethod
    def _points(
        samples: Iterable[NavSample],
        *,
        spy_closes: dict[str, float] | None,
        avg_exposure: float | None,
    ) -> list[PerformancePoint]:
        ordered = list(samples)
        baseline_close = (
            spy_on_or_before(
                spy_closes,
                ordered[0].at.date().isoformat(),
            )
            if spy_closes and ordered
            else None
        )
        baseline_nav = ordered[0].nav if ordered else None
        peak: Decimal | None = None
        points: list[PerformancePoint] = []
        for sample in ordered:
            peak = sample.nav if peak is None else max(peak, sample.nav)
            drawdown = float((peak - sample.nav) / peak) if peak > 0 else None
            close = (
                spy_on_or_before(spy_closes, sample.at.date().isoformat())
                if spy_closes
                else None
            )
            benchmark_nav = (
                baseline_nav
                * Decimal(str(1 + avg_exposure * (close / baseline_close - 1)))
                if baseline_nav is not None
                and baseline_close is not None
                and close is not None
                and avg_exposure is not None
                else None
            )
            points.append(
                PerformancePoint(
                    at=sample.at,
                    nav=sample.nav,
                    drawdown=drawdown,
                    benchmark_nav=benchmark_nav,
                )
            )
        return points
