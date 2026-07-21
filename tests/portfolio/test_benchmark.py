"""Tests for the beta-scaled benchmark / alpha computation.

The book is only ~30% net-long, so SPY outright is an unfair bar; the fair
benchmark is exposure × SPY (i.e. "30% SPY + 70% cash"). Alpha = actual
return − beta-scaled benchmark. Answers "is Alembic losing more / gaining
less than its market exposure explains?" (no such metric existed before).
"""
from __future__ import annotations

from src.portfolio.benchmark import compute_period_benchmark


def _nav(date, nav, expo):
    return {"date": date, "nav": nav, "exposure": expo}


def test_alpha_is_negative_when_underperforming_beta_scaled_spy():
    # Alembic −1.0%, SPY −0.4%, exposure 0.30 → benchmark −0.12%, alpha −0.88pp.
    nav_rows = [
        _nav("2026-07-03", 100000.0, 0.30),  # baseline (before range)
        _nav("2026-07-06", 99800.0, 0.30),
        _nav("2026-07-20", 99000.0, 0.30),   # end
    ]
    spy = {"2026-07-03": 500.0, "2026-07-06": 499.0, "2026-07-17": 498.0}

    out = compute_period_benchmark(nav_rows, spy, "2026-07-06", "2026-07-20")

    assert out["alembic_return"] == round(99000.0 / 100000.0 - 1, 6)  # −1.0%
    assert out["spy_return"] == round(498.0 / 500.0 - 1, 6)           # −0.4%
    assert out["avg_exposure"] == 0.30
    assert out["benchmark_return"] == round(0.30 * (498.0 / 500.0 - 1), 6)
    assert out["alpha"] == round(out["alembic_return"] - out["benchmark_return"], 6)
    assert out["alpha"] < 0


def test_positive_alpha_when_beating_the_bar():
    nav_rows = [_nav("2026-07-03", 100000.0, 0.50), _nav("2026-07-10", 101000.0, 0.50)]
    spy = {"2026-07-03": 500.0, "2026-07-10": 505.0}  # SPY +1.0%, bench +0.5%
    out = compute_period_benchmark(nav_rows, spy, "2026-07-06", "2026-07-10")
    assert out["alembic_return"] > out["benchmark_return"]
    assert out["alpha"] > 0


def test_spy_uses_close_on_or_before_the_anchor_date():
    # baseline 2026-07-06 has no SPY bar (holiday) → use 07-03; end weekend → 07-17.
    nav_rows = [_nav("2026-07-06", 100000.0, 0.40), _nav("2026-07-20", 100500.0, 0.40)]
    spy = {"2026-07-03": 500.0, "2026-07-17": 510.0}
    out = compute_period_benchmark(nav_rows, spy, "2026-07-06", "2026-07-20")
    assert out["spy_return"] == round(510.0 / 500.0 - 1, 6)


def test_returns_none_fields_when_spy_unavailable():
    nav_rows = [_nav("2026-07-03", 100000.0, 0.30), _nav("2026-07-20", 99000.0, 0.30)]
    out = compute_period_benchmark(nav_rows, None, "2026-07-06", "2026-07-20")
    assert out["alembic_return"] == round(99000.0 / 100000.0 - 1, 6)
    assert out["spy_return"] is None
    assert out["benchmark_return"] is None
    assert out["alpha"] is None


def test_returns_none_when_no_nav_baseline():
    out = compute_period_benchmark([], {"2026-07-03": 500.0}, "2026-07-06", "2026-07-20")
    assert out["alembic_return"] is None
    assert out["alpha"] is None
