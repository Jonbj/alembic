"""Behavior tests for NAV-based mobile performance formulas."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.mobile_monitoring.performance import (
    MobilePerformanceService,
    NavSample,
    downsample,
    performance_summary,
)


def test_performance_uses_anchor_drawdown_and_exposure_adjusted_benchmark() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    samples = [
        NavSample(start, Decimal("100"), None),
        NavSample(start + timedelta(days=1), Decimal("110"), 0.50),
        NavSample(start + timedelta(days=2), Decimal("90"), 0.25),
        NavSample(start + timedelta(days=3), Decimal("120"), 0.75),
    ]

    summary = performance_summary(
        samples,
        realized_pnl=Decimal("10"),
        benchmark={
            "alembic_return": 0.20,
            "spy_return": 0.10,
            "avg_exposure": 0.50,
            "benchmark_return": 0.05,
            "alpha": 0.15,
        },
    )

    assert summary.nav_change == Decimal("20")
    assert summary.portfolio_return == 0.20
    assert summary.max_drawdown == float(Decimal("20") / Decimal("110"))
    assert summary.avg_gross_exposure == 0.50
    assert summary.benchmark_return == 0.05
    assert summary.alpha == 0.15
    assert summary.realized_pnl == Decimal("10")


def test_benchmark_fields_are_null_as_a_group_without_spy() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    summary = performance_summary(
        [
            NavSample(start, Decimal("100"), None),
            NavSample(start + timedelta(days=1), Decimal("105"), 0.30),
        ],
        realized_pnl=None,
        benchmark=None,
    )

    assert summary.spy_return is None
    assert summary.benchmark_return is None
    assert summary.alpha is None


def test_single_nav_point_does_not_invent_zero_return() -> None:
    summary = performance_summary(
        [
            NavSample(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                Decimal("105"),
                0.30,
            )
        ],
        realized_pnl=None,
        benchmark={
            "alembic_return": 0.0,
            "spy_return": 0.10,
            "avg_exposure": 0.30,
            "benchmark_return": 0.03,
            "alpha": -0.03,
        },
    )

    assert summary.nav_start is None
    assert summary.nav_end == Decimal("105")
    assert summary.nav_change is None
    assert summary.portfolio_return is None
    assert summary.max_drawdown is None


def test_benchmark_curve_is_populated_as_one_group() -> None:
    start = datetime(2026, 1, 2, tzinfo=timezone.utc)
    samples = [
        NavSample(start, Decimal("100"), 0.50),
        NavSample(start + timedelta(days=1), Decimal("105"), 0.50),
    ]

    points = MobilePerformanceService._points(
        samples,
        spy_closes={"2026-01-02": 100.0, "2026-01-03": 110.0},
        avg_exposure=0.50,
    )

    assert points[0].benchmark_nav == Decimal("100.0")
    assert points[1].benchmark_nav == Decimal("105.00")


def test_downsample_retains_endpoints_and_nav_extrema() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    samples = [
        NavSample(start + timedelta(minutes=index), Decimal(index), 0.30)
        for index in range(600)
    ]
    samples[123] = NavSample(samples[123].at, Decimal("-50"), 0.30)
    samples[456] = NavSample(samples[456].at, Decimal("999"), 0.30)

    result = downsample(samples)

    assert len(result) <= 500
    assert result[0] == samples[0]
    assert result[-1] == samples[-1]
    assert samples[123] in result
    assert samples[456] in result
