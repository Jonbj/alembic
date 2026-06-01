"""Validation tests: compare metrics engine against empyrical on known data (T-006).

empyrical has a pandas_datareader incompatibility in this environment; the
module is stubbed out before import to work around it.
"""
from __future__ import annotations

import sys
import types

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Stub broken pandas_datareader so empyrical can be imported
# ---------------------------------------------------------------------------
_pdr = types.ModuleType("pandas_datareader")
_pdr_data = types.ModuleType("pandas_datareader.data")
_pdr.data = _pdr_data
sys.modules.setdefault("pandas_datareader", _pdr)
sys.modules.setdefault("pandas_datareader.data", _pdr_data)

import empyrical  # noqa: E402  (must come after the stub)

from src.backtest.metrics.performance import sharpe_ratio
from src.backtest.metrics.risk import max_drawdown

# ---------------------------------------------------------------------------
# Shared data: three deterministic return series
# ---------------------------------------------------------------------------

_SEEDS_AND_PARAMS: list[tuple[int, float, float]] = [
    (0,  0.0005, 0.012),   # mild positive drift
    (1,  0.0,    0.015),   # zero drift, volatile
    (2, -0.0003, 0.010),   # slight negative drift
]

_SERIES: dict[str, pd.Series] = {}
for _seed, _mu, _sigma in _SEEDS_AND_PARAMS:
    _rng = np.random.default_rng(_seed)
    _key = f"seed{_seed}_mu{_mu}_s{_sigma}"
    _SERIES[_key] = pd.Series(_rng.normal(_mu, _sigma, 756))  # ~3 years

_TOLERANCE = 1e-6


@pytest.mark.parametrize("key", list(_SERIES.keys()))
class TestSharpeVsEmpyrical:
    """Our sharpe_ratio must match empyrical.sharpe_ratio to within 1e-6."""

    def test_sharpe_no_riskfree(self, key: str) -> None:
        r = _SERIES[key]
        ours = sharpe_ratio(r, risk_free=0.0, periods=252)
        theirs = float(empyrical.sharpe_ratio(r, risk_free=0.0, period="daily"))
        assert abs(ours - theirs) < _TOLERANCE, (
            f"[{key}] Sharpe mismatch: ours={ours:.8f}, empyrical={theirs:.8f}"
        )

    def test_sharpe_with_riskfree(self, key: str) -> None:
        r = _SERIES[key]
        rf_annual = 0.04  # 4% annual
        # empyrical expects a per-period (daily) rate, not annualised
        rf_daily = rf_annual / 252
        ours = sharpe_ratio(r, risk_free=rf_annual, periods=252)
        theirs = float(empyrical.sharpe_ratio(r, risk_free=rf_daily, period="daily"))
        assert abs(ours - theirs) < _TOLERANCE, (
            f"[{key}] Sharpe (rf=4%) mismatch: ours={ours:.8f}, empyrical={theirs:.8f}"
        )


@pytest.mark.parametrize("key", list(_SERIES.keys()))
class TestMaxDrawdownVsEmpyrical:
    """Our max_drawdown must match empyrical.max_drawdown to within 1e-10."""

    def test_max_drawdown(self, key: str) -> None:
        r = _SERIES[key]
        ours = max_drawdown(r)
        theirs = float(empyrical.max_drawdown(r))
        assert abs(ours - theirs) < 1e-10, (
            f"[{key}] MaxDD mismatch: ours={ours:.12f}, empyrical={theirs:.12f}"
        )

    def test_max_drawdown_non_positive(self, key: str) -> None:
        assert max_drawdown(_SERIES[key]) <= 0.0

    def test_max_drawdown_matches_empyrical_sign(self, key: str) -> None:
        r = _SERIES[key]
        ours = max_drawdown(r)
        theirs = float(empyrical.max_drawdown(r))
        # Both should agree on sign (both ≤ 0)
        assert np.sign(ours) == np.sign(theirs) or (ours == 0.0 and theirs == 0.0)


class TestKnownValuesEmpyrical:
    """Spot-checks on small, hand-verifiable series."""

    def test_sharpe_large_positive_drift(self) -> None:
        # empyrical returns NaN / inf for zero-std constant series (known quirk);
        # use a high-drift noisy series instead.
        rng = np.random.default_rng(99)
        r = pd.Series(rng.normal(0.002, 0.01, 500))
        ours = sharpe_ratio(r, risk_free=0.0, periods=252)
        theirs = float(empyrical.sharpe_ratio(r, risk_free=0.0, period="daily"))
        assert abs(ours - theirs) < _TOLERANCE

    def test_max_drawdown_single_drop(self) -> None:
        r = pd.Series([-0.05, 0.0, 0.0])
        ours = max_drawdown(r)
        theirs = float(empyrical.max_drawdown(r))
        assert abs(ours - theirs) < 1e-10

    def test_max_drawdown_monotone_up_zero(self) -> None:
        r = pd.Series([0.01] * 50)
        ours = max_drawdown(r)
        theirs = float(empyrical.max_drawdown(r))
        assert abs(ours - theirs) < 1e-10
        assert ours == pytest.approx(0.0, abs=1e-9)
