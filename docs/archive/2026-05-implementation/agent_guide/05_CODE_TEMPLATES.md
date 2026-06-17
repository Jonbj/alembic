# 05 — Code Templates

**Audience**: agente LLM che implementa Alembic v2.

**Scopo**: template di codice ricorrenti, da copiare/adattare per ogni nuovo task. Riduce drasticamente le decisioni di "come scrivere X" e garantisce consistenza tra moduli.

**Come usarli**: ogni template è un punto di partenza, non immutabile. Adatta a contesto specifico ma mantieni la struttura generale per consistenza.

---

## TPL-01 — BaseStrategy Implementation

Quando l'agente crea una nuova strategia (`s5`, `s6`, ecc. future), usa questo template come scheletro.

```python
"""<Strategy Name> — <one-line description>.

Reference: <paper citation, alembic_v2 doc reference>

Strategy summary:
- Signal: <how computed>
- Sizing: <weighting method>
- Universe: <which assets>
- Rebalance: <frequency>
- Allocation: <X%> of total portfolio
"""
from datetime import datetime
from pathlib import Path
from typing import Any
import logging

import numpy as np
import pandas as pd
import yaml

from alembic.strategies.base import (
    BaseStrategy,
    StrategyContext,
    StrategyOutput,
    StrategyHealth,
    StrategyHealthReport,
    RebalanceFrequency,
)


log = logging.getLogger(__name__)


class <StrategyName>Strategy(BaseStrategy):
    """<One-line description>."""
    
    def __init__(self, config_path: Path | None = None):
        if config_path is None:
            config_path = Path(__file__).parent / "config.yaml"
        with open(config_path) as f:
            self._config = yaml.safe_load(f)
        
        self._validate_config()
        self._compile_params()
    
    def _validate_config(self) -> None:
        """Sanity check sulla config. Fail fast su valori invalidi."""
        required_keys = ["strategy_id", "signal", "sizing", "trading", "allocation"]
        missing = [k for k in required_keys if k not in self._config]
        if missing:
            raise ValueError(f"Config missing required keys: {missing}")
        
        # Type/range checks
        alloc = self._config["allocation"]["target_pct"]
        if not 0 < alloc <= 1:
            raise ValueError(f"target_pct must be in (0, 1], got {alloc}")
    
    def _compile_params(self) -> None:
        """Compila i parametri config in dataclass tipizzati."""
        # Override in subclass se servono dataclass specifici
        pass
    
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
        
        freq = self.rebalance_frequency
        if freq == RebalanceFrequency.DAILY:
            return as_of.date() != last_rebalance.date()
        elif freq == RebalanceFrequency.WEEKLY:
            return as_of.isocalendar().week != last_rebalance.isocalendar().week
        elif freq == RebalanceFrequency.MONTHLY:
            return (as_of.year, as_of.month) != (last_rebalance.year, last_rebalance.month)
        return False
    
    def compute_target_weights(self, ctx: StrategyContext) -> StrategyOutput:
        """Compute target weights. PURE FUNCTION.
        
        Must not:
        - Mutate ctx
        - Access network/DB (data comes via ctx)
        - Use stochastic state (must be deterministic)
        """
        try:
            # 1. Compute signals
            signals = self._compute_signals(ctx)
            
            # 2. Apply sizing
            weights = self._apply_sizing(signals, ctx)
            
            # 3. Filter zero weights
            target_weights = {
                t: float(w) for t, w in weights.items()
                if abs(w) > 1e-6
            }
            
            # 4. Build rationale (debug info)
            rationale = self._build_rationale(signals, weights, ctx)
            
            return StrategyOutput(
                strategy_id=self.strategy_id,
                as_of=ctx.as_of,
                target_weights=target_weights,
                confidence=self._compute_confidence(ctx),
                rationale=rationale,
            )
        
        except Exception as e:
            log.error(f"Strategy {self.strategy_id} failed at {ctx.as_of}: {e}", exc_info=e)
            # Return empty output rather than crash entire backtest/live run
            return StrategyOutput(
                strategy_id=self.strategy_id,
                as_of=ctx.as_of,
                target_weights={},
                confidence=0.0,
                rationale={"error": str(e)},
            )
    
    def health_check(self, ctx: StrategyContext) -> StrategyHealthReport:
        """Health check: data freshness, signal availability, ecc."""
        issues = []
        status = StrategyHealth.GREEN
        
        # Check data freshness
        last_data_ts = ctx.price_history.index.max()
        if (ctx.as_of - last_data_ts).days > 5:
            issues.append(f"Stale data: last point {last_data_ts}, as_of {ctx.as_of}")
            status = StrategyHealth.YELLOW
        
        # Check universe coverage
        expected_assets = len(self._config.get("universe_size_expected", 10))
        actual_assets = ctx.price_history.shape[1]
        if actual_assets < expected_assets * 0.7:
            issues.append(f"Universe coverage: {actual_assets}/{expected_assets}")
            status = StrategyHealth.YELLOW
        
        # Sub-class can override for additional checks
        return StrategyHealthReport(
            strategy_id=self.strategy_id,
            as_of=ctx.as_of,
            status=status,
            issues=issues,
            metrics={
                "n_assets_in_universe": actual_assets,
                "data_freshness_days": (ctx.as_of - last_data_ts).days,
            },
        )
    
    # --- Methods to implement in subclass ---
    
    def _compute_signals(self, ctx: StrategyContext) -> pd.Series:
        """Returns pd.Series indexed by ticker with signal values."""
        raise NotImplementedError
    
    def _apply_sizing(self, signals: pd.Series, ctx: StrategyContext) -> pd.Series:
        """Convert signals to weights."""
        raise NotImplementedError
    
    def _build_rationale(self, signals: pd.Series, weights: pd.Series, ctx: StrategyContext) -> dict[str, Any]:
        return {
            "n_active_signals": int((signals.abs() > 0).sum()),
            "n_positions": int((weights.abs() > 1e-6).sum()),
            "gross_exposure": float(weights.abs().sum()),
            "signal_summary": {
                "max": float(signals.max()) if len(signals) > 0 else 0,
                "min": float(signals.min()) if len(signals) > 0 else 0,
                "median": float(signals.median()) if len(signals) > 0 else 0,
            },
        }
    
    def _compute_confidence(self, ctx: StrategyContext) -> float:
        """Override per strategie con confidence scoring."""
        return 1.0
```

---

## TPL-02 — Strategy Config YAML

Ogni strategia ha un `config.yaml`. Usa questo template:

```yaml
# Strategy config for <strategy_id>
# Reference: <paper citation>, /alembic_v2/01_strategy_design.md §<section>
version: "0.1.0"
last_modified: "YYYY-MM-DD"
strategy_id: "<snake_case_id>"
description: "<one-line description>"

# Signal generation parameters
# IMPORTANTE: questi valori vengono dalla letteratura, NON da optimization.
# Cambiare richiede:
# 1. Documented rationale in DECISIONS.md
# 2. Re-run di tutti i 5 gates
# 3. HG-11 (decisione strategica)
signal:
  lookback_long_days: 252
  lookback_skip_days: 21
  vol_window_days: 60
  # ... altri parametri specifici

# Position sizing
sizing:
  method: "inverse_vol"  # "equal_weight" | "inverse_vol" | "risk_parity"
  total_vol_target: 0.10
  max_leverage_per_asset: 1.5
  max_gross_exposure: 2.0
  signal_threshold: 0.0
  short_enabled: false

# Trading mechanics
trading:
  rebalance_frequency: "MONTHLY"  # "DAILY" | "WEEKLY" | "MONTHLY"
  min_holding_days: 21
  
# Allocazione in portfolio combinato
allocation:
  target_pct: 0.40
  is_rd_sleeve: false  # se true, criteri di validazione più tolleranti

# Universe reference
universe: "s1"  # chiave in config/universe.yaml

# Risk overlays
overlays:
  regime_modulation:
    enabled: false  # true per S2
  event_filter:
    enabled: false  # true per S2, S4

# Monitoring thresholds (per runtime alerts)
monitoring:
  sharpe_30d_warning: 0.0
  sharpe_30d_critical: -0.5
  drawdown_warning: -0.08
  drawdown_critical: -0.15
  ic_decay_warning: 0.0

# Changelog
changelog:
  - "0.1.0: initial version from literature defaults"
```

---

## TPL-03 — Test Fixtures Pattern

`tests/strategies/<strategy_id>/conftest.py`:

```python
"""Fixtures per testing di <strategy_id>."""
from datetime import datetime, date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from alembic.strategies.base import StrategyContext


@pytest.fixture
def synthetic_prices_uptrend() -> pd.DataFrame:
    """Deterministic uptrend prices, multi-ticker."""
    np.random.seed(42)
    dates = pd.bdate_range("2020-01-01", "2023-12-29")
    n = len(dates)
    
    data = {}
    for i, ticker in enumerate(["SPY", "TLT", "GLD", "QQQ", "IWM"]):
        drift = 0.0005 + i * 0.0001  # slight differentiation
        vol = 0.012 + i * 0.001
        returns = np.random.normal(drift, vol, n)
        prices = 100 * np.exp(np.cumsum(returns))
        data[ticker] = prices
    
    return pd.DataFrame(data, index=dates)


@pytest.fixture
def synthetic_prices_downtrend() -> pd.DataFrame:
    """Deterministic downtrend prices."""
    np.random.seed(43)
    dates = pd.bdate_range("2020-01-01", "2023-12-29")
    n = len(dates)
    
    data = {}
    for ticker in ["SPY", "TLT", "GLD"]:
        returns = np.random.normal(-0.0008, 0.015, n)
        prices = 100 * np.exp(np.cumsum(returns))
        data[ticker] = prices
    
    return pd.DataFrame(data, index=dates)


@pytest.fixture
def synthetic_prices_flat() -> pd.DataFrame:
    """Range-bound prices (no trend)."""
    np.random.seed(44)
    dates = pd.bdate_range("2020-01-01", "2023-12-29")
    n = len(dates)
    
    data = {}
    for ticker in ["SPY", "TLT", "GLD"]:
        returns = np.random.normal(0, 0.010, n)
        prices = 100 * np.exp(np.cumsum(returns))
        data[ticker] = prices
    
    return pd.DataFrame(data, index=dates)


def make_strategy_context(
    prices: pd.DataFrame,
    as_of: datetime | None = None,
    portfolio_value: float = 100_000.0,
    current_weights: dict[str, float] | None = None,
    regime: object | None = None,
    news_signals: dict | None = None,
) -> StrategyContext:
    """Helper per costruire StrategyContext per test."""
    if as_of is None:
        as_of = prices.index[-1].to_pydatetime()
    
    return StrategyContext(
        as_of=as_of,
        current_portfolio_weights=current_weights or {},
        total_portfolio_value_usd=portfolio_value,
        price_history=prices,
        returns_history=prices.pct_change(),
        volume_history=None,
        regime=regime,
        news_signals=news_signals,
        params={},
    )


@pytest.fixture
def ctx_uptrend(synthetic_prices_uptrend) -> StrategyContext:
    return make_strategy_context(synthetic_prices_uptrend)


@pytest.fixture
def ctx_downtrend(synthetic_prices_downtrend) -> StrategyContext:
    return make_strategy_context(synthetic_prices_downtrend)


@pytest.fixture
def ctx_flat(synthetic_prices_flat) -> StrategyContext:
    return make_strategy_context(synthetic_prices_flat)


@pytest.fixture
def golden_test_cases() -> list[dict]:
    """Loaded from JSON. Input → expected output pairs."""
    import json
    fixtures_path = Path(__file__).parent / "fixtures" / "golden_cases.json"
    if fixtures_path.exists():
        with open(fixtures_path) as f:
            return json.load(f)
    return []
```

---

## TPL-04 — Strategy Test Suite

`tests/strategies/<strategy_id>/test_strategy.py`:

```python
"""Tests per <StrategyName>Strategy."""
import math
from datetime import datetime

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, strategies as st, settings

from alembic.strategies.<strategy_id>.strategy import <StrategyName>Strategy
from alembic.strategies.base import RebalanceFrequency, StrategyHealth


class TestStrategyMetadata:
    """Test che i metadata della strategy siano consistenti."""
    
    def test_strategy_id_matches_config(self):
        strategy = <StrategyName>Strategy()
        assert strategy.strategy_id == "<expected_id>"
    
    def test_allocation_in_valid_range(self):
        strategy = <StrategyName>Strategy()
        assert 0 < strategy.target_allocation_pct <= 1
    
    def test_rebalance_frequency_valid(self):
        strategy = <StrategyName>Strategy()
        assert isinstance(strategy.rebalance_frequency, RebalanceFrequency)


class TestRebalanceLogic:
    """Test logica should_rebalance."""
    
    def test_first_call_always_rebalances(self):
        strategy = <StrategyName>Strategy()
        assert strategy.should_rebalance(datetime(2024, 1, 1), None) is True
    
    def test_monthly_same_month_no_rebalance(self):
        # Assume strategy is monthly
        strategy = <StrategyName>Strategy()
        if strategy.rebalance_frequency == RebalanceFrequency.MONTHLY:
            jan_15 = datetime(2024, 1, 15)
            jan_28 = datetime(2024, 1, 28)
            assert strategy.should_rebalance(jan_28, jan_15) is False
    
    def test_monthly_different_month_rebalance(self):
        strategy = <StrategyName>Strategy()
        if strategy.rebalance_frequency == RebalanceFrequency.MONTHLY:
            jan_15 = datetime(2024, 1, 15)
            feb_5 = datetime(2024, 2, 5)
            assert strategy.should_rebalance(feb_5, jan_15) is True


class TestComputeTargetWeights:
    """Test del core: compute_target_weights."""
    
    def test_output_format(self, ctx_uptrend):
        strategy = <StrategyName>Strategy()
        output = strategy.compute_target_weights(ctx_uptrend)
        
        assert output.strategy_id == strategy.strategy_id
        assert output.as_of == ctx_uptrend.as_of
        assert isinstance(output.target_weights, dict)
        assert 0 <= output.confidence <= 1
        assert isinstance(output.rationale, dict)
    
    def test_weights_respect_max_gross(self, ctx_uptrend):
        strategy = <StrategyName>Strategy()
        output = strategy.compute_target_weights(ctx_uptrend)
        
        gross = sum(abs(w) for w in output.target_weights.values())
        max_gross = strategy._config["sizing"]["max_gross_exposure"]
        assert gross <= max_gross + 1e-6
    
    def test_weights_respect_per_asset_cap(self, ctx_uptrend):
        strategy = <StrategyName>Strategy()
        output = strategy.compute_target_weights(ctx_uptrend)
        
        max_per_asset = strategy._config["sizing"]["max_leverage_per_asset"]
        for ticker, w in output.target_weights.items():
            assert abs(w) <= max_per_asset + 1e-6, f"{ticker}: {w}"
    
    def test_long_only_when_short_disabled(self, ctx_uptrend):
        strategy = <StrategyName>Strategy()
        if not strategy._config["sizing"]["short_enabled"]:
            output = strategy.compute_target_weights(ctx_uptrend)
            for ticker, w in output.target_weights.items():
                assert w >= 0, f"Short position when short disabled: {ticker}={w}"
    
    def test_deterministic_output(self, ctx_uptrend):
        """Same input → same output (no stochastic state)."""
        strategy = <StrategyName>Strategy()
        out1 = strategy.compute_target_weights(ctx_uptrend)
        out2 = strategy.compute_target_weights(ctx_uptrend)
        assert out1.target_weights == out2.target_weights
    
    def test_no_nan_or_inf_in_weights(self, ctx_uptrend):
        strategy = <StrategyName>Strategy()
        output = strategy.compute_target_weights(ctx_uptrend)
        for ticker, w in output.target_weights.items():
            assert math.isfinite(w), f"{ticker}: {w}"
    
    def test_handles_empty_history_gracefully(self):
        strategy = <StrategyName>Strategy()
        empty_prices = pd.DataFrame(
            {"SPY": []},
            index=pd.DatetimeIndex([], name="date"),
        )
        ctx = make_strategy_context(empty_prices, as_of=datetime(2024, 1, 1))
        
        output = strategy.compute_target_weights(ctx)
        # Should not crash, should return empty or all-zero weights
        assert output.target_weights == {} or all(w == 0 for w in output.target_weights.values())


class TestHealthCheck:
    def test_green_for_normal_data(self, ctx_uptrend):
        strategy = <StrategyName>Strategy()
        report = strategy.health_check(ctx_uptrend)
        assert report.status == StrategyHealth.GREEN
    
    def test_yellow_for_stale_data(self):
        strategy = <StrategyName>Strategy()
        # Stale: last data 10 days ago
        old_dates = pd.bdate_range("2020-01-01", "2023-12-01")
        prices = pd.DataFrame({"SPY": range(len(old_dates))}, index=old_dates)
        ctx = make_strategy_context(prices, as_of=datetime(2024, 1, 1))
        
        report = strategy.health_check(ctx)
        assert report.status in (StrategyHealth.YELLOW, StrategyHealth.RED)


class TestRegressionBugs:
    """Regression tests per bug noti."""
    
    # Aggiungi qui ogni volta che un bug viene fixato.
    # Esempio template:
    
    def test_regression_bug_xyz(self):
        """Bug: <description>. Fixed in commit <hash>.
        
        Per evitare ricorrenza, questo test riproduce input e verifica output corretto.
        """
        # ... (test specifico)
        pass


# Property-based tests (Hypothesis)

class TestProperties:
    @given(
        portfolio_value=st.floats(min_value=10_000, max_value=10_000_000),
    )
    @settings(deadline=5000, max_examples=20)
    def test_weights_scale_with_portfolio_value(self, synthetic_prices_uptrend, portfolio_value):
        """Property: i target_weights non dipendono dal portfolio_value totale.
        
        Sono frazioni (%), quindi il valore totale non li deve cambiare.
        """
        strategy = <StrategyName>Strategy()
        ctx = make_strategy_context(synthetic_prices_uptrend, portfolio_value=portfolio_value)
        output = strategy.compute_target_weights(ctx)
        # Weights are %, indipendent of portfolio value
        # (this test would fail only if strategy mistakenly uses portfolio_value)
```

---

## TPL-05 — Database Migration (Alembic-migrations)

`migrations/versions/YYYYMMDD_HHMM_<description>.py`:

```python
"""<Description>.

Revision ID: <auto-generated>
Revises: <previous revision>
Create Date: YYYY-MM-DD HH:MM:SS.SSSSSS
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "<auto-generated>"
down_revision: Union[str, None] = "<previous_revision>"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply migration."""
    op.create_table(
        "strategy_outputs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("strategy_id", sa.String(50), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("target_weights", sa.JSON, nullable=False),
        sa.Column("rationale", sa.JSON, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("health_status", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), 
                  server_default=sa.func.now(), nullable=False),
    )
    
    op.create_index(
        "idx_strategy_outputs_lookup",
        "strategy_outputs",
        ["strategy_id", "as_of"],
        postgresql_using="btree",
        postgresql_ops={"as_of": "DESC"},
    )
    
    # Unique constraint: una sola output per (strategy, timestamp)
    op.create_unique_constraint(
        "uq_strategy_outputs_strategy_asof",
        "strategy_outputs",
        ["strategy_id", "as_of"],
    )


def downgrade() -> None:
    """Rollback migration. MUST be reversible."""
    op.drop_constraint("uq_strategy_outputs_strategy_asof", "strategy_outputs")
    op.drop_index("idx_strategy_outputs_lookup", table_name="strategy_outputs")
    op.drop_table("strategy_outputs")
```

**Test migration**:

```python
# tests/migrations/test_<migration_name>.py
"""Test che la migration sia idempotente e reversibile."""
import pytest
from alembic import command
from alembic.config import Config


def test_migration_up_down(alembic_config: Config):
    # Apply
    command.upgrade(alembic_config, "head")
    
    # Verify table exists
    # ... (check via SQLAlchemy inspection)
    
    # Rollback
    command.downgrade(alembic_config, "-1")
    
    # Verify table gone
    # ...
    
    # Re-apply (idempotency)
    command.upgrade(alembic_config, "head")
```

---

## TPL-06 — Celery Task with Robust Error Handling

```python
"""<Task purpose>."""
from datetime import datetime, timezone
import logging
from typing import Any

from celery import shared_task
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from alembic.observability.metrics import counter, histogram


log = logging.getLogger(__name__)


class TransientError(Exception):
    """Errore recuperabile via retry (es. network)."""
    pass


class PermanentError(Exception):
    """Errore non recuperabile via retry (es. validation)."""
    pass


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=300,  # 5 min
    soft_time_limit=600,  # 10 min soft
    time_limit=900,  # 15 min hard
)
def <task_name>(self, *args: Any, **kwargs: Any) -> dict:
    """<Task description>.
    
    Args:
        *args, **kwargs: see specific task
    
    Returns:
        Dict with task result + metadata for observability
    
    Raises:
        PermanentError: per validation o errori non recuperabili
        TransientError: per errori recuperabili (will retry)
    """
    task_id = self.request.id
    started_at = datetime.now(timezone.utc)
    
    log.info(
        "<task_name> started",
        extra={"task_id": task_id, "args": args, "kwargs": kwargs},
    )
    
    try:
        with histogram("task_duration_seconds", tags={"task": "<task_name>"}).time():
            result = _do_work(*args, **kwargs)
        
        counter("task_success", tags={"task": "<task_name>"}).inc()
        
        log.info(
            "<task_name> completed",
            extra={
                "task_id": task_id,
                "duration_sec": (datetime.now(timezone.utc) - started_at).total_seconds(),
                "result_summary": _summarize(result),
            },
        )
        
        return {
            "task_id": task_id,
            "status": "success",
            "result": result,
            "started_at": started_at.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
    
    except PermanentError as e:
        # Don't retry permanent errors
        counter("task_failure_permanent", tags={"task": "<task_name>"}).inc()
        log.error(
            "<task_name> failed permanently",
            extra={"task_id": task_id, "error": str(e)},
            exc_info=e,
        )
        # Re-raise without retry
        raise
    
    except TransientError as e:
        # Retry with exponential backoff
        counter("task_failure_transient", tags={"task": "<task_name>"}).inc()
        log.warning(
            "<task_name> transient failure, will retry",
            extra={
                "task_id": task_id,
                "retry_count": self.request.retries,
                "error": str(e),
            },
        )
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
    
    except Exception as e:
        # Unexpected error - log, alert, and re-raise
        counter("task_failure_unexpected", tags={"task": "<task_name>"}).inc()
        log.exception(
            "<task_name> unexpected error",
            extra={"task_id": task_id},
        )
        # Optional: send critical alert
        from alembic.observability.alerts import alert_critical
        alert_critical(
            title=f"Task <task_name> failed unexpectedly",
            details={"task_id": task_id, "error": str(e)},
        )
        raise


def _do_work(*args, **kwargs):
    """Actual business logic. Separated for testability."""
    # ... implementation
    pass


def _summarize(result: Any) -> dict:
    """Summarize result for logging (no sensitive data)."""
    if isinstance(result, dict):
        return {"keys": list(result.keys())[:10], "n_items": len(result)}
    return {"type": type(result).__name__}


# Retry pattern for external calls
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(TransientError),
)
def _external_call(*args, **kwargs):
    """Wrapper for external API calls with retry."""
    try:
        # ... actual call
        pass
    except ConnectionError as e:
        raise TransientError(f"Network error: {e}") from e
    except ValueError as e:
        raise PermanentError(f"Validation error: {e}") from e
```

---

## TPL-07 — Structured Logging Pattern

`alembic/common/logging_config.py`:

```python
"""Centralized structured logging config.

Tutti i log sono JSON, con campi standard:
- timestamp (ISO 8601 UTC)
- level
- logger name
- message
- ... e fields aggiuntivi tramite `extra={}`
"""
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class JSONFormatter(logging.Formatter):
    """Format log records as single-line JSON."""
    
    RESERVED_ATTRS = {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "message",
    }
    
    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add extra fields (passed via extra={} kwarg)
        for key, val in record.__dict__.items():
            if key not in self.RESERVED_ATTRS and not key.startswith("_"):
                data[key] = self._safe_value(val)
        
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(data, default=str)
    
    def _safe_value(self, val: Any) -> Any:
        """Coerce to JSON-serializable."""
        if isinstance(val, (str, int, float, bool, type(None))):
            return val
        if isinstance(val, (list, tuple)):
            return [self._safe_value(v) for v in val]
        if isinstance(val, dict):
            return {k: self._safe_value(v) for k, v in val.items()}
        return str(val)


def setup_logging(level: str = "INFO", log_file: str | None = None) -> None:
    """Configure root logger with JSON format."""
    root = logging.getLogger()
    root.setLevel(level)
    
    # Remove existing handlers
    for handler in root.handlers[:]:
        root.removeHandler(handler)
    
    # Stdout handler
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(JSONFormatter())
    root.addHandler(stdout_handler)
    
    # File handler (optional)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(JSONFormatter())
        root.addHandler(file_handler)
    
    # Silence noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("yfinance").setLevel(logging.WARNING)
```

**Pattern di uso nei moduli**:

```python
import logging
log = logging.getLogger(__name__)

# Standard log
log.info("Signal computed", extra={
    "strategy_id": "s1_ts_momentum",
    "as_of": as_of.isoformat(),
    "n_active_signals": 12,
    "compute_duration_ms": 250,
})

# Error con context
try:
    result = risky_call()
except Exception as e:
    log.error("Risky call failed", extra={
        "strategy_id": "s1_ts_momentum",
        "input_size": len(inputs),
    }, exc_info=e)
    raise
```

---

## TPL-08 — Sanity Check Script Pattern

`scripts/sanity_check_<area>.py`:

```python
#!/usr/bin/env python
"""Sanity check per <area>.

Esegue verifiche di base che dovrebbero SEMPRE passare. Se fail,
indica bug serio nel codice.

Usage:
    poetry run python scripts/sanity_check_<area>.py [--verbose]

Exit codes:
    0: all checks passed
    1: one or more checks failed
"""
import argparse
import logging
import sys
from dataclasses import dataclass
from typing import Callable


@dataclass
class SanityCheck:
    name: str
    description: str
    check_fn: Callable[[], bool]
    critical: bool = True  # se True, fail = stop all
    expected_value: str = ""


def check_data_loader_works() -> bool:
    from datetime import date
    from alembic.backtest.data.loader import DataLoader
    loader = DataLoader()
    df = loader.download("SPY", start=date(2023, 1, 1), end=date(2023, 12, 31))
    return len(df) > 200 and "Adj Close" in df.columns


def check_spy_buy_hold_sharpe() -> bool:
    """SPY 2010-2019 buy-and-hold deve avere Sharpe 0.5-1.0."""
    from datetime import date
    from alembic.backtest.data.loader import DataLoader
    import numpy as np
    
    loader = DataLoader()
    df = loader.download("SPY", start=date(2010, 1, 1), end=date(2019, 12, 31))
    daily_returns = df["Adj Close"].pct_change().dropna()
    sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)
    return 0.5 <= sharpe <= 1.0


def check_anti_lookahead_tests_pass() -> bool:
    """Run anti-look-ahead test suite."""
    import subprocess
    result = subprocess.run(
        ["pytest", "tests/backtest/test_no_lookahead.py", "-q"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


SANITY_CHECKS = [
    SanityCheck(
        name="data_loader",
        description="Data loader funziona e ritorna OHLCV",
        check_fn=check_data_loader_works,
        critical=True,
    ),
    SanityCheck(
        name="spy_buy_hold",
        description="SPY 2010-2019 buy-hold Sharpe in [0.5, 1.0]",
        check_fn=check_spy_buy_hold_sharpe,
        critical=True,
        expected_value="Sharpe ~ 0.7",
    ),
    SanityCheck(
        name="anti_lookahead",
        description="Anti-look-ahead test suite passes",
        check_fn=check_anti_lookahead_tests_pass,
        critical=True,
    ),
    # ... add more
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)
    
    passed = 0
    failed = 0
    
    print(f"Running {len(SANITY_CHECKS)} sanity checks...\n")
    
    for check in SANITY_CHECKS:
        try:
            result = check.check_fn()
            if result:
                print(f"  ✓ {check.name:30s} {check.description}")
                passed += 1
            else:
                print(f"  ✗ {check.name:30s} {check.description}")
                if check.expected_value:
                    print(f"      Expected: {check.expected_value}")
                failed += 1
                if check.critical:
                    print(f"\nCRITICAL CHECK FAILED. STOPPING.")
                    break
        except Exception as e:
            print(f"  ✗ {check.name:30s} ERROR: {e}")
            failed += 1
            if check.critical:
                print(f"\nCRITICAL CHECK ERRORED. STOPPING.")
                break
    
    print(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
```

---

## TPL-09 — PR Description Template

`.github/pull_request_template.md`:

```markdown
## Task

**Task ID**: T-NNN
**Phase**: <A|B|C|D|E|F|G>
**Reference docs**: 
- `/agent_guide/<doc>.md` §<section>
- `/alembic_v2/<doc>.md` §<section>

## What changed

- Added: `path/to/new_file.py` — <one-line purpose>
- Modified: `path/to/existing_file.py` — <what changed>
- Removed: `path/to/old_file.py` — <why>
- Database migration: `migrations/versions/YYYYMMDD_HHMM_*.py` — <description>

## How to test

```bash
# Tests
poetry run pytest tests/<path>/ -v

# Linting
poetry run ruff check alembic/<path>/
poetry run mypy --strict alembic/<path>/

# Sanity check
poetry run python scripts/sanity_check_<area>.py
```

## Acceptance criteria check

- [ ] All unit tests pass
- [ ] Coverage ≥ target (see DR-05)
- [ ] Linting clean
- [ ] Type check strict clean
- [ ] CI green
- [ ] Sanity check passes
- [ ] No TODO/FIXME left
- [ ] No hardcoded secrets

## Dependencies

- **Depends on**: T-NNN (must be merged first)
- **Unblocks**: T-NNN+1

## Decisions made

Documented in `DECISIONS.md`:
- <decision 1>
- <decision 2>

If no non-trivial decisions: "None — followed reference doc exactly."

## Known limitations

- <limitation 1, with link to follow-up issue>
- <limitation 2>

## Screenshots / Reports (if applicable)

For backtest tasks, attach:
- `reports/<strategy>/gates.html`
- `reports/<strategy>/sensitivity.csv`

## Reviewer checklist

- [ ] Code is readable, ben commentato dove necessario
- [ ] Tests are meaningful (not just for coverage)
- [ ] No new dependencies added without justification
- [ ] Backward-compatible OR migration path documented
- [ ] Security considerations (no exposed secrets, input validation)
```

---

## TPL-10 — DECISIONS.md Entry

Quando l'agente prende una decisione non-banale, append a `DECISIONS.md`:

```markdown
## YYYY-MM-DD — [T-NNN] <Short title>

**Context**: 
<2-3 frasi su cosa ha causato la necessità di decidere>

**Options considered**:
A) <option A> — pro/con
B) <option B> — pro/con
C) <option C> — pro/con

**Decision**: <X>

**Rationale**:
<perché X invece di Y/Z. Cita reference se disponibile.>

**Reversible**: yes/no
<se no: spiegare perché irreversibile>

**Reference docs**:
- `/agent_guide/...`
- `/alembic_v2/...`
- External: <paper / blog / docs URL>

**Follow-up**:
<eventuali task creati come conseguenza>
```

**Esempio reale**:

```markdown
## 2026-06-15 — [T-201] S3 universe constituent source

**Context**:
S3 needs an equity universe with point-in-time correct constituents
(no survivorship). Alembic v1 has a static 72-ticker list from 2025.

**Options considered**:
A) Use static v1 list — pro: simple; con: survivorship bias
B) Wikipedia S&P 500 historical snapshots — pro: free; con: must scrape
C) Bloomberg / FactSet — pro: gold standard; con: $$$

**Decision**: B (Wikipedia snapshots + filter to large/mid cap)

**Rationale**:
Survivorship bias would inflate backtest Sharpe by est. 0.2-0.3.
Wikipedia gives quarterly snapshots back to 2007, sufficient for our
backtest range. Scraping effort ~2h one-time.

**Reversible**: yes (can switch to C if budget allows)

**Reference docs**:
- /agent_guide/06_DECISION_RULES.md DR-03
- /alembic_v2/01_strategy_design.md §S3.Universe
- External: https://en.wikipedia.org/wiki/List_of_S%26P_500_companies

**Follow-up**:
- T-201.1: write Wikipedia scraper
- T-201.2: validate constituent list against known historical events
```

---

## TPL-11 — pyproject.toml Setup

Per nuovo dev environment o aggiornamenti dipendenze:

```toml
[tool.poetry]
name = "alembic"
version = "2.0.0"
description = "Personal quant multi-strategy system"
authors = ["You <you@example.com>"]
readme = "README.md"
python = "^3.11"

[tool.poetry.dependencies]
python = "^3.11"

# Core
pandas = "^2.2"
numpy = "^1.26"
scipy = "^1.13"
pyyaml = "^6.0"
python-dateutil = "^2.9"

# Storage
psycopg2-binary = "^2.9"
sqlalchemy = "^2.0"
alembic = "^1.13"
redis = "^5.0"

# Data
yfinance = "^0.2"
pyarrow = "^16.0"
requests = "^2.31"

# Backtest
vectorbt = "^0.27"

# Trading
alpaca-py = "^0.26"
ib-insync = "^0.9"

# Statistics / ML
empyrical = "^0.5"
scikit-learn = "^1.5"
arch = { version = "^7.0", optional = true }

# Orchestration
celery = "^5.4"
tenacity = "^9.0"

# Dashboard
streamlit = { version = "^1.36", optional = true }
plotly = { version = "^5.22", optional = true }

[tool.poetry.group.dev.dependencies]
pytest = "^8.3"
pytest-cov = "^5.0"
pytest-asyncio = "^0.23"
hypothesis = "^6.108"
ruff = "^0.5"
mypy = "^1.10"
ipython = "^8.26"

[tool.poetry.extras]
dashboard = ["streamlit", "plotly"]
arch = ["arch"]

[tool.ruff]
line-length = 110
target-version = "py311"

[tool.ruff.lint]
select = [
    "E", "F", "W",   # pyflakes + pycodestyle
    "I",             # isort
    "B",             # bugbear
    "UP",            # pyupgrade
    "C4",            # comprehensions
    "SIM",           # simplify
    "RET",           # return statements
    "ARG",           # unused arguments
]
ignore = [
    "E501",  # line too long (handled by formatter)
]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["ARG"]  # allow unused fixture args

[tool.mypy]
python_version = "3.11"
strict = true
warn_unused_configs = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
check_untyped_defs = true
warn_redundant_casts = true
warn_unused_ignores = true
warn_return_any = true
no_implicit_reexport = true

[[tool.mypy.overrides]]
module = ["yfinance.*", "vectorbt.*", "ib_insync.*"]
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = [
    "--strict-markers",
    "--strict-config",
    "-ra",
]
markers = [
    "slow: marks tests as slow (deselect with -m 'not slow')",
    "integration: integration tests requiring external services",
    "live: tests that hit live APIs (use sparingly)",
]
filterwarnings = [
    "ignore::DeprecationWarning:yfinance.*",
]

[tool.coverage.run]
source = ["alembic"]
omit = [
    "*/migrations/*",
    "*/__init__.py",
    "*/scripts/*",
]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise NotImplementedError",
    "if TYPE_CHECKING:",
    "if __name__ == .__main__.:",
]
```

---

## TPL-12 — GitHub Actions CI

`.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main, "phase-*"]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: alembic_test
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      
      redis:
        image: redis:7
        ports: ["6379:6379"]
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      
      - name: Install Poetry
        run: pipx install poetry==1.8.3
      
      - name: Install dependencies
        run: poetry install --with dev
      
      # CRITICAL: anti-look-ahead tests run first and MUST pass
      - name: Anti-look-ahead tests (CRITICAL)
        run: poetry run pytest tests/backtest/test_no_lookahead.py -v
      
      - name: Lint
        run: poetry run ruff check alembic/ tests/
      
      - name: Type check
        run: poetry run mypy --strict alembic/
      
      - name: Run tests with coverage
        run: poetry run pytest --cov=alembic --cov-report=term --cov-report=xml -m "not live"
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/alembic_test
          REDIS_URL: redis://localhost:6379/0
      
      - name: Coverage threshold
        run: poetry run python -c "
          import xml.etree.ElementTree as ET
          tree = ET.parse('coverage.xml')
          coverage = float(tree.getroot().attrib['line-rate'])
          print(f'Coverage: {coverage:.1%}')
          assert coverage >= 0.80, f'Coverage {coverage:.1%} below 80% threshold'
          "
      
      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          file: ./coverage.xml
```

---

## TPL-13 — Repository Survey Script

Eseguito dall'agente all'inizio di ogni sessione (riferimento da `00_AGENT_GUIDE.md`):

```python
#!/usr/bin/env python
"""Repo survey: produce un overview del repo per l'agente.

Output: /tmp/repo_survey.txt con tutte le info di contesto.
"""
import subprocess
import sys
from pathlib import Path


def run(cmd: str) -> str:
    """Run shell command, return stdout."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip()


def section(title: str, content: str) -> str:
    return f"\n{'=' * 70}\n{title}\n{'=' * 70}\n{content}\n"


def main():
    sections = []
    
    sections.append(section(
        "REPO STRUCTURE (top 100)",
        run("git ls-tree -r HEAD --name-only | head -100"),
    ))
    
    sections.append(section(
        "TOP-LEVEL FILES",
        run("ls -la"),
    ))
    
    sections.append(section(
        "RECENT COMMITS (last 20)",
        run("git log --oneline -20"),
    ))
    
    sections.append(section(
        "OPEN BRANCHES",
        run("git branch -a"),
    ))
    
    # Docs presence
    for doc in ["README.md", "ARCHITECTURE.md", "CLAUDE.md", "DECISIONS.md"]:
        if Path(doc).exists():
            sections.append(section(
                f"DOC: {doc} (first 50 lines)",
                run(f"head -50 {doc}"),
            ))
    
    sections.append(section(
        "STRATEGIES IN REPO",
        run("find alembic -type d -name 'strategies' -o -name '*strategy*' 2>/dev/null"),
    ))
    
    sections.append(section(
        "EXISTING STRATEGY CLASSES",
        run('grep -r "class.*Strategy" --include="*.py" alembic/ 2>/dev/null | head -20'),
    ))
    
    sections.append(section(
        "REGIME CLASSIFIER LOCATION",
        run('grep -r "regime_classifier\|RegimeDetector\|RegimeState" --include="*.py" alembic/ | head -10'),
    ))
    
    sections.append(section(
        "EXISTING TESTS COUNT",
        run("find tests -name 'test_*.py' | wc -l"),
    ))
    
    sections.append(section(
        "DEPENDENCIES (from pyproject.toml)",
        run("grep -E '^[a-z-]+ = ' pyproject.toml 2>/dev/null || echo 'no pyproject.toml'"),
    ))
    
    sections.append(section(
        "CONFIG FILES",
        run("find . -name '*.yaml' -o -name '*.yml' | grep -v node_modules | head -20"),
    ))
    
    sections.append(section(
        "ENV VARIABLES EXPECTED (from .env.example)",
        run("cat .env.example 2>/dev/null || echo 'no .env.example found'"),
    ))
    
    output = "\n".join(sections)
    
    out_path = Path("/tmp/repo_survey.txt")
    out_path.write_text(output)
    
    print(f"Repo survey saved to {out_path}")
    print(f"Total length: {len(output)} chars")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

---

## Riassunto template

| Template | Quando usarlo |
|---|---|
| TPL-01 BaseStrategy | Ogni nuova strategia |
| TPL-02 Config YAML | Ogni nuova strategia |
| TPL-03 Test Fixtures | conftest.py di ogni strategia |
| TPL-04 Strategy Test Suite | Test della strategia |
| TPL-05 DB Migration | Ogni schema change |
| TPL-06 Celery Task | Ogni nuovo background task |
| TPL-07 Logging | Setup iniziale + uso in moduli |
| TPL-08 Sanity Check Script | Per area critica (data, backtest, ecc.) |
| TPL-09 PR Description | Ogni PR |
| TPL-10 DECISIONS.md Entry | Ogni decisione non-banale |
| TPL-11 pyproject.toml | Setup iniziale + dependency update |
| TPL-12 GitHub Actions CI | Setup iniziale |
| TPL-13 Repo Survey | Inizio di ogni sessione agent |
