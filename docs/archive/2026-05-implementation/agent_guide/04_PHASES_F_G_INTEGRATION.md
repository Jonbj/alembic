# 04 — Phases F & G: Combiner + Deployment

## PHASE F — Portfolio Combiner

**Branch**: `phase-F-combiner`
**Effort totale**: ~4 settimane part-time
**Reference docs**: `/alembic_v2/02_architecture.md` §4, `/alembic_v2/03_backtest_framework.md`

A questo punto S1, S2, S3, S4 sono tutti validati individualmente. La Phase F aggrega gli output in un portafoglio coerente.

### Setup pre-Phase F

```bash
git checkout main
git pull
git checkout -b phase-F-combiner

mkdir -p alembic/portfolio
touch alembic/portfolio/__init__.py
```

---

### T-501 — Portfolio Combiner Base

**Status**: OPEN | **Effort**: L (1-2w) | **Dependencies**: tutte le strategie validate

#### Files to create

```
alembic/portfolio/types.py              # PortfolioConstraints, RiskParams
alembic/portfolio/combiner.py           # PortfolioCombiner base
alembic/portfolio/constraints.py        # Constraint enforcer
tests/portfolio/test_combiner.py
tests/portfolio/test_constraints.py
```

#### Implementation: types

```python
# alembic/portfolio/types.py
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PortfolioConstraints:
    max_gross_exposure: float = 1.5
    max_net_exposure: float = 1.2
    max_single_asset: float = 0.15
    max_sector: float = 0.35
    max_correlation_concentration: float = 0.80


@dataclass(frozen=True)
class RiskParams:
    target_total_vol: float = 0.10
    use_risk_parity: bool = False
    correlation_window_days: int = 90


@dataclass
class CombinerOutput:
    final_target_weights: dict[str, float]
    strategy_contributions: dict[str, dict[str, float]]  # strategy_id -> {ticker: contribution}
    constraints_breached: list[str]
    portfolio_gross_exposure: float
    portfolio_net_exposure: float
    estimated_portfolio_vol: float
```

#### Implementation: combiner base

```python
# alembic/portfolio/combiner.py
"""Aggrega StrategyOutput in target weights finali del portafoglio."""
from collections import defaultdict
from dataclasses import dataclass
import logging
import pandas as pd

from alembic.strategies.base import StrategyOutput
from alembic.portfolio.types import (
    PortfolioConstraints, RiskParams, CombinerOutput
)
from alembic.portfolio.constraints import enforce_constraints


log = logging.getLogger(__name__)


class PortfolioCombiner:
    """Aggrega output multi-strategy in portfolio weights finali."""
    
    def __init__(
        self,
        constraints: PortfolioConstraints,
        risk_params: RiskParams,
    ):
        self.constraints = constraints
        self.risk_params = risk_params
    
    def combine(
        self,
        strategy_outputs: list[StrategyOutput],
        strategy_allocations: dict[str, float],  # strategy_id -> target_pct
        cov_matrix: pd.DataFrame | None = None,
    ) -> CombinerOutput:
        """Aggrega outputs per produrre target weights finali.
        
        Steps:
        1. Scale ogni strategia per il suo target_allocation_pct
        2. Aggrega ticker-by-ticker (alcuni ticker possono apparire in più strategie)
        3. Apply hard constraints (sector, concentration, max single)
        4. Vol targeting (se cov_matrix disponibile)
        5. Final cap su gross exposure
        """
        # Step 1+2: aggrega
        contributions: dict[str, dict[str, float]] = defaultdict(dict)
        aggregated: dict[str, float] = defaultdict(float)
        
        for output in strategy_outputs:
            alloc = strategy_allocations.get(output.strategy_id, 0.0)
            for ticker, weight in output.target_weights.items():
                contribution = weight * alloc
                aggregated[ticker] += contribution
                contributions[output.strategy_id][ticker] = contribution
        
        # Step 3: constraints
        constrained_weights, breaches = enforce_constraints(
            dict(aggregated), self.constraints
        )
        
        # Step 4: vol targeting (se cov disponibile)
        if cov_matrix is not None:
            portfolio_vol = self._estimate_portfolio_vol(constrained_weights, cov_matrix)
            if portfolio_vol > self.risk_params.target_total_vol:
                scale = self.risk_params.target_total_vol / portfolio_vol
                constrained_weights = {k: v * scale for k, v in constrained_weights.items()}
                log.info(f"Vol scaling applied: {scale:.3f} (vol {portfolio_vol:.2%} → target {self.risk_params.target_total_vol:.2%})")
        else:
            portfolio_vol = 0.0
        
        # Step 5: final gross exposure cap
        gross = sum(abs(w) for w in constrained_weights.values())
        if gross > self.constraints.max_gross_exposure:
            scale = self.constraints.max_gross_exposure / gross
            constrained_weights = {k: v * scale for k, v in constrained_weights.items()}
            log.info(f"Gross exposure cap applied: scale {scale:.3f}")
        
        net = sum(constrained_weights.values())
        
        return CombinerOutput(
            final_target_weights=constrained_weights,
            strategy_contributions=dict(contributions),
            constraints_breached=breaches,
            portfolio_gross_exposure=sum(abs(w) for w in constrained_weights.values()),
            portfolio_net_exposure=net,
            estimated_portfolio_vol=portfolio_vol,
        )
    
    def _estimate_portfolio_vol(
        self,
        weights: dict[str, float],
        cov_matrix: pd.DataFrame,
    ) -> float:
        """Compute portfolio vol given weights + cov matrix."""
        common = [t for t in weights if t in cov_matrix.index]
        if not common:
            return 0.0
        
        w_vec = pd.Series({t: weights[t] for t in common})
        sub_cov = cov_matrix.loc[common, common]
        
        port_var = w_vec @ sub_cov @ w_vec
        return float(port_var ** 0.5)
```

#### Implementation: constraint enforcer

```python
# alembic/portfolio/constraints.py
import logging
from alembic.portfolio.types import PortfolioConstraints

log = logging.getLogger(__name__)


# Mapping ticker → sector (semplificato; in produzione load da DB o yfinance info)
SECTOR_MAP = {
    "SPY": "EQUITY_INDEX",
    "QQQ": "EQUITY_INDEX",
    "IWM": "EQUITY_INDEX",
    "VEA": "EQUITY_INTL",
    "VWO": "EQUITY_INTL",
    "EWJ": "EQUITY_INTL",
    "TLT": "RATES",
    "IEF": "RATES",
    "SHY": "RATES",
    "TIP": "RATES",
    "LQD": "CREDIT",
    "HYG": "CREDIT",
    "GLD": "GOLD",
    "DBC": "COMMODITY",
    "VNQ": "REITS",
    # ... popolare per equity tickers (S3 universe)
}


def get_sector(ticker: str) -> str:
    return SECTOR_MAP.get(ticker, "OTHER")


def enforce_constraints(
    weights: dict[str, float],
    constraints: PortfolioConstraints,
    max_iterations: int = 10,
) -> tuple[dict[str, float], list[str]]:
    """Apply constraints iteratively.
    
    Returns:
        (constrained_weights, list of breaches with description)
    """
    breaches = []
    current = dict(weights)
    
    for iteration in range(max_iterations):
        modified = False
        
        # 1. Max single asset
        for ticker, w in list(current.items()):
            if abs(w) > constraints.max_single_asset:
                sign = 1 if w > 0 else -1
                breach_msg = f"Single asset {ticker}: {w:.2%} > {constraints.max_single_asset:.2%}"
                breaches.append(breach_msg)
                current[ticker] = sign * constraints.max_single_asset
                modified = True
        
        # 2. Max sector
        sector_weights: dict[str, float] = {}
        for ticker, w in current.items():
            sec = get_sector(ticker)
            sector_weights[sec] = sector_weights.get(sec, 0) + abs(w)
        
        for sec, total in sector_weights.items():
            if total > constraints.max_sector:
                breach_msg = f"Sector {sec}: {total:.2%} > {constraints.max_sector:.2%}"
                breaches.append(breach_msg)
                scale = constraints.max_sector / total
                for ticker in list(current.keys()):
                    if get_sector(ticker) == sec:
                        current[ticker] *= scale
                modified = True
        
        if not modified:
            break
    
    return current, list(set(breaches))  # dedupe
```

#### Acceptance

```bash
poetry run pytest tests/portfolio/ -v

# Sanity: combinare 4 strategie con outputs sintetici
poetry run python -c "
from alembic.portfolio.combiner import PortfolioCombiner
from alembic.portfolio.types import PortfolioConstraints, RiskParams
from alembic.strategies.base import StrategyOutput
from datetime import datetime

s1 = StrategyOutput('s1_ts_momentum', datetime.now(), {'SPY': 0.5, 'TLT': 0.3, 'GLD': 0.2}, 1.0, {})
s2 = StrategyOutput('s2_vrp', datetime.now(), {'SPY': 0.3}, 1.0, {})  # short put = SPY equity exposure
s3 = StrategyOutput('s3_xs_momentum', datetime.now(), {'AAPL': 0.4, 'MSFT': 0.3, 'NVDA': 0.3}, 1.0, {})
s4 = StrategyOutput('s4_news_tactical', datetime.now(), {'TSLA': 0.2, 'AAPL': 0.2}, 1.0, {})

allocations = {'s1_ts_momentum': 0.40, 's2_vrp': 0.30, 's3_xs_momentum': 0.20, 's4_news_tactical': 0.10}

combiner = PortfolioCombiner(PortfolioConstraints(), RiskParams())
result = combiner.combine([s1, s2, s3, s4], allocations)

print(f'Final weights: {result.final_target_weights}')
print(f'Gross: {result.portfolio_gross_exposure:.2%}')
print(f'Net: {result.portfolio_net_exposure:.2%}')
print(f'Breaches: {result.constraints_breached}')

# Sanity: SPY aggregato da S1 + S2 = 0.5*0.4 + 0.3*0.3 = 0.29
assert abs(result.final_target_weights.get('SPY', 0) - 0.29) < 0.01 or 'Single asset SPY' in str(result.constraints_breached)
print('OK')
"
```

#### Commit

```
[T-501] Portfolio combiner base

- Aggregates StrategyOutputs scaled by allocation
- Per-strategy contribution tracking
- Constraint enforcer (max single, max sector, iterative)
- Sector mapping for equity/bond/credit/commodity

Refs: alembic_v2/02_architecture.md §4
```

---

### T-502 — Risk Parity Overlay

**Status**: OPEN | **Effort**: M (3-5d) | **Dependencies**: T-501

Implementa risk parity allocation cross-strategy.

```python
# alembic/portfolio/risk_parity.py
"""Risk parity weights based on strategy ex-ante volatility."""
import numpy as np
import pandas as pd


def compute_risk_parity_weights(
    strategy_returns: pd.DataFrame,  # columns = strategy_id, rows = days
    lookback_days: int = 90,
) -> dict[str, float]:
    """Inverse-vol risk parity (semplificato).
    
    For HRP più sofisticato, usare riskfolio-lib.
    """
    recent = strategy_returns.tail(lookback_days)
    vols = recent.std() * np.sqrt(252)
    
    # Inverse vol weights
    inv_vols = 1 / vols
    weights = inv_vols / inv_vols.sum()
    
    return weights.to_dict()
```

#### Acceptance + Commit

```bash
poetry run pytest tests/portfolio/test_risk_parity.py -v
```

```
[T-502] Risk parity overlay for strategy allocation

- Inverse-vol weights based on rolling 90d strategy returns
- Replaces fixed 40/30/20/10 when enabled
- Sanity tested against ex-ante target

Refs: alembic_v2/02_architecture.md §4
```

---

### T-503 — Cross-Strategy Constraint Enforcer

**Status**: OPEN | **Effort**: M (3-5d) | **Dependencies**: T-501

Estende T-501 con constraint cross-strategy:
- Stesso ticker richiesto da più strategie: aggregare
- Constraint logging dettagliato: quale strategia ha causato breach
- Iterative resolution stabile

```python
# Extension to combiner.py
def combine_with_attribution(self, ...) -> CombinerOutput:
    """Like combine() but with detailed breach attribution.
    
    Per ogni constraint breach, traccia: quale strategia ha contribuito di più
    al ticker/sector violato.
    """
    ...
```

#### Commit

```
[T-503] Cross-strategy constraint enforcer with attribution

- Tracks which strategy caused each breach
- Iterative resolution converges within 10 iterations
- Logs delta between requested and actual weights

Refs: alembic_v2/02_architecture.md §4
```

---

### T-504 — Vol Targeting Overlay

**Status**: OPEN | **Effort**: S (1-2d) | **Dependencies**: T-501, T-503

Già parzialmente in T-501, qui estendi con:
- Calcolo cov matrix da returns history multi-asset
- Backward-looking 90d window
- Vol forecast adjustment (EWMA)

```python
# alembic/portfolio/vol_targeting.py
import pandas as pd
import numpy as np


def estimate_cov_matrix(
    returns_df: pd.DataFrame,
    method: str = "sample",  # "sample" | "ewma" | "ledoit_wolf"
    window: int = 90,
    halflife: int = 30,
) -> pd.DataFrame:
    recent = returns_df.tail(window)
    
    if method == "sample":
        cov = recent.cov() * 252  # annualized
    elif method == "ewma":
        cov = recent.ewm(halflife=halflife).cov().iloc[-len(recent.columns):]
        cov = cov * 252
    elif method == "ledoit_wolf":
        from sklearn.covariance import LedoitWolf
        lw = LedoitWolf().fit(recent.fillna(0))
        cov = pd.DataFrame(lw.covariance_ * 252, index=recent.columns, columns=recent.columns)
    
    return cov
```

#### Commit

```
[T-504] Vol targeting overlay

- Cov matrix estimation: sample, EWMA, Ledoit-Wolf
- Portfolio vol estimation
- Scaling to target_total_vol

Refs: alembic_v2/02_architecture.md §4
```

---

### T-505 — Full Multi-Strategy Backtest

**Status**: OPEN | **Effort**: M (3-5d) | **Dependencies**: T-501..T-504

Esegui backtest dell'intero sistema combinato 2010-2023.

```bash
poetry run python scripts/run_combined_backtest.py \
  --start 2010-01-01 \
  --end 2023-12-31 \
  --strategies s1,s2,s3,s4 \
  --allocations 0.4,0.3,0.2,0.1 \
  --output reports/combined/full_backtest.html
```

#### Acceptance criteria

- [ ] Backtest completa senza errori
- [ ] Sharpe combinato OOS netto costi ≥ 0.8 (target 1.0-1.2)
- [ ] Max DD combined ≤ 18%
- [ ] Diversification ratio > 1.3 (vol equal-weight / vol combined)
- [ ] Per-strategy attribution disponibile

#### On failure

| Failure | Diagnostic | Action |
|---|---|---|
| Sharpe < 0.8 | Strategy correlation troppo alta? | Check correlation matrix output |
| DD > 18% | S2 stress crash? | Verifica overlay attivi nel combiner |
| Diversification < 1.3 | Strategie troppo correlate | Re-validate S1 vs S3 (entrambi momentum) |

#### Commit

```
[T-505] Full multi-strategy backtest

- Combined backtest 2010-2023 net of costs
- Sharpe X.XX OOS, DD XX%, diversification XX
- Per-strategy attribution + correlation matrix
- HTML report with charts

Refs: alembic_v2/02_architecture.md §4
```

---

### MILESTONE F — Combined System Validated

### 🛑 HUMAN_GATE [HG-Milestone-F]

```markdown
## 🛑 HUMAN_GATE [HG-Milestone-F]: Combined System validated

**Done**:
- 4 strategie validate, integrate via combiner
- Risk parity + vol targeting + constraints
- Backtest 2010-2023 multi-strategy

**Critical results**:
- Combined OOS Sharpe: X.XX (target 1.0-1.2)
- Combined Max DD: XX%
- Strategy correlation matrix [allegata]
- Diversification ratio: X.X
- Per-strategy contribution to Sharpe:
  - S1: XX%
  - S2: XX%
  - S3: XX%
  - S4: XX%

**Files for review**:
- `alembic/portfolio/`
- `reports/combined/full_backtest.html`

**Awaiting**: approval per procedere a Phase G (deployment)
```

---

## PHASE G — Production Deployment

**Branch**: `phase-G-deployment`
**Effort totale**: ~8 settimane part-time (include 90gg paper continuous monitoring)
**Reference docs**: `/alembic_v2/02_architecture.md` §6, `/alembic_v2/05_validation_and_gates.md`

### Setup

```bash
git checkout main
git pull
git checkout -b phase-G-deployment
```

---

### T-601 — Celery Multi-Strategy Orchestration

**Status**: OPEN | **Effort**: M (3-5d) | **Dependencies**: tutte le strategie

Estendi Celery worker esistente di Alembic v1 per gestire multi-strategy.

#### Files to create

```
alembic/scheduler/multi_strategy_tasks.py
alembic/scheduler/strategy_registry.py
config/celery_schedule.yaml
```

#### Implementation

```python
# alembic/scheduler/strategy_registry.py
"""Registry per active strategies."""
from typing import Type
from alembic.strategies.base import BaseStrategy
from alembic.strategies.s1_ts_momentum.strategy import TimeSeriesMomentumStrategy
from alembic.strategies.s2_vrp.strategy import VolatilityRiskPremiumStrategy
from alembic.strategies.s3_xs_momentum.strategy import CrossSectionalMomentumStrategy
from alembic.strategies.s4_news_tactical.strategy import NewsTacticalStrategy


STRATEGY_REGISTRY: dict[str, Type[BaseStrategy]] = {
    "s1_ts_momentum": TimeSeriesMomentumStrategy,
    "s2_vrp": VolatilityRiskPremiumStrategy,
    "s3_xs_momentum": CrossSectionalMomentumStrategy,
    "s4_news_tactical": NewsTacticalStrategy,
}


def load_strategy(strategy_id: str) -> BaseStrategy:
    if strategy_id not in STRATEGY_REGISTRY:
        raise ValueError(f"Unknown strategy: {strategy_id}")
    return STRATEGY_REGISTRY[strategy_id]()


def active_strategies() -> list[BaseStrategy]:
    """Returns active strategies from config."""
    import yaml
    with open("config/alembic_v2.yaml") as f:
        config = yaml.safe_load(f)
    return [load_strategy(sid) for sid in config["active_strategies"]]
```

```python
# alembic/scheduler/multi_strategy_tasks.py
from celery import shared_task
from datetime import datetime, timezone
import logging

from alembic.scheduler.strategy_registry import active_strategies
from alembic.portfolio.combiner import PortfolioCombiner
from alembic.portfolio.types import PortfolioConstraints, RiskParams
from alembic.brokers.alpaca_adapter import AlpacaAdapter
from alembic.brokers.ibkr_adapter import IBKRAdapter
# Persistence
from alembic.storage.strategy_outputs import StrategyOutputRepository
from alembic.storage.portfolio_decisions import PortfolioDecisionRepository


log = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def compute_strategy_signals(self):
    """Daily 06:00 ET: per ogni strategia, compute target weights."""
    repo = StrategyOutputRepository()
    
    for strategy in active_strategies():
        try:
            ctx = build_strategy_context(strategy)
            output = strategy.compute_target_weights(ctx)
            repo.persist(output)
            log.info(f"Computed signals for {strategy.strategy_id}")
        except Exception as e:
            log.error(f"Failed to compute {strategy.strategy_id}: {e}", exc_info=e)
            self.retry(countdown=300, exc=e)


@shared_task(bind=True, max_retries=2)
def combine_and_rebalance(self):
    """Daily 06:30 ET: aggrega outputs, applica combiner, place orders."""
    output_repo = StrategyOutputRepository()
    decision_repo = PortfolioDecisionRepository()
    
    # 1. Load today's outputs
    today = datetime.now(timezone.utc).date()
    outputs = output_repo.load_today(today)
    if not outputs:
        log.warning("No strategy outputs for today, skipping rebalance")
        return
    
    # 2. Combine
    combiner = PortfolioCombiner(PortfolioConstraints(), RiskParams())
    allocations = load_strategy_allocations()
    cov = compute_cov_matrix()  # from price history
    result = combiner.combine(outputs, allocations, cov)
    
    # 3. Persist decision
    decision_repo.persist(result)
    
    # 4. Check circuit breaker
    from alembic.risk.monitor import is_circuit_breaker_active
    if is_circuit_breaker_active():
        log.warning("Circuit breaker active, blocking new orders")
        return
    
    # 5. Compute deltas vs current portfolio (from broker)
    # Use Alpaca for equity, IBKR for options
    alpaca = AlpacaAdapter()
    ibkr = IBKRAdapter(paper=True)
    
    current_equity = {p.symbol: p.quantity for p in alpaca.get_positions()}
    current_options = ibkr.get_positions()  # filter to options
    
    # 6. Generate orders
    orders = generate_orders(result.final_target_weights, current_equity, current_options)
    
    # 7. Submit
    for order in orders:
        if order.is_option:
            ibkr.submit_order(order)
        else:
            alpaca.submit_order(order)
        log.info(f"Submitted order: {order}")


@shared_task
def monitor_positions():
    """Hourly during market: check stops, exits, position health."""
    # ... (vedi T-602)
    ...


@shared_task
def daily_reconciliation():
    """Post-close: reconcile fills with broker, snapshot portfolio."""
    ...
```

#### Schedule config

```yaml
# config/celery_schedule.yaml
beat_schedule:
  compute-strategy-signals:
    task: alembic.scheduler.multi_strategy_tasks.compute_strategy_signals
    schedule: "0 6 * * 1-5"  # 06:00 ET weekdays
    options:
      timezone: "America/New_York"
  
  combine-and-rebalance:
    task: alembic.scheduler.multi_strategy_tasks.combine_and_rebalance
    schedule: "30 6 * * 1-5"  # 06:30 ET weekdays
    options:
      timezone: "America/New_York"
  
  monitor-positions:
    task: alembic.scheduler.multi_strategy_tasks.monitor_positions
    schedule: "*/30 9-16 * * 1-5"  # every 30min during market
    options:
      timezone: "America/New_York"
  
  daily-reconciliation:
    task: alembic.scheduler.multi_strategy_tasks.daily_reconciliation
    schedule: "0 17 * * 1-5"  # 17:00 ET post-close
    options:
      timezone: "America/New_York"
  
  weekly-decay-study:
    task: alembic.scheduler.multi_strategy_tasks.weekly_decay_study
    schedule: "0 6 * * 0"  # Sunday 06:00 UTC
```

#### Acceptance

```bash
# Run worker in dev mode
celery -A alembic worker -B --loglevel=info

# Trigger manualmente
celery -A alembic call alembic.scheduler.multi_strategy_tasks.compute_strategy_signals

# Verify outputs persistiti
poetry run python -c "
from alembic.storage.strategy_outputs import StrategyOutputRepository
from datetime import date
repo = StrategyOutputRepository()
outputs = repo.load_today(date.today())
print(f'Outputs today: {len(outputs)}')
for o in outputs:
    print(f'  {o.strategy_id}: {len(o.target_weights)} positions')
"
```

#### Commit

```
[T-601] Celery multi-strategy orchestration

- Strategy registry with 4 active strategies
- Daily signal computation + rebalance tasks
- Hourly position monitoring during market hours
- Post-close reconciliation
- Routing: equity → Alpaca, options → IBKR

Refs: alembic_v2/02_architecture.md §6
```

---

### T-602 — Risk Monitor Multi-Strategy

**Status**: OPEN | **Effort**: M (3-5d) | **Dependencies**: T-601

Estende risk monitor esistente per:
- Aggregate metrics cross-strategy
- Per-strategy DD tracking
- Circuit breaker triggers (combined DD > 15%, vol > 1.5×target)
- Option-specific risk: assignment risk, gamma exposure, vega

```python
# alembic/risk/multi_strategy_monitor.py
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass
class RiskSnapshot:
    as_of: date
    portfolio_nav: float
    portfolio_drawdown: float
    realized_vol_30d: float
    realized_vol_90d: float
    
    per_strategy_dd: dict[str, float]
    per_strategy_sharpe_30d: dict[str, float]
    
    option_exposure: float  # absolute notional of options
    option_gamma_total: float
    option_vega_total: float
    assignment_risk_contracts: int  # count of positions with delta < -0.50
    
    circuit_breaker_active: bool
    circuit_breaker_reasons: list[str]


def compute_risk_snapshot(as_of: date) -> RiskSnapshot:
    ...


def check_circuit_breaker(snapshot: RiskSnapshot) -> tuple[bool, list[str]]:
    """Returns (should_block_new_orders, reasons)."""
    reasons = []
    
    if snapshot.portfolio_drawdown < -0.15:
        reasons.append(f"Portfolio DD {snapshot.portfolio_drawdown:.1%} < -15%")
    
    if snapshot.realized_vol_30d > 0.15:  # 1.5× target 10%
        reasons.append(f"30d vol {snapshot.realized_vol_30d:.1%} > 15%")
    
    for strategy_id, dd in snapshot.per_strategy_dd.items():
        if dd < -0.20:
            reasons.append(f"{strategy_id} DD {dd:.1%} < -20%")
    
    if snapshot.assignment_risk_contracts > 0:
        reasons.append(f"{snapshot.assignment_risk_contracts} options at assignment risk")
    
    return len(reasons) > 0, reasons
```

#### Commit

```
[T-602] Multi-strategy risk monitor

- Aggregate NAV, drawdown, vol tracking
- Per-strategy decomposition
- Option-specific risk (gamma, vega, assignment)
- Circuit breaker with multiple triggers
- Hourly checks during market hours

Refs: alembic_v2/02_architecture.md §6, alembic_v2/05_validation_and_gates.md §2
```

---

### T-603 — Dashboard

**Status**: OPEN | **Effort**: L (1-2w) | **Dependencies**: T-602

#### Decisione tool

| Tool | Pro | Contro | Verdict |
|---|---|---|---|
| Grafana + Prometheus | Production-grade, alert built-in | Setup pesante per single-user | Per HG-3 |
| Custom Streamlit | Quick, pythonic, sufficient per single-user | Meno features | **Default** |
| Custom React | Fully customizable | Effort enorme | No |

**Default**: Streamlit per minimo effort, sufficiente per single-user. Se future scale → Grafana.

#### Implementation outline

```python
# alembic/dashboard/app.py
"""Streamlit dashboard."""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from alembic.storage.portfolio_snapshots import PortfolioSnapshotRepository
from alembic.risk.multi_strategy_monitor import compute_risk_snapshot
from datetime import date, timedelta


st.set_page_config(page_title="Alembic Dashboard", layout="wide")
st.title("Alembic v2 — Multi-Strategy Quant System")

# Sidebar
with st.sidebar:
    st.header("Filters")
    end_date = st.date_input("End date", date.today())
    lookback = st.selectbox("Lookback", ["30d", "90d", "1y", "All"])

# Top metrics row
col1, col2, col3, col4 = st.columns(4)
risk = compute_risk_snapshot(end_date)
col1.metric("NAV", f"${risk.portfolio_nav:,.0f}")
col2.metric("DD", f"{risk.portfolio_drawdown:.1%}")
col3.metric("30d Vol", f"{risk.realized_vol_30d:.1%}")
col4.metric("Circuit Breaker", "🟢 OFF" if not risk.circuit_breaker_active else "🔴 ON")

# Charts
st.header("Performance")
nav_series = load_nav_series(end_date - timedelta(days=lookback_to_days(lookback)), end_date)
fig = go.Figure()
fig.add_trace(go.Scatter(x=nav_series.index, y=nav_series.values, name="NAV"))
st.plotly_chart(fig, use_container_width=True)

st.header("Per-Strategy Attribution")
attribution = load_strategy_attribution(end_date)
st.bar_chart(attribution)

st.header("Open Positions")
positions = load_open_positions()
st.dataframe(positions)

st.header("Recent Decisions")
decisions = load_recent_decisions(n=20)
st.dataframe(decisions)

st.header("Alerts")
alerts = load_recent_alerts(n=10)
for alert in alerts:
    st.warning(f"{alert.timestamp}: {alert.message}")
```

#### Acceptance

```bash
poetry run streamlit run alembic/dashboard/app.py
# Open browser, verifica tutte le sezioni renderano
```

#### Commit

```
[T-603] Streamlit dashboard

- NAV, DD, vol metrics row
- Performance chart with strategy attribution
- Open positions table
- Recent decisions log
- Recent alerts feed

Refs: alembic_v2/02_architecture.md §6
```

---

### T-604 — Paper Trading 90 Days

**Status**: OPEN | **Effort**: continuous (90 days)
**Dependencies**: T-601, T-602, T-603

#### Setup

```bash
# Avvia Celery worker + beat
celery -A alembic worker -B --loglevel=info --logfile=/var/log/alembic/celery.log &

# Avvia dashboard
streamlit run alembic/dashboard/app.py --server.port 8501 &

# Verify systemd services (consigliato in produzione)
sudo systemctl status alembic-worker
sudo systemctl status alembic-dashboard
```

#### Daily checks per l'agente

Per i 90 giorni di paper, l'agente fa daily check:

```bash
# Cron: ogni giorno alle 18:00 ET (post-close + 1h)
poetry run python scripts/daily_health_check.py

# Cosa controlla:
# 1. Celery beat ha eseguito tutti i scheduled tasks oggi
# 2. Tutte le strategie hanno prodotto outputs oggi
# 3. Combiner ha eseguito senza breach gravi
# 4. Orders sono stati submitted/filled
# 5. Risk metrics dentro tolerance
# 6. Nessun critical alert non-acknowledged
# 7. Live performance vs backtest expected: entro 1σ
```

#### Weekly checks

Ogni domenica:
- Decay study automatico (T-605)
- Report settimanale generato e archiviato

#### HUMAN_GATE rolling: HG-Live-Monitoring

L'utente riceve daily summary. Per problemi seri:

```markdown
## 🛑 HUMAN_GATE [HG-Live-Monitoring-Day-N]

**Status**: 🔴 ATTENZIONE

**Issue rilevati oggi (giorno N/90)**:
- ...

**Recommended action**:
- ...

**Awaiting**: tua decisione
```

#### Acceptance per Milestone G

- [ ] 90 giorni consecutivi senza unplanned downtime > 1h
- [ ] Performance live entro ±1σ del backtest expected
- [ ] Nessun critical alert non-resolved
- [ ] Tutte le strategie hanno decay verdict ≥ "WATCHING" (no DEAD)
- [ ] Reproducibility test passes weekly
- [ ] Disaster recovery test eseguito almeno una volta (vedi sotto)

#### Disaster recovery drill

Una volta nei 90 giorni, simulare:
- DB connection loss
- Broker reconnect failure
- LLM provider down
- Data feed loss

Verificare che il sistema:
- NON esegue ordini in stato degraded
- Alert correttamente
- Recovery automatico quando il problema cessa

#### Commit (multiple, durante i 90 giorni)

Daily commits per fix di issue minori. Weekly summary commit.

---

### T-605 — Decay Monitoring

**Status**: OPEN | **Effort**: M (3-5d) | **Dependencies**: T-604

Job mensile (sotto Celery) che esegue walk-forward su data recente, confronta con baseline, alert su decay.

```python
# alembic/scheduler/decay_tasks.py
from celery import shared_task
from datetime import date
from dateutil.relativedelta import relativedelta

from alembic.backtest.walkforward.runner import WalkForwardRunner, WalkForwardConfig
from alembic.scheduler.strategy_registry import active_strategies
from alembic.storage.strategy_health import StrategyHealthRepository


@shared_task
def monthly_decay_study():
    """Mensile: run WF su last 12 months per ogni strategia, compare con historical baseline."""
    today = date.today()
    health_repo = StrategyHealthRepository()
    
    for strategy in active_strategies():
        # Recent OOS (last 12 months)
        recent_wf = run_walkforward(
            strategy=strategy,
            start=today - relativedelta(months=12),
            end=today,
        )
        
        # Historical baseline (pre last 12 months)
        historical = load_historical_baseline(strategy.strategy_id)
        
        # Decay metrics
        sharpe_decay = recent_wf.sharpe - historical.sharpe
        ic_decay = recent_wf.ic_mean - historical.ic_mean
        
        verdict = classify_decay(sharpe_decay, ic_decay)
        
        health_repo.save_decay_report(
            strategy_id=strategy.strategy_id,
            as_of=today,
            recent_sharpe=recent_wf.sharpe,
            historical_sharpe=historical.sharpe,
            sharpe_decay=sharpe_decay,
            verdict=verdict,
        )
        
        if verdict in ("DECAYING", "DEAD"):
            send_alert(
                level="CRITICAL" if verdict == "DEAD" else "WARNING",
                message=f"{strategy.strategy_id}: decay verdict {verdict}, sharpe decay {sharpe_decay:.2f}",
            )


def classify_decay(sharpe_decay: float, ic_decay: float) -> str:
    if sharpe_decay > -0.2 and ic_decay > -0.01:
        return "HEALTHY"
    if sharpe_decay > -0.5 and ic_decay > -0.03:
        return "WATCHING"
    if sharpe_decay > -1.0:
        return "DECAYING"
    return "DEAD"
```

#### Acceptance

- [ ] Job schedulato e gira mensile
- [ ] Output salvato in `strategy_health` table
- [ ] Alert generati per DECAYING/DEAD verdicts
- [ ] Dashboard mostra trend decay

#### Commit

```
[T-605] Monthly decay monitoring

- Walk-forward on last 12 months per strategy
- Compare to historical baseline
- Verdict: HEALTHY / WATCHING / DECAYING / DEAD
- Auto-alert for DECAYING+
- Dashboard integration

Refs: alembic_v2/05_validation_and_gates.md §4
```

---

### MILESTONE G — 90 Days Paper Trading Passed

### 🛑 HUMAN_GATE [HG-Milestone-G]

```markdown
## 🛑 HUMAN_GATE [HG-Milestone-G]: 90 days paper trading passed

**Done**:
- 90 consecutive days paper trading
- Live performance within tolerance of backtest expected
- No critical unresolved issues
- Disaster recovery drill executed
- All strategy decay verdicts ≥ WATCHING

**Performance summary (90 days live vs expected)**:
- Live Sharpe: X.XX (expected: Y.YY ± 0.3)
- Live DD: X.X% (expected max: Y.Y%)
- Live vol: X.X% (target: 10%)
- N trades: XXX
- Total cost: $X,XXX (X.X bps of NAV)

**Per-strategy live performance**:
| Strategy | Live Sharpe | Expected | Decay verdict |
|---|---|---|---|
| S1 | X.X | 0.6 | HEALTHY |
| S2 | X.X | 1.0 | HEALTHY |
| S3 | X.X | 0.5 | WATCHING |
| S4 | X.X | 0.3 | HEALTHY |

**System health**:
- Uptime: XX.X%
- Critical alerts: X (all resolved)
- Disaster recovery: PASSED

**The system has demonstrated production-readiness in paper.**

**Next decisions (HG-9 next steps)**:
A) Go live with small capital (5-10k recommended)
B) Continue paper trading, gather more data
C) Implement improvements based on 90-day observations
D) Pause and re-evaluate strategy mix

**Recommended**: B for 60 more days, then A with small capital.
Mai più del 5% del wealth totale all'inizio.

**Awaiting**: tua decisione strategica.
```

---

## Post-Milestone-G Roadmap (Phase H opzionale)

Se utente sceglie A (go live):

### T-701 — Live small capital deployment
- Capitale inizial 5-10k
- Stesso codice/setup di paper
- Daily reconciliation con broker
- Aggressive monitoring nei primi 30 giorni

### T-702-T-704 — R&D
- Nuove strategie (commodity trend, carry, ecc.)
- Sempre gates completi prima di entrare in portfolio
- Mai modifiche reattive a strategie esistenti

### T-705 — Tax engine completo
- Lot accounting accurato (FIFO/LIFO)
- Bollo 0.20%/anno
- Capital gains 26%
- Report annual per dichiarazione

Questi sono task per fasi successive, non parte della roadmap attuale.
