# 02 — Phases B, C, E: Strategies S1, S3, S4

Tre strategie raggruppate perché condividono pattern simile:
1. Signal-based (long-only inizialmente)
2. Equity/ETF only (no opzioni)
3. Stesso template di implementazione
4. Stesso template di validazione (gates 1-5)

**S2 (Volatility Risk Premium) sta in documento separato (`03_PHASE_D_S2_OPTIONS.md`) perché è significativamente diversa.**

---

## Common pattern: come si implementa una strategia

Ogni strategia segue questo template. Lo descrivo una volta, le strategie specifiche dopo.

### Pattern di file structure per strategia

```
alembic/strategies/<strategy_id>/
├── __init__.py
├── config.yaml             # Parametri default da literature
├── signal.py               # Pure functions: compute signal
├── sizing.py               # Pure functions: from signal to weights
├── strategy.py             # BaseStrategy implementation
└── README.md               # Documentazione della strategia

tests/strategies/<strategy_id>/
├── __init__.py
├── test_signal.py          # Unit tests signal
├── test_sizing.py          # Unit tests sizing
├── test_strategy.py        # Integration tests
└── fixtures/               # Test data fixtures
```

### BaseStrategy interface

Definita una volta in `alembic/strategies/base.py` (parte del setup pre-Phase-B):

```python
"""Base class per tutte le strategie. Tutte le strategie aderiscono a questo contratto."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
import uuid


class RebalanceFrequency(str, Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"


class StrategyHealth(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


@dataclass(frozen=True)
class StrategyContext:
    """State + data passed to a strategy at each rebalance.
    
    Tutto immutable. La strategia legge questo e produce un StrategyOutput.
    NON modifica il context.
    """
    as_of: datetime
    current_portfolio_weights: dict[str, float]  # ticker -> current weight
    total_portfolio_value_usd: float
    
    # Market data (from DataReplay in backtest, from live data in production)
    price_history: Any  # pd.DataFrame, index=date, columns=tickers
    returns_history: Any  # pd.DataFrame, same shape
    volume_history: Any  # pd.DataFrame, same shape
    
    # Optional: enrichments
    regime: Any  # RegimeState | None
    news_signals: Any  # dict[ticker, AggregatedSignal] | None
    
    # Strategy params (loaded from YAML)
    params: dict[str, Any]


@dataclass(frozen=True)
class StrategyOutput:
    """What a strategy produces."""
    strategy_id: str
    as_of: datetime
    target_weights: dict[str, float]  # ticker -> weight WITHIN this strategy's allocation
    confidence: float  # [0, 1]
    rationale: dict[str, Any]  # debugging info
    output_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class StrategyHealthReport:
    strategy_id: str
    as_of: datetime
    status: StrategyHealth
    issues: list[str]
    metrics: dict[str, Any]


class BaseStrategy(ABC):
    """Contract all strategies must satisfy."""
    
    @property
    @abstractmethod
    def strategy_id(self) -> str: ...
    
    @property
    @abstractmethod
    def target_allocation_pct(self) -> float:
        """Portion of total portfolio this strategy claims."""
        ...
    
    @property
    @abstractmethod
    def rebalance_frequency(self) -> RebalanceFrequency: ...
    
    @abstractmethod
    def should_rebalance(self, as_of: datetime, last_rebalance: datetime | None) -> bool:
        """Should this strategy rebalance at `as_of`?"""
        ...
    
    @abstractmethod
    def compute_target_weights(self, ctx: StrategyContext) -> StrategyOutput:
        """Compute desired weights given context. Pure function."""
        ...
    
    def health_check(self, ctx: StrategyContext) -> StrategyHealthReport:
        """Default: GREEN. Override in subclasses for specific checks."""
        return StrategyHealthReport(
            strategy_id=self.strategy_id,
            as_of=ctx.as_of,
            status=StrategyHealth.GREEN,
            issues=[],
            metrics={},
        )
```

Setup pre-Phase B:

```bash
# Crea base interface
mkdir -p alembic/strategies tests/strategies
touch alembic/strategies/__init__.py tests/strategies/__init__.py

# Create base.py (con il codice sopra)
# Create test_base.py con tests minimali per assicurarsi che il contratto sia valido

git add alembic/strategies tests/strategies
git commit -m "[Phase B prep] Add BaseStrategy interface"
```

---

## PHASE B — Strategia S1: Time-Series Momentum

**Branch**: `phase-B-s1-momentum`
**Effort totale**: ~3 settimane part-time
**Reference docs**: `/alembic_v2/01_strategy_design.md` §S1

---

### T-101 — Universe e data per S1

**Status**: OPEN
**Effort**: S (1-2d)
**Dependencies**: T-001
**Reference docs**: `/alembic_v2/01_strategy_design.md` §S1.Universe

#### Prerequisites check

```bash
# Verify T-001 done
poetry run python -c "from alembic.backtest.data.universe import load_universe; load_universe('s1')"
```

#### Implementation steps

L'universo è già in `config/universe.yaml` (creato in T-001). Questo task aggiunge:

1. **Survivorship check**: per ogni ticker, verifica inception date corretta usando yfinance metadata
2. **Data quality validation**: no large gaps, no spike anomali, dividend-adjusted correttamente
3. **Pre-backfill**: scarica 30+ anni di history per tutti i ticker

```bash
# Backfill 30 anni
poetry run python scripts/download_initial_data.py --start 1995-01-01 --universe s1

# Validate data quality
poetry run python scripts/validate_universe_data.py --universe s1
```

Crea `scripts/validate_universe_data.py`:

```python
"""Data quality validation per universe S1."""
import argparse
from datetime import date

import pandas as pd

from alembic.backtest.data.loader import DataLoader
from alembic.backtest.data.universe import load_universe


def validate_ticker(symbol: str, df: pd.DataFrame) -> list[str]:
    issues = []
    
    # 1. No missing days (excluding holidays, weekends)
    expected_days = pd.bdate_range(df.index.min(), df.index.max())
    missing = set(expected_days) - set(df.index)
    if len(missing) > 30:  # tolerance for holidays
        issues.append(f"  - {len(missing)} missing business days")
    
    # 2. No price spikes (one-day return > 50%)
    daily_returns = df["Adj Close"].pct_change()
    spikes = daily_returns[daily_returns.abs() > 0.50]
    if len(spikes) > 0:
        issues.append(f"  - {len(spikes)} suspicious price spikes (|return| > 50%)")
        for ts, r in spikes.head(5).items():
            issues.append(f"      {ts.date()}: {r:.1%}")
    
    # 3. Volume sanity (no zero volume days for liquid ETFs)
    zero_vol = (df["Volume"] == 0).sum()
    if zero_vol > 5:
        issues.append(f"  - {zero_vol} zero-volume days")
    
    # 4. Adj Close ≤ Close on average (shows dividends/splits are being subtracted)
    if (df["Adj Close"] > df["Close"]).all():
        issues.append("  - Adj Close always > Close (suspicious dividend handling)")
    
    return issues


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", default="s1")
    args = parser.parse_args()
    
    universe = load_universe(args.universe)
    loader = DataLoader()
    
    all_pass = True
    for asset in universe.assets:
        df = loader.download(asset.symbol, start=date(1995, 1, 1))
        issues = validate_ticker(asset.symbol, df)
        
        if issues:
            all_pass = False
            print(f"\n✗ {asset.symbol}:")
            for issue in issues:
                print(issue)
        else:
            print(f"✓ {asset.symbol}: clean ({len(df)} rows, {df.index.min().date()} → {df.index.max().date()})")
    
    print(f"\n{'All clean' if all_pass else 'ISSUES FOUND, REVIEW'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

#### Acceptance verification

```bash
poetry run python scripts/download_initial_data.py --start 1995-01-01 --universe s1
poetry run python scripts/validate_universe_data.py --universe s1
# Expected: tutti puliti o issues minori documentati

# Verifica che point-in-time inception sia rispettato
poetry run python -c "
from datetime import date
from alembic.backtest.data.universe import load_universe

universe = load_universe('s1')
# A 2003-01-01, EWJ esiste (1996) ma TIP no (2003-12-04)
active = universe.active_at(date(2003, 1, 1))
symbols = [a.symbol for a in active]
assert 'EWJ' in symbols
assert 'TIP' not in symbols
print('Point-in-time universe OK')
"
```

#### Commit

```
[T-101] S1 universe data + quality validation

- Pre-backfill 30 years of OHLCV for 15 ETF
- Data quality script: gaps, spikes, volume, adj close
- Verified point-in-time inception dates

Refs: alembic_v2/01_strategy_design.md §S1
```

---

### T-102 — S1 Signal Computation

**Status**: OPEN
**Effort**: M (3-5d)
**Dependencies**: T-101
**Reference docs**: `/alembic_v2/01_strategy_design.md` §S1.Signal

#### Files to create

```
alembic/strategies/s1_ts_momentum/__init__.py
alembic/strategies/s1_ts_momentum/config.yaml
alembic/strategies/s1_ts_momentum/signal.py
tests/strategies/s1_ts_momentum/__init__.py
tests/strategies/s1_ts_momentum/test_signal.py
```

#### Implementation: signal.py

```python
"""Signal computation per S1 Time-Series Momentum.

Riferimento: Moskowitz, Ooi, Pedersen (2012) "Time series momentum".

Signal formula:
    momentum_12_1(t) = log(P[t-skip] / P[t-skip-lookback])
    σ_60d(t) = std of log returns over rolling 60d window, annualized
    risk_adjusted_signal(t) = momentum_12_1(t) / σ_60d(t)
"""
from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class S1SignalParams:
    lookback_long_days: int = 252
    lookback_skip_days: int = 21
    vol_window_days: int = 60
    annualization_factor: int = 252


def compute_log_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Daily log returns from adjusted close prices."""
    return np.log(prices / prices.shift(1))


def compute_realized_vol(
    log_returns: pd.DataFrame,
    window: int,
    annualization: int = 252,
) -> pd.DataFrame:
    """Rolling realized volatility, annualized."""
    return log_returns.rolling(window).std() * np.sqrt(annualization)


def compute_momentum_12_1(
    prices: pd.DataFrame,
    lookback: int = 252,
    skip: int = 21,
) -> pd.DataFrame:
    """12-month momentum excluding most recent month.
    
    Signal at time t = log(P[t-skip] / P[t-skip-lookback])
    
    Why skip? Per evitare short-term reversal effects (Jegadeesh 1990).
    """
    # P[t-skip]
    recent = prices.shift(skip)
    # P[t-skip-lookback]
    distant = prices.shift(skip + lookback)
    return np.log(recent / distant)


def compute_s1_signal(
    prices: pd.DataFrame,
    params: S1SignalParams | None = None,
) -> pd.DataFrame:
    """Compute risk-adjusted S1 signal per ogni ticker.
    
    Returns DataFrame con NaN per i primi (lookback + skip + vol_window) giorni.
    
    Args:
        prices: pd.DataFrame, index=date, columns=ticker, values=adj close
        params: S1SignalParams (default: literature standard)
    
    Returns:
        pd.DataFrame con stessa shape, valori = risk-adjusted momentum signal
    """
    params = params or S1SignalParams()
    
    log_returns = compute_log_returns(prices)
    realized_vol = compute_realized_vol(log_returns, params.vol_window_days, params.annualization_factor)
    momentum = compute_momentum_12_1(prices, params.lookback_long_days, params.lookback_skip_days)
    
    # Risk-adjusted (Sharpe-like)
    signal = momentum / realized_vol.replace(0, np.nan)
    
    return signal
```

#### Implementation: tests

Crea `tests/strategies/s1_ts_momentum/test_signal.py`:

```python
"""Tests for S1 signal computation."""
from datetime import date

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, strategies as st, settings

from alembic.strategies.s1_ts_momentum.signal import (
    S1SignalParams,
    compute_log_returns,
    compute_momentum_12_1,
    compute_realized_vol,
    compute_s1_signal,
)


def make_trending_prices(n_days: int = 500, drift_per_day: float = 0.001) -> pd.DataFrame:
    """Synthetic prices with deterministic positive drift."""
    dates = pd.bdate_range("2020-01-01", periods=n_days)
    np.random.seed(42)
    
    # Geometric series with small noise around drift
    log_returns = np.random.normal(drift_per_day, 0.005, n_days)
    log_returns[0] = 0  # First day no return
    log_prices = np.cumsum(log_returns)
    prices = 100 * np.exp(log_prices)
    
    return pd.DataFrame({"TEST": prices}, index=dates)


def make_declining_prices(n_days: int = 500) -> pd.DataFrame:
    """Synthetic prices with deterministic negative drift."""
    return make_trending_prices(n_days, drift_per_day=-0.001)


def make_flat_prices(n_days: int = 500) -> pd.DataFrame:
    """Random walk no drift."""
    return make_trending_prices(n_days, drift_per_day=0.0)


class TestLogReturns:
    def test_basic(self):
        prices = pd.DataFrame({"A": [100, 110, 121]}, index=pd.date_range("2020-01-01", periods=3))
        result = compute_log_returns(prices)
        
        # First should be NaN (no prior price)
        assert pd.isna(result["A"].iloc[0])
        
        # log(110/100) ≈ 0.0953
        assert abs(result["A"].iloc[1] - np.log(1.1)) < 1e-6
        # log(121/110) ≈ 0.0953 (constant 10% growth)
        assert abs(result["A"].iloc[2] - np.log(1.1)) < 1e-6


class TestMomentum12_1:
    def test_uptrend_positive_signal(self):
        prices = make_trending_prices(n_days=500)
        mom = compute_momentum_12_1(prices)
        
        # At the end of period, with uptrend, momentum should be positive
        final_mom = mom["TEST"].iloc[-1]
        assert final_mom > 0, f"Uptrend should give positive momentum, got {final_mom}"
    
    def test_downtrend_negative_signal(self):
        prices = make_declining_prices(n_days=500)
        mom = compute_momentum_12_1(prices)
        
        final_mom = mom["TEST"].iloc[-1]
        assert final_mom < 0, f"Downtrend should give negative momentum, got {final_mom}"
    
    def test_flat_near_zero(self):
        prices = make_flat_prices(n_days=500)
        mom = compute_momentum_12_1(prices)
        
        # Allow some noise
        final_mom = mom["TEST"].iloc[-1]
        assert abs(final_mom) < 0.1, f"Flat should give near-zero momentum, got {final_mom}"
    
    def test_first_lookback_skip_days_are_nan(self):
        prices = make_trending_prices(n_days=500)
        mom = compute_momentum_12_1(prices, lookback=252, skip=21)
        
        # First 252+21 days should be NaN
        assert pd.isna(mom["TEST"].iloc[272])  # OK at index 273 should not be NaN
        assert not pd.isna(mom["TEST"].iloc[273])


class TestRealizedVol:
    def test_constant_returns_zero_vol(self):
        # Returns identici → vol = 0
        prices_const_growth = pd.DataFrame(
            {"A": [100 * 1.01**i for i in range(100)]},
            index=pd.date_range("2020-01-01", periods=100)
        )
        log_ret = compute_log_returns(prices_const_growth)
        vol = compute_realized_vol(log_ret, window=20)
        
        # After warmup, vol should be ~0
        assert vol["A"].iloc[-1] < 1e-6
    
    def test_higher_vol_for_more_volatile_returns(self):
        np.random.seed(42)
        prices_low_vol = pd.DataFrame(
            {"A": 100 * np.exp(np.cumsum(np.random.normal(0, 0.005, 200)))},
            index=pd.date_range("2020-01-01", periods=200)
        )
        prices_high_vol = pd.DataFrame(
            {"A": 100 * np.exp(np.cumsum(np.random.normal(0, 0.025, 200)))},
            index=pd.date_range("2020-01-01", periods=200)
        )
        
        vol_low = compute_realized_vol(compute_log_returns(prices_low_vol), 60)
        vol_high = compute_realized_vol(compute_log_returns(prices_high_vol), 60)
        
        assert vol_low["A"].iloc[-1] < vol_high["A"].iloc[-1]


class TestS1Signal:
    def test_full_pipeline(self):
        prices = make_trending_prices(n_days=500)
        signal = compute_s1_signal(prices)
        
        # Signal at the end should be positive (uptrend) and finite
        final = signal["TEST"].iloc[-1]
        assert np.isfinite(final)
        assert final > 0
    
    def test_no_lookahead(self):
        """Signal at time t must not depend on data after t."""
        prices = make_trending_prices(n_days=500)
        signal_full = compute_s1_signal(prices)
        
        # Compute signal on truncated data, verify same value at common date
        truncate_at = 300
        signal_truncated = compute_s1_signal(prices.iloc[:truncate_at])
        
        # Both should give same signal at index 299
        for i in range(280, truncate_at):
            full_val = signal_full["TEST"].iloc[i]
            trunc_val = signal_truncated["TEST"].iloc[i]
            if not pd.isna(full_val):
                assert abs(full_val - trunc_val) < 1e-10, \
                    f"Look-ahead detected at index {i}: full={full_val}, truncated={trunc_val}"
    
    @given(drift=st.floats(min_value=-0.002, max_value=0.002))
    @settings(deadline=2000, max_examples=20)
    def test_signal_sign_matches_drift_property(self, drift):
        """Property: signal sign should usually match the drift sign."""
        prices = make_trending_prices(n_days=500, drift_per_day=drift)
        signal = compute_s1_signal(prices)
        final = signal["TEST"].iloc[-1]
        
        # For very small drift, signal can have any sign (noise dominates)
        if abs(drift) > 0.0005:
            if drift > 0:
                assert final > 0, f"Positive drift {drift} should give positive signal, got {final}"
            else:
                assert final < 0, f"Negative drift {drift} should give negative signal, got {final}"
```

#### S1 config

Crea `alembic/strategies/s1_ts_momentum/config.yaml`:

```yaml
version: "0.1.0"
last_modified: "2026-05-28"
strategy_id: "s1_ts_momentum"

# Signal parameters (from Moskowitz et al. 2012)
signal:
  lookback_long_days: 252       # 12 months trading days
  lookback_skip_days: 21        # 1 month skip
  vol_window_days: 60           # 3 months realized vol
  annualization_factor: 252

# Position sizing
sizing:
  total_vol_target: 0.10        # 10% annualized portfolio vol
  max_leverage_per_asset: 1.5
  max_gross_exposure: 2.0
  signal_threshold: 0.0         # long if signal > 0, flat if <= 0
  
# Trading
trading:
  rebalance_frequency: "MONTHLY"
  min_holding_days: 21
  short_enabled: false          # long-only initially
  
# Strategy allocation in combined portfolio
allocation:
  target_pct: 0.40              # 40% of total portfolio

# Universe ref
universe: "s1"
```

#### Acceptance verification

```bash
poetry run pytest tests/strategies/s1_ts_momentum/test_signal.py -v
# Expected: tutti pass

poetry run pytest tests/strategies/s1_ts_momentum/ \
  --cov=alembic.strategies.s1_ts_momentum --cov-report=term
# Expected: coverage >= 90%

# Sanity: compute signal su SPY 2010-2023
poetry run python -c "
from datetime import date
from alembic.backtest.data.loader import DataLoader
from alembic.backtest.data.universe import load_universe
from alembic.strategies.s1_ts_momentum.signal import compute_s1_signal

loader = DataLoader()
universe = load_universe('s1')
prices = loader.get_aligned_prices(universe, date(2010, 1, 1), date(2023, 12, 31))
signals = compute_s1_signal(prices)

# Final signals should make sense: bull market = mostly positive
final = signals.iloc[-1]
n_positive = (final > 0).sum()
print(f'Tickers with positive signal at end: {n_positive}/{len(final)}')
# 2023 was bull → expect >= 8 positive
assert n_positive >= 8
print('Sanity OK')
"
```

#### Commit

```
[T-102] S1 signal computation

- compute_momentum_12_1: 12-1 momentum (Moskowitz et al. 2012)
- compute_realized_vol: rolling annualized vol
- compute_s1_signal: risk-adjusted momentum
- Property-based tests for sign of signal vs drift
- Anti-look-ahead regression test
- Config file with literature default params

Refs: alembic_v2/01_strategy_design.md §S1
```

---

### T-103 — S1 Strategy Module (Sizing + Interface)

**Status**: OPEN
**Effort**: S (1-2d)
**Dependencies**: T-102

#### Files to create
```
alembic/strategies/s1_ts_momentum/sizing.py
alembic/strategies/s1_ts_momentum/strategy.py
tests/strategies/s1_ts_momentum/test_sizing.py
tests/strategies/s1_ts_momentum/test_strategy.py
```

#### Implementation: sizing.py

```python
"""Sizing per S1: inverse-vol with leverage cap."""
from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class S1SizingParams:
    total_vol_target: float = 0.10
    max_leverage_per_asset: float = 1.5
    max_gross_exposure: float = 2.0
    signal_threshold: float = 0.0
    short_enabled: bool = False


def compute_inverse_vol_weights(
    signals: pd.Series,
    vols: pd.Series,
    params: S1SizingParams,
) -> pd.Series:
    """Compute portfolio weights per ticker, given signals and realized vols.
    
    Args:
        signals: pd.Series, index=ticker, values=signal (risk-adjusted momentum)
        vols: pd.Series, index=ticker, values=realized annualized vol
        params: S1SizingParams
    
    Returns:
        pd.Series with weights summing to <= max_gross_exposure
    """
    # Filter active signals
    active_signals = signals[signals.abs() > params.signal_threshold]
    
    if len(active_signals) == 0:
        return pd.Series(0.0, index=signals.index)
    
    # If short not enabled, drop negative signals
    if not params.short_enabled:
        active_signals = active_signals[active_signals > 0]
    
    n_active = len(active_signals)
    if n_active == 0:
        return pd.Series(0.0, index=signals.index)
    
    # Per-asset vol target (so each asset contributes roughly equally to portfolio vol)
    per_asset_vol_target = params.total_vol_target / np.sqrt(n_active)
    
    # Inverse-vol raw weights
    aligned_vols = vols.reindex(active_signals.index)
    
    raw_weights = pd.Series(0.0, index=signals.index)
    for ticker in active_signals.index:
        sign = np.sign(active_signals[ticker])
        vol = aligned_vols[ticker]
        if vol > 0 and np.isfinite(vol):
            raw_w = sign * per_asset_vol_target / vol
            # Cap per asset leverage
            raw_w = max(min(raw_w, params.max_leverage_per_asset), -params.max_leverage_per_asset)
            raw_weights[ticker] = raw_w
    
    # Scale to max gross exposure if needed
    gross = raw_weights.abs().sum()
    if gross > params.max_gross_exposure:
        raw_weights = raw_weights * (params.max_gross_exposure / gross)
    
    return raw_weights
```

#### Implementation: strategy.py

```python
"""S1 Strategy: Time-Series Momentum implementation of BaseStrategy."""
from datetime import datetime
from pathlib import Path
import yaml

import numpy as np
import pandas as pd

from alembic.strategies.base import (
    BaseStrategy, StrategyContext, StrategyOutput, RebalanceFrequency
)
from alembic.strategies.s1_ts_momentum.signal import (
    S1SignalParams, compute_s1_signal, compute_realized_vol, compute_log_returns
)
from alembic.strategies.s1_ts_momentum.sizing import (
    S1SizingParams, compute_inverse_vol_weights
)


class TimeSeriesMomentumStrategy(BaseStrategy):
    
    def __init__(self, config_path: Path | None = None):
        if config_path is None:
            config_path = Path(__file__).parent / "config.yaml"
        with open(config_path) as f:
            self._config = yaml.safe_load(f)
        
        self._signal_params = S1SignalParams(
            lookback_long_days=self._config["signal"]["lookback_long_days"],
            lookback_skip_days=self._config["signal"]["lookback_skip_days"],
            vol_window_days=self._config["signal"]["vol_window_days"],
            annualization_factor=self._config["signal"]["annualization_factor"],
        )
        self._sizing_params = S1SizingParams(
            total_vol_target=self._config["sizing"]["total_vol_target"],
            max_leverage_per_asset=self._config["sizing"]["max_leverage_per_asset"],
            max_gross_exposure=self._config["sizing"]["max_gross_exposure"],
            signal_threshold=self._config["sizing"]["signal_threshold"],
            short_enabled=self._config["sizing"]["short_enabled"],
        )
    
    @property
    def strategy_id(self) -> str:
        return self._config["strategy_id"]
    
    @property
    def target_allocation_pct(self) -> float:
        return self._config["allocation"]["target_pct"]
    
    @property
    def rebalance_frequency(self) -> RebalanceFrequency:
        return RebalanceFrequency(self._config["trading"]["rebalance_frequency"])
    
    def should_rebalance(self, as_of: datetime, last_rebalance: datetime | None) -> bool:
        if last_rebalance is None:
            return True
        
        if self.rebalance_frequency == RebalanceFrequency.MONTHLY:
            # First business day of month
            return as_of.month != last_rebalance.month
        # Add other frequencies if needed
        return False
    
    def compute_target_weights(self, ctx: StrategyContext) -> StrategyOutput:
        """Compute target weights for S1.
        
        Steps:
        1. Get prices history from context
        2. Compute signal for each ticker
        3. Compute realized vol for each ticker
        4. Apply inverse-vol sizing
        5. Return target weights
        """
        prices = ctx.price_history
        
        # Compute signal at as_of (last row)
        signals_df = compute_s1_signal(prices, self._signal_params)
        latest_signals = signals_df.iloc[-1].dropna()
        
        # Compute realized vol at as_of
        log_returns = compute_log_returns(prices)
        vols_df = compute_realized_vol(log_returns, self._signal_params.vol_window_days)
        latest_vols = vols_df.iloc[-1].dropna()
        
        # Align
        common_tickers = latest_signals.index.intersection(latest_vols.index)
        signals_aligned = latest_signals[common_tickers]
        vols_aligned = latest_vols[common_tickers]
        
        # Sizing
        weights = compute_inverse_vol_weights(signals_aligned, vols_aligned, self._sizing_params)
        
        # Filter zero weights
        target_weights = {t: float(w) for t, w in weights.items() if abs(w) > 1e-6}
        
        rationale = {
            "n_active_signals": int((signals_aligned > self._sizing_params.signal_threshold).sum()),
            "n_positions": len(target_weights),
            "gross_exposure": float(weights.abs().sum()),
            "signals_summary": {
                "max": float(signals_aligned.max()),
                "min": float(signals_aligned.min()),
                "median": float(signals_aligned.median()),
            },
        }
        
        return StrategyOutput(
            strategy_id=self.strategy_id,
            as_of=ctx.as_of,
            target_weights=target_weights,
            confidence=1.0,  # Always full confidence for S1 (deterministic from signal)
            rationale=rationale,
        )
```

#### Tests

Crea `tests/strategies/s1_ts_momentum/test_strategy.py`:

```python
from datetime import date, datetime
import pandas as pd
import pytest

from alembic.strategies.base import StrategyContext, RebalanceFrequency
from alembic.strategies.s1_ts_momentum.strategy import TimeSeriesMomentumStrategy


def make_test_ctx(prices: pd.DataFrame) -> StrategyContext:
    return StrategyContext(
        as_of=prices.index[-1].to_pydatetime(),
        current_portfolio_weights={},
        total_portfolio_value_usd=100_000.0,
        price_history=prices,
        returns_history=prices.pct_change(),
        volume_history=None,
        regime=None,
        news_signals=None,
        params={},
    )


class TestS1Strategy:
    def test_strategy_metadata(self):
        strategy = TimeSeriesMomentumStrategy()
        assert strategy.strategy_id == "s1_ts_momentum"
        assert strategy.target_allocation_pct == 0.40
        assert strategy.rebalance_frequency == RebalanceFrequency.MONTHLY
    
    def test_rebalance_logic_monthly(self):
        strategy = TimeSeriesMomentumStrategy()
        
        last_jan = datetime(2024, 1, 15)
        same_jan = datetime(2024, 1, 20)
        next_feb = datetime(2024, 2, 5)
        
        assert not strategy.should_rebalance(same_jan, last_jan)
        assert strategy.should_rebalance(next_feb, last_jan)
        assert strategy.should_rebalance(last_jan, None)  # Always rebalance first time
    
    def test_compute_target_weights_smoke(self, synthetic_universe_prices):
        strategy = TimeSeriesMomentumStrategy()
        ctx = make_test_ctx(synthetic_universe_prices)
        output = strategy.compute_target_weights(ctx)
        
        assert output.strategy_id == "s1_ts_momentum"
        assert output.as_of == ctx.as_of
        assert isinstance(output.target_weights, dict)
        # Gross exposure ≤ max
        gross = sum(abs(w) for w in output.target_weights.values())
        assert gross <= 2.0 + 1e-6


@pytest.fixture
def synthetic_universe_prices():
    """Multi-ticker synthetic prices for testing."""
    import numpy as np
    np.random.seed(42)
    dates = pd.bdate_range("2020-01-01", "2023-12-31")
    
    data = {}
    for ticker in ["SPY", "TLT", "GLD"]:
        log_returns = np.random.normal(0.0003, 0.012, len(dates))
        data[ticker] = 100 * np.exp(np.cumsum(log_returns))
    
    return pd.DataFrame(data, index=dates)
```

#### Acceptance verification

```bash
poetry run pytest tests/strategies/s1_ts_momentum/ -v
# Expected: all pass

poetry run pytest tests/strategies/s1_ts_momentum/ --cov=alembic.strategies.s1_ts_momentum --cov-report=term
# Expected: >= 85%

# Sanity: strategy run su universe reale
poetry run python -c "
from datetime import date, datetime
from alembic.backtest.data.loader import DataLoader
from alembic.backtest.data.universe import load_universe
from alembic.strategies.s1_ts_momentum.strategy import TimeSeriesMomentumStrategy
from alembic.strategies.base import StrategyContext

loader = DataLoader()
universe = load_universe('s1')
prices = loader.get_aligned_prices(universe, date(2010, 1, 1), date(2023, 12, 31))

ctx = StrategyContext(
    as_of=datetime(2023, 12, 29),
    current_portfolio_weights={},
    total_portfolio_value_usd=100_000.0,
    price_history=prices,
    returns_history=prices.pct_change(),
    volume_history=None, regime=None, news_signals=None, params={},
)

strategy = TimeSeriesMomentumStrategy()
output = strategy.compute_target_weights(ctx)

print(f'Active positions: {len(output.target_weights)}')
print(f'Gross exposure: {sum(abs(w) for w in output.target_weights.values()):.2%}')
print(f'Top 3 holdings:')
top = sorted(output.target_weights.items(), key=lambda x: -abs(x[1]))[:3]
for t, w in top:
    print(f'  {t}: {w:+.2%}')

assert 0 < sum(abs(w) for w in output.target_weights.values()) <= 2.0
print('Sanity OK')
"
```

#### Commit

```
[T-103] S1 strategy module + sizing

- Inverse-vol sizing with leverage caps
- TimeSeriesMomentumStrategy implements BaseStrategy
- Config-driven, deterministic
- Tests covering metadata, rebalance logic, weights computation

Refs: alembic_v2/01_strategy_design.md §S1
```

---

### T-104 — S1 Backtest + Gates Run

**Status**: OPEN
**Effort**: M (3-5d)
**Dependencies**: T-103, T-007 (gates)
**Reference docs**: `/alembic_v2/01_strategy_design.md` §S1, `/alembic_v2/05_validation_and_gates.md`

#### Implementation

Crea adapter per fare girare la strategia nel backtest engine:

```python
# alembic/backtest/engine/strategy_adapter.py
"""Adapter da BaseStrategy → StrategyCallable per BacktestOrchestrator."""
from datetime import datetime
from typing import Callable

from alembic.backtest.engine.data_replay import DataReplay
from alembic.backtest.engine.portfolio import VirtualPortfolio
from alembic.backtest.engine.types import MarketSnapshot, Order, OrderSide
from alembic.strategies.base import BaseStrategy, StrategyContext


def make_strategy_callable(strategy: BaseStrategy) -> Callable:
    """Wrap a BaseStrategy into a callable usable by BacktestOrchestrator."""
    last_rebalance: list[datetime | None] = [None]  # mutable container
    
    def callable_fn(ts, data_replay: DataReplay, portfolio: VirtualPortfolio, market: MarketSnapshot):
        # Check rebalance
        if not strategy.should_rebalance(ts, last_rebalance[0]):
            return []
        
        # Build context
        current_weights = portfolio.mark_to_market(market).weights(market)
        nav = portfolio.mark_to_market(market).total_nav
        ctx = StrategyContext(
            as_of=ts,
            current_portfolio_weights=current_weights,
            total_portfolio_value_usd=nav,
            price_history=data_replay.prices_until(ts),
            returns_history=data_replay.returns_until(ts),
            volume_history=None,
            regime=None,
            news_signals=None,
            params={},
        )
        
        # Compute target weights
        output = strategy.compute_target_weights(ctx)
        
        # Convert target weights → orders (delta from current)
        orders = []
        all_tickers = set(output.target_weights.keys()) | set(current_weights.keys())
        for ticker in all_tickers:
            target_w = output.target_weights.get(ticker, 0.0) * strategy.target_allocation_pct
            current_w = current_weights.get(ticker, 0.0)
            delta_w = target_w - current_w
            
            price = market.price_of(ticker)
            if price is None:
                continue
            
            delta_value = delta_w * nav
            delta_qty = delta_value / price
            
            if abs(delta_qty) < 1:
                continue  # too small to trade
            
            side = OrderSide.BUY if delta_qty > 0 else OrderSide.SELL
            orders.append(Order.market_order(ts, ticker, side, abs(delta_qty), strategy.strategy_id))
        
        last_rebalance[0] = ts
        return orders
    
    return callable_fn
```

Esegui backtest e gates:

```bash
# Crea report dir
mkdir -p reports/s1

# Backtest completo 2003-2023
poetry run python -m alembic.backtest.gates.runner \
    --strategy s1_ts_momentum \
    --start 2003-01-01 \
    --end 2023-12-31 \
    --output reports/s1/gates_full.html
```

#### Acceptance criteria

**OBBLIGATORIO**: tutti i 5 gate devono passare. Se uno fail → HG-5.

Verifica:
- [ ] Gate 1: IC > 0 (sui forward 1-month returns), p-value < 0.01
- [ ] Gate 2: OOS Sharpe / IS Sharpe ≥ 0.5
- [ ] Gate 3: Sharpe median > 0.5 con IQR/median < 0.4 across 20 variants
- [ ] Gate 4: Sharpe > 0.3 in almeno 3 di 4 regimi (RISK_ON, RISK_OFF, GOLDILOCKS, STRESS)
- [ ] Gate 5: DD < 30% in tutti gli stress periods (2008, 2020, 2022)

Atteso (da letteratura): Sharpe OOS 0.5-0.7, DD < 18%, Calmar > 0.4.

#### On gate failure

**Procedura rigorosa**:

1. **Verifica il backtest engine**: re-run sanity check su buy-and-hold SPY. Se anche quello fail → debug engine, non strategy.
2. **Anti-look-ahead check**: re-run `test_no_lookahead.py`. Se fail → debug data_replay.
3. **Data quality**: re-run `validate_universe_data.py`. Se fail → fix data.
4. **Cost model**: troppo aggressivo? Test con 0 costs, se passa → ricalibra costs.
5. **Parameter sensitivity**: gate 3 fail = parametri instabili. Mostra in HG-5.

**MAI** modificare parametri "per far passare". Se necessario:
- Documenta in `DECISIONS.md` perché i parametri di literature non funzionano nel tuo backtest
- Apri HG-5 con analisi completa

#### Commit

```
[T-104] S1 backtest + validation gates

- Strategy adapter for BacktestOrchestrator
- Full backtest 2003-2023 on S1 universe
- All 5 gates passed:
  - Gate 1: IC X.XX (p=YYY)
  - Gate 2: OOS/IS ratio 0.XX
  - Gate 3: Robustness 0.XX
  - Gate 4: 3 of 4 regimes positive
  - Gate 5: All stress periods DD < 30%
- Report: reports/s1/gates_full.html

Refs: alembic_v2/01_strategy_design.md §S1, alembic_v2/05_validation_and_gates.md
```

---

### T-105 — S1 Sensitivity Analysis

**Status**: OPEN
**Effort**: S (1-2d)
**Dependencies**: T-104

Test variants di parametri per documentare robustness e capire dove "il chiosco crolla".

```python
# scripts/s1_sensitivity.py
"""Sensitivity analysis per parametri S1."""
import itertools
import json
import pandas as pd
from datetime import date

from alembic.strategies.s1_ts_momentum.strategy import TimeSeriesMomentumStrategy
# ... (full implementation)

PARAMETER_GRID = {
    "lookback_long_days": [126, 189, 252, 378, 504],
    "lookback_skip_days": [0, 11, 21, 42],
    "vol_window_days": [20, 30, 60, 90, 120],
}

results = []
for combo in itertools.product(*PARAMETER_GRID.values()):
    params = dict(zip(PARAMETER_GRID.keys(), combo))
    # Run backtest, collect Sharpe + DD
    sharpe, dd = run_with_params(params)
    results.append({**params, "sharpe": sharpe, "max_dd": dd})

df = pd.DataFrame(results)
df.to_csv("reports/s1/sensitivity.csv")
df.to_html("reports/s1/sensitivity.html")
print(df.describe())
```

#### Acceptance verification

```bash
poetry run python scripts/s1_sensitivity.py

# Verifica che i parametri base (252, 21, 60) siano near-optimum ma NON peak esatto
# Se il base è peak esatto = sospetto di overfit / lucky params
poetry run python -c "
import pandas as pd
df = pd.read_csv('reports/s1/sensitivity.csv')
base = df[(df['lookback_long_days']==252) & (df['lookback_skip_days']==21) & (df['vol_window_days']==60)]
print('Base config:', base.iloc[0].to_dict())
print(f'Median across all combos: Sharpe={df[\"sharpe\"].median():.2f}, DD={df[\"max_dd\"].median():.2%}')
print(f'Top 10% Sharpe combos:')
print(df.nlargest(int(len(df) * 0.1), 'sharpe'))
"
```

#### Commit

```
[T-105] S1 sensitivity analysis

- Grid search across 80 parameter combinations
- Base config (252/21/60) near-median, robust
- Sharpe surface visualizes parameter sensitivity

Refs: alembic_v2/05_validation_and_gates.md Gate 3
```

---

### MILESTONE B — S1 validated

**Verification**:
```bash
# Tutti i tests Phase B passano
poetry run pytest tests/strategies/s1_ts_momentum/ -v

# Tutti i gates passano
cat reports/s1/gates_full.html | grep -i "PASSED"  # all 5 should be there

# Sensitivity ok
ls reports/s1/sensitivity.csv
```

### 🛑 HUMAN_GATE [HG-Milestone-B]: S1 review

```markdown
## 🛑 HUMAN_GATE [HG-Milestone-B]: S1 Time-Series Momentum validated

**Done**:
- S1 implementato come BaseStrategy
- Backtest 2003-2023 completato
- 5/5 gates passed
- Sensitivity analysis confirms robustness

**Backtest results**:
- OOS Sharpe: 0.XX
- Max DD: XX%
- Calmar: 0.XX

**Files for review**:
- `alembic/strategies/s1_ts_momentum/`
- `reports/s1/gates_full.html`
- `reports/s1/sensitivity.csv`

**Awaiting**:
- Tua review del report
- Approval per merge in main e procedere a Phase C
```

---

## PHASE C — Strategia S3: Cross-Sectional Momentum

**Branch**: `phase-C-s3-momentum`
**Effort totale**: ~3 settimane part-time
**Reference docs**: `/alembic_v2/01_strategy_design.md` §S3

### Approach

S3 è analoga a S1 ma:
- Cross-sectional (rank vs altri ticker), non time-series
- Su equity universe (riusa universe 72 ticker da v1)
- Beta-adjusted momentum
- Output: top decile long, bottom decile excluded

Pattern di implementazione **identico** a S1. Sintetizzo i task.

### T-201 — Universe S3 + liquidity filter

```
alembic/strategies/s3_xs_momentum/config.yaml
alembic/backtest/data/liquidity.py  # filtri liquidity point-in-time
```

Implementazione: porting universe esistente da Alembic v1 + filtro dinamico:
- min market cap 2B
- min ADV 10M USD
- min price 5 USD
- point-in-time (no survivorship)

### T-202 — S3 signal: residual momentum

```python
# alembic/strategies/s3_xs_momentum/signal.py

def compute_beta(ticker_returns, market_returns, window=252):
    """Rolling beta vs market."""
    cov = ticker_returns.rolling(window).cov(market_returns)
    var = market_returns.rolling(window).var()
    return cov / var

def compute_residual_momentum(prices, market_ticker="SPY", lookback=252, skip=21):
    """Beta-adjusted 12-1 momentum."""
    log_returns = np.log(prices / prices.shift(1))
    market_returns = log_returns[market_ticker]
    
    momentum = compute_momentum_12_1(prices, lookback, skip)
    market_momentum = compute_momentum_12_1(prices[[market_ticker]], lookback, skip)
    
    # For each ticker, compute beta
    betas = log_returns.rolling(252).cov(market_returns).div(market_returns.rolling(252).var(), axis=0)
    
    residual = momentum.subtract(betas.mul(market_momentum.values, axis=0), fill_value=0)
    return residual
```

### T-203 — S3 strategy module + backtest + gates

Stesso pattern di T-103 / T-104. Differenze:
- Selection: top N% del rank (default 10% top, 10% bottom excluded)
- Sizing: equal-weight o inverse-vol dentro top decile
- Allocazione target: 20%

**Atteso**: Sharpe OOS 0.4-0.6, DD < 30%, DD severo in momentum crashes (2009, 2020).

### MILESTONE C — S3 validated

Stesso pattern di MILESTONE B.

---

## PHASE E — Strategia S4: News-Driven Tactical Refactor

**Branch**: `phase-E-s4-refactor`
**Effort totale**: ~2 settimane part-time
**Reference docs**: `/alembic_v2/01_strategy_design.md` §S4

### Key difference from S1, S3

S4 NON costruisce signal da zero. **Riusa il codice esistente di Alembic v1**.

### T-401 — Refactor signal aggregation

L'output dell'aggregator esistente (`aggregated_signal` per ticker, EWMA) viene usato come signal.

```python
# alembic/strategies/s4_news_tactical/signal.py
"""Wrapper attorno al signal aggregator esistente di Alembic v1."""
import pandas as pd

# Import dal codice esistente
from alembic.signals.aggregator import AggregatedSignalRepository  # path da verificare nel repo


def get_signal_at(as_of: datetime, universe: list[str], repo: AggregatedSignalRepository) -> pd.Series:
    """Returns signal score per ticker at as_of."""
    signals = {}
    for ticker in universe:
        agg = repo.get_aggregated_signal(ticker, as_of=as_of, horizon=SignalHorizon.SHORT)
        signals[ticker] = agg.aggregated_score if agg else 0.0
    return pd.Series(signals)
```

### T-402 — Strategy module (10% cap)

```python
class NewsTacticalStrategy(BaseStrategy):
    target_allocation_pct = 0.10  # HARD CAP 10%
    rebalance_frequency = RebalanceFrequency.DAILY
    
    def compute_target_weights(self, ctx):
        # Get signals da repo esistente
        signals = get_signal_at(ctx.as_of, universe_72_tickers, self.repo)
        
        # Cross-sectional top 5
        top_5 = signals.nlargest(5)
        
        # Equal weight, allocazione 10% del portafoglio totale = ognuno 2%
        weights = {t: 0.10 / 5 * 0.10 for t in top_5.index}  # in unit of strategy's bucket
        
        return StrategyOutput(...)
```

### T-403 — Backtest + gates (tolleranti)

Riuso del news replay esistente per backtest. Gates con criteri ridotti (S4 è R&D sleeve):
- Gate 1: IC > 0 (anche se p-value > 0.01, ok)
- Gate 2: best effort
- Gate 5: DD < 5% (su 10% allocation, DD nominale piccolo)

**Anche se non passa tutti i gate, S4 entra in portfolio combinato al 10%**. Solo se Sharpe negativo persistente per 6 mesi → retire.

### MILESTONE E — S4 in portfolio

```markdown
## 🛑 HUMAN_GATE [HG-Milestone-E]

**Done**:
- S4 refactored a cross-sectional ranking
- Cap 10% allocation rigido
- Backtest con news replay
- Decay study baseline definita

**Awaiting**: approval per procedere a Phase F (combiner)
```
