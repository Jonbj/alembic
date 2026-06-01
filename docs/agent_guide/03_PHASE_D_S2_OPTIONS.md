# 03 — Phase D: Strategy S2 — Volatility Risk Premium

**Branch**: `phase-D-s2-vrp`
**Effort totale**: ~6 settimane part-time (la più lunga)
**Reference docs**: `/alembic_v2/01_strategy_design.md` §S2

S2 è significativamente diversa dalle altre strategie:
- Trade su opzioni (SPY puts), non equity/ETF
- Richiede IBKR (Alpaca non offre opzioni in IT)
- Cost model opzioni-specifico
- Position management diverso (greche, assignment risk, expiration)
- Sopravvivere a marzo 2020 è il vero gate

**Se non hai familiarità con opzioni**: prima di iniziare T-301, leggi:
- Natenberg, "Option Volatility & Pricing" cap. 1-6 (basics)
- CBOE PUT Index methodology paper (replica esatta della strategia base)
- Israelov & Klein (AQR 2016) "Risk and Return of Equity Index Collar Strategies"

---

## Setup pre-Phase D

```bash
git checkout main
git pull
git checkout -b phase-D-s2-vrp

# Crea struttura
mkdir -p alembic/strategies/s2_vrp
mkdir -p alembic/brokers
mkdir -p alembic/data/options
mkdir -p tests/strategies/s2_vrp
mkdir -p tests/brokers
mkdir -p tests/data/options

touch alembic/strategies/s2_vrp/__init__.py
touch alembic/brokers/__init__.py  # se non esiste già
touch alembic/data/options/__init__.py
```

---

## T-301 — IBKR API Setup

**Status**: OPEN
**Effort**: M (3-5d)
**Dependencies**: nessuna
**Reference docs**: `/alembic_v2/01_strategy_design.md` §S2

### 🛑 PRIMA DI INIZIARE: HUMAN_GATE [HG-1]

L'agente deve avere:
- Un account IBKR (paper account è gratuito, sufficiente per development)
- Credenziali IBKR (username, password)
- TWS (Trader Workstation) o IB Gateway installato e accessibile su `localhost:7497` (paper) o `:7496` (live)

```markdown
## 🛑 HUMAN_GATE [HG-1]: IBKR account required

Per procedere con Phase D ho bisogno di:

1. **Account IBKR paper trading attivo**. Setup gratuito su https://www.interactivebrokers.com → "Open Account" → "Paper Trading".
2. **IB Gateway installato** (più leggero di TWS). Download: https://www.interactivebrokers.com/en/trading/ib-gateway-stable.php
3. **Credenziali** salvate in `.env` (gitignored):
   ```
   IBKR_USER=your_username
   IBKR_PASSWORD=your_password
   IBKR_HOST=127.0.0.1
   IBKR_PAPER_PORT=7497
   IBKR_LIVE_PORT=7496
   ```
4. **IB Gateway running** in paper mode, listening su port 7497

**Test che funzioni**:
```bash
poetry run python -c "
from ib_insync import IB
ib = IB()
ib.connect('127.0.0.1', 7497, clientId=1)
print('Connected. Account:', ib.managedAccounts())
ib.disconnect()
"
```

**Awaiting**: conferma che setup è completo e funzionante.
```

### Prerequisites check (post HG-1)

```bash
# Install ib_insync
poetry add ib-insync

# Verify env vars
poetry run python -c "
import os
required = ['IBKR_USER', 'IBKR_PASSWORD', 'IBKR_HOST', 'IBKR_PAPER_PORT']
missing = [k for k in required if not os.getenv(k)]
if missing:
    print(f'Missing env vars: {missing}')
    exit(1)
print('Env vars OK')
"

# Verify IB Gateway is running
nc -zv 127.0.0.1 7497 2>&1 | head -1
# Expected: "Connection to 127.0.0.1 7497 port [tcp/*] succeeded!"
```

### Files to create

```
alembic/brokers/base.py                 # BrokerAdapter abstract base
alembic/brokers/ibkr_adapter.py         # IBKR implementation
alembic/brokers/types.py                # Order, Position, AccountState types
tests/brokers/test_ibkr_adapter.py
```

### Implementation: BrokerAdapter base

```python
# alembic/brokers/base.py
"""Abstract broker interface."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from alembic.brokers.types import Order, OrderStatus, Position, AccountState


class BrokerAdapter(ABC):
    @abstractmethod
    def connect(self) -> None: ...
    
    @abstractmethod
    def disconnect(self) -> None: ...
    
    @abstractmethod
    def is_connected(self) -> bool: ...
    
    @abstractmethod
    def get_account_state(self) -> AccountState: ...
    
    @abstractmethod
    def get_positions(self) -> list[Position]: ...
    
    @abstractmethod
    def submit_order(self, order: Order) -> str:
        """Returns broker_order_id."""
        ...
    
    @abstractmethod
    def cancel_order(self, broker_order_id: str) -> bool: ...
    
    @abstractmethod
    def get_order_status(self, broker_order_id: str) -> OrderStatus: ...
    
    @abstractmethod
    def __enter__(self): ...
    
    @abstractmethod
    def __exit__(self, *args): ...
```

### Implementation: IBKRAdapter (essenziale)

```python
# alembic/brokers/ibkr_adapter.py
"""IBKR broker adapter using ib_insync."""
from datetime import datetime
import logging
import os

from ib_insync import IB, Stock, Option, MarketOrder, LimitOrder, Contract
from ib_insync import Position as IBPosition

from alembic.brokers.base import BrokerAdapter
from alembic.brokers.types import Order, OrderStatus, Position, AccountState


log = logging.getLogger(__name__)


class IBKRAdapter(BrokerAdapter):
    
    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        client_id: int = 1,
        paper: bool = True,
    ):
        self.host = host or os.getenv("IBKR_HOST", "127.0.0.1")
        port_env = "IBKR_PAPER_PORT" if paper else "IBKR_LIVE_PORT"
        self.port = port or int(os.getenv(port_env, 7497 if paper else 7496))
        self.client_id = client_id
        self.paper = paper
        self._ib: IB | None = None
    
    def connect(self) -> None:
        if self._ib is not None and self._ib.isConnected():
            return
        self._ib = IB()
        self._ib.connect(self.host, self.port, clientId=self.client_id, timeout=15)
        log.info(f"Connected to IBKR ({'paper' if self.paper else 'LIVE'}) at {self.host}:{self.port}")
    
    def disconnect(self) -> None:
        if self._ib is not None:
            self._ib.disconnect()
            self._ib = None
    
    def is_connected(self) -> bool:
        return self._ib is not None and self._ib.isConnected()
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, *args):
        self.disconnect()
    
    def get_account_state(self) -> AccountState:
        self._ensure_connected()
        summary = self._ib.accountSummary()
        values = {item.tag: item.value for item in summary}
        return AccountState(
            account_id=self._ib.managedAccounts()[0],
            cash_usd=float(values.get("TotalCashValue", 0)),
            net_liquidation=float(values.get("NetLiquidation", 0)),
            buying_power=float(values.get("BuyingPower", 0)),
            timestamp=datetime.utcnow(),
        )
    
    def get_positions(self) -> list[Position]:
        self._ensure_connected()
        ib_positions = self._ib.positions()
        result = []
        for p in ib_positions:
            symbol = self._contract_to_symbol(p.contract)
            result.append(Position(
                symbol=symbol,
                quantity=float(p.position),
                avg_cost=float(p.avgCost),
                contract_type=self._contract_type(p.contract),
            ))
        return result
    
    def submit_order(self, order: Order) -> str:
        self._ensure_connected()
        contract = self._build_contract(order)
        ib_order = self._build_ib_order(order)
        trade = self._ib.placeOrder(contract, ib_order)
        return str(trade.order.orderId)
    
    def cancel_order(self, broker_order_id: str) -> bool:
        self._ensure_connected()
        for trade in self._ib.openTrades():
            if str(trade.order.orderId) == broker_order_id:
                self._ib.cancelOrder(trade.order)
                return True
        return False
    
    def get_order_status(self, broker_order_id: str) -> OrderStatus:
        self._ensure_connected()
        for trade in self._ib.trades():
            if str(trade.order.orderId) == broker_order_id:
                return self._map_status(trade.orderStatus.status)
        return OrderStatus.UNKNOWN
    
    # --- helpers ---
    def _ensure_connected(self):
        if not self.is_connected():
            raise ConnectionError("IBKR not connected. Call connect() first.")
    
    def _build_contract(self, order: Order) -> Contract:
        if order.is_option:
            return Option(
                symbol=order.underlying,
                lastTradeDateOrContractMonth=order.expiration.strftime("%Y%m%d"),
                strike=order.strike,
                right=order.right,  # 'P' or 'C'
                exchange="SMART",
                currency="USD",
            )
        return Stock(order.symbol, "SMART", "USD")
    
    def _build_ib_order(self, order: Order):
        action = "BUY" if order.side == "BUY" else "SELL"
        if order.order_type == "MARKET":
            return MarketOrder(action, order.quantity)
        elif order.order_type == "LIMIT":
            return LimitOrder(action, order.quantity, order.limit_price)
        raise ValueError(f"Unsupported order type: {order.order_type}")
    
    def _contract_to_symbol(self, contract: Contract) -> str:
        if contract.secType == "OPT":
            return f"{contract.symbol}_{contract.lastTradeDateOrContractMonth}_{contract.right}_{contract.strike}"
        return contract.symbol
    
    def _contract_type(self, contract: Contract) -> str:
        return contract.secType
    
    def _map_status(self, ib_status: str) -> OrderStatus:
        mapping = {
            "Submitted": OrderStatus.SUBMITTED,
            "Filled": OrderStatus.FILLED,
            "Cancelled": OrderStatus.CANCELLED,
            "PendingSubmit": OrderStatus.PENDING,
            "ApiCancelled": OrderStatus.CANCELLED,
            "Inactive": OrderStatus.CANCELLED,
        }
        return mapping.get(ib_status, OrderStatus.UNKNOWN)
```

### Acceptance verification

```bash
poetry run pytest tests/brokers/test_ibkr_adapter.py -v

# Smoke test live
poetry run python -c "
from alembic.brokers.ibkr_adapter import IBKRAdapter

with IBKRAdapter(paper=True) as broker:
    state = broker.get_account_state()
    print(f'Account: {state.account_id}')
    print(f'NAV: \${state.net_liquidation:,.2f}')
    print(f'Cash: \${state.cash_usd:,.2f}')
    positions = broker.get_positions()
    print(f'Positions: {len(positions)}')
    for p in positions[:5]:
        print(f'  {p.symbol}: {p.quantity} @ {p.avg_cost}')
"
# Expected: connection successful, valid account state
```

### Commit

```
[T-301] IBKR API setup with ib_insync

- BrokerAdapter abstract base class
- IBKRAdapter implementing connect/disconnect, positions, orders
- Support for both stock and option contracts
- Context manager for auto-cleanup
- Smoke test against paper account

Refs: alembic_v2/01_strategy_design.md §S2
```

---

## T-302 — Option Chain Ingestion + Storage

**Status**: OPEN
**Effort**: L (1-2w)
**Dependencies**: T-301
**Reference docs**: `/alembic_v2/02_architecture.md` §7 (storage layout)

### Critical decision

Per backtest S2 servono **5+ anni di SPY option chains EOD**. Le opzioni a:
- **IBKR historical**: disponibili tramite `reqHistoricalData` ma limitate (1 anno daily, sparse strikes)
- **Tradier**: $30/mo, copertura buona
- **Polygon options**: $80/mo, alta qualità
- **CBOE direct**: gratuito EOD ma limitato

**Decision rule** (DR-03): scegli in ordine
1. Se hai già accesso Polygon (per qualsiasi motivo) → usa Polygon
2. Altrimenti → IBKR historical per development, accettando che backtest sia su 1-2 anni invece di 5
3. Se HG-2 raised: paid data source → utente decide

```markdown
## 🛑 HUMAN_GATE [HG-2]: Option chain data source

Per S2 backtest serve 5+ anni di SPY option chain EOD. Opzioni:

A) **Polygon.io options** ($80/mo Starter): copertura completa, alta qualità
B) **Tradier** ($30/mo Pro): copertura buona, sufficient
C) **IBKR historical**: gratis ma limitato (1-2 anni, sparse)
D) **Skip backtest, paper-only**: setup S2 senza backtest storico → risky

**Recommended**: B (Tradier) per balance cost/quality. Sufficient per validation.

**Awaiting**: tua scelta A/B/C/D
```

### Files to create

```
alembic/data/options/types.py            # OptionContract, OptionChain
alembic/data/options/ibkr_provider.py    # IBKR provider
alembic/data/options/tradier_provider.py # Tradier provider (if HG-2 = B)
alembic/data/options/storage.py          # Postgres storage
alembic/data/options/migrations/         # DB migrations
scripts/backfill_option_chains.py
tests/data/options/
```

### DB schema

```python
# alembic/data/options/storage.py
"""Postgres storage per option chains."""

# SQL per migration alembic
"""
CREATE TABLE IF NOT EXISTS option_chains (
    id BIGSERIAL PRIMARY KEY,
    underlying VARCHAR(10) NOT NULL,
    snapshot_date DATE NOT NULL,
    expiration DATE NOT NULL,
    strike NUMERIC(12, 4) NOT NULL,
    right CHAR(1) NOT NULL,  -- 'P' or 'C'
    
    bid NUMERIC(10, 4),
    ask NUMERIC(10, 4),
    mid NUMERIC(10, 4),
    last NUMERIC(10, 4),
    volume INTEGER,
    open_interest INTEGER,
    
    implied_vol NUMERIC(8, 6),
    delta NUMERIC(8, 6),
    gamma NUMERIC(10, 8),
    theta NUMERIC(8, 6),
    vega NUMERIC(8, 6),
    
    underlying_price NUMERIC(10, 4),
    
    source VARCHAR(20) NOT NULL,
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE (underlying, snapshot_date, expiration, strike, right)
);

CREATE INDEX idx_option_chains_lookup 
ON option_chains (underlying, snapshot_date, expiration);

CREATE INDEX idx_option_chains_dte 
ON option_chains (underlying, snapshot_date, (expiration - snapshot_date));
"""
```

### Acceptance verification

```bash
# Migration applicata
poetry run alembic upgrade head

# Backfill (long-running, ~1h per 5 years)
poetry run python scripts/backfill_option_chains.py \
  --underlying SPY \
  --start 2019-01-01 \
  --end 2024-12-31 \
  --provider tradier  # o ibkr

# Verify data
poetry run python -c "
from datetime import date
from alembic.data.options.storage import OptionChainRepository

repo = OptionChainRepository()
chain = repo.get_chain('SPY', date(2024, 3, 15))
print(f'Chain at 2024-03-15: {len(chain)} contracts')
print(f'Expirations: {sorted(set(c.expiration for c in chain))[:5]}')
# Sanity: SPY had options with weekly expirations
assert len(chain) > 500
"

# Query performance
poetry run python -c "
import time
from datetime import date
from alembic.data.options.storage import OptionChainRepository
repo = OptionChainRepository()
t0 = time.time()
chain = repo.get_chain('SPY', date(2024, 3, 15))
print(f'Query time: {(time.time()-t0)*1000:.0f}ms')
assert time.time()-t0 < 1.0
"
```

### Commit

```
[T-302] Option chain ingestion + Postgres storage

- OptionContract / OptionChain types
- Multi-provider support (IBKR, Tradier)
- Postgres schema with indices for fast lookup
- Backfill script for 5+ years SPY EOD chains
- Query performance < 1s per chain

Refs: alembic_v2/02_architecture.md §7
```

---

## T-303 — Black-Scholes + Greeks

**Status**: OPEN
**Effort**: S (1-2d)
**Dependencies**: nessuna

### Implementation

```python
# alembic/strategies/s2_vrp/pricing.py
"""Black-Scholes pricing + greeks. Used per validation e fallback.

Note: per opzioni americane (es. SPY), BS è approssimazione.
Per put SPY OTM, l'errore vs binomial è tipicamente < 0.5%.
"""
from dataclasses import dataclass
from math import log, sqrt, exp
import numpy as np
from scipy.stats import norm


@dataclass(frozen=True)
class GreeksAndPrice:
    price: float
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float


def black_scholes(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: str = "P",
    q: float = 0.0,
) -> GreeksAndPrice:
    """Black-Scholes-Merton with continuous dividend yield.
    
    Args:
        S: spot price
        K: strike
        T: time to expiry (years)
        r: risk-free rate (decimal)
        sigma: implied vol (decimal)
        option_type: 'P' (put) or 'C' (call)
        q: dividend yield (decimal)
    
    Returns:
        GreeksAndPrice
    """
    if T <= 0 or sigma <= 0:
        # Expired or zero-vol edge case
        intrinsic = max(K - S, 0) if option_type == "P" else max(S - K, 0)
        return GreeksAndPrice(intrinsic, 0, 0, 0, 0, 0)
    
    d1 = (log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    
    if option_type == "C":
        price = S * exp(-q * T) * norm.cdf(d1) - K * exp(-r * T) * norm.cdf(d2)
        delta = exp(-q * T) * norm.cdf(d1)
        rho = K * T * exp(-r * T) * norm.cdf(d2) / 100
    else:  # P
        price = K * exp(-r * T) * norm.cdf(-d2) - S * exp(-q * T) * norm.cdf(-d1)
        delta = -exp(-q * T) * norm.cdf(-d1)
        rho = -K * T * exp(-r * T) * norm.cdf(-d2) / 100
    
    gamma = exp(-q * T) * norm.pdf(d1) / (S * sigma * sqrt(T))
    vega = S * exp(-q * T) * norm.pdf(d1) * sqrt(T) / 100  # per 1% IV change
    
    theta_call = (
        -S * exp(-q * T) * norm.pdf(d1) * sigma / (2 * sqrt(T))
        + q * S * exp(-q * T) * norm.cdf(d1)
        - r * K * exp(-r * T) * norm.cdf(d2)
    )
    theta_put = (
        -S * exp(-q * T) * norm.pdf(d1) * sigma / (2 * sqrt(T))
        - q * S * exp(-q * T) * norm.cdf(-d1)
        + r * K * exp(-r * T) * norm.cdf(-d2)
    )
    theta = (theta_call if option_type == "C" else theta_put) / 365  # per-day
    
    return GreeksAndPrice(price, delta, gamma, theta, vega, rho)


def implied_vol(
    market_price: float,
    S: float,
    K: float,
    T: float,
    r: float,
    option_type: str = "P",
    q: float = 0.0,
    tol: float = 1e-4,
    max_iter: int = 100,
) -> float | None:
    """Solve for IV using Newton-Raphson. Returns None if no convergence."""
    if market_price <= 0 or T <= 0:
        return None
    
    sigma = 0.30  # initial guess
    for _ in range(max_iter):
        result = black_scholes(S, K, T, r, sigma, option_type, q)
        diff = result.price - market_price
        if abs(diff) < tol:
            return sigma
        vega = result.vega * 100  # un-scale (vega is per 1% IV)
        if vega < 1e-10:
            return None
        sigma -= diff / vega
        if sigma <= 0:
            sigma = 0.01
        if sigma > 5:
            return None  # not converging
    return None
```

### Tests

```python
# tests/strategies/s2_vrp/test_pricing.py
import pytest
from alembic.strategies.s2_vrp.pricing import black_scholes, implied_vol


class TestBlackScholes:
    def test_atm_put_price_known(self):
        """Test contro valore noto: SPY ATM put 30dte 20% IV."""
        result = black_scholes(S=400, K=400, T=30/365, r=0.05, sigma=0.20, option_type="P")
        # Approximate expected from textbook
        assert 8.0 < result.price < 10.0
    
    def test_atm_put_delta_near_neg_half(self):
        result = black_scholes(S=400, K=400, T=30/365, r=0.05, sigma=0.20, option_type="P")
        assert -0.55 < result.delta < -0.45
    
    def test_otm_put_delta(self):
        """Put 20-delta dovrebbe essere ~5% OTM (depends on vol, T)."""
        # For SPY at 400, ~20% vol, 30dte, 20-delta put è ~strike 388
        result = black_scholes(S=400, K=388, T=30/365, r=0.05, sigma=0.20, option_type="P")
        assert -0.30 < result.delta < -0.15
    
    def test_theta_negative_for_long_options(self):
        result = black_scholes(S=400, K=400, T=30/365, r=0.05, sigma=0.20, option_type="P")
        assert result.theta < 0
    
    def test_expired_option_intrinsic_only(self):
        result = black_scholes(S=380, K=400, T=0, r=0.05, sigma=0.20, option_type="P")
        assert result.price == 20  # intrinsic
        assert result.delta == 0


class TestImpliedVol:
    def test_iv_recovers_input(self):
        """Compute price, then solve IV → should recover."""
        original_iv = 0.25
        S, K, T, r = 400, 380, 45/365, 0.05
        result = black_scholes(S, K, T, r, original_iv, "P")
        recovered = implied_vol(result.price, S, K, T, r, "P")
        assert abs(recovered - original_iv) < 0.001
```

### Acceptance

```bash
poetry run pytest tests/strategies/s2_vrp/test_pricing.py -v
# Expected: tutti pass

# Validate vs Bloomberg/online calculator
poetry run python -c "
from alembic.strategies.s2_vrp.pricing import black_scholes
# SPY at 480, put 460, 30dte, IV 18%, r 5%
r = black_scholes(480, 460, 30/365, 0.05, 0.18, 'P')
print(f'Price: {r.price:.2f}, Delta: {r.delta:.3f}, Vega: {r.vega:.3f}')
# Sanity: ~3-4 USD, delta -0.20 range
assert 2.0 < r.price < 5.0
assert -0.30 < r.delta < -0.10
"
```

### Commit

```
[T-303] Black-Scholes pricing + greeks + IV solver

- BS-M with dividend yield
- All five greeks (delta, gamma, theta, vega, rho)
- Newton-Raphson IV solver
- Tested against textbook values
- Edge cases: expired, zero-vol, deep ITM/OTM

Refs: alembic_v2/01_strategy_design.md §S2
```

---

## T-304 — S2 Signal: Put Selection

**Status**: OPEN
**Effort**: M (3-5d)
**Dependencies**: T-302, T-303

### Logic

```python
# alembic/strategies/s2_vrp/signal.py
"""S2 signal: select put to sell."""
from dataclasses import dataclass
from datetime import date, timedelta
import pandas as pd

from alembic.data.options.types import OptionContract, OptionChain


@dataclass(frozen=True)
class S2SignalParams:
    target_delta: float = -0.20
    delta_tolerance: float = 0.05
    target_dte_min: int = 30
    target_dte_max: int = 45
    min_volume: int = 100
    min_open_interest: int = 500
    min_bid: float = 0.20  # avoid penny options
    

@dataclass(frozen=True)
class PutSelectionResult:
    contract: OptionContract
    expected_premium_per_contract: float
    delta: float
    iv: float
    days_to_expiry: int
    collateral_required_per_contract: float  # 100 * strike
    rationale: dict


def select_put_to_sell(
    chain: OptionChain,
    underlying_price: float,
    as_of: date,
    params: S2SignalParams,
) -> PutSelectionResult | None:
    """Find best put to sell given target delta + DTE.
    
    Strategy:
    1. Filter to puts only
    2. Filter to DTE in [target_dte_min, target_dte_max]
    3. Filter to liquidity (volume, OI, bid)
    4. Among remaining, pick the one with delta closest to target_delta
    
    Returns None if no suitable contract found.
    """
    puts = [c for c in chain.contracts if c.right == "P"]
    
    # DTE filter
    puts = [
        c for c in puts
        if params.target_dte_min <= (c.expiration - as_of).days <= params.target_dte_max
    ]
    
    # Liquidity filter
    puts = [
        c for c in puts
        if c.volume >= params.min_volume
        and c.open_interest >= params.min_open_interest
        and c.bid >= params.min_bid
    ]
    
    # Delta filter
    candidates = [
        c for c in puts
        if abs(c.delta - params.target_delta) <= params.delta_tolerance
    ]
    
    if not candidates:
        return None
    
    # Pick closest to target delta
    best = min(candidates, key=lambda c: abs(c.delta - params.target_delta))
    
    dte = (best.expiration - as_of).days
    mid_premium = (best.bid + best.ask) / 2
    
    return PutSelectionResult(
        contract=best,
        expected_premium_per_contract=mid_premium * 100,  # contract = 100 shares
        delta=best.delta,
        iv=best.implied_vol,
        days_to_expiry=dte,
        collateral_required_per_contract=best.strike * 100,
        rationale={
            "n_candidates": len(candidates),
            "n_total_puts": len(puts),
            "delta_target": params.target_delta,
            "delta_actual": best.delta,
            "premium_yield_annualized": (mid_premium / best.strike) * (365 / dte),
        },
    )


def compute_position_size(
    selected: PutSelectionResult,
    available_capital: float,
    max_capital_allocation_pct: float,
    vrp_multiplier: float = 1.0,
) -> int:
    """How many contracts to sell, given available capital and VRP richness.
    
    Returns n_contracts (positive = short put).
    """
    max_collateral = available_capital * max_capital_allocation_pct * vrp_multiplier
    n_contracts = int(max_collateral / selected.collateral_required_per_contract)
    return max(n_contracts, 0)
```

### Acceptance verification

```bash
poetry run pytest tests/strategies/s2_vrp/test_signal.py -v

# Smoke su data storica
poetry run python -c "
from datetime import date
from alembic.data.options.storage import OptionChainRepository
from alembic.strategies.s2_vrp.signal import select_put_to_sell, S2SignalParams

repo = OptionChainRepository()
chain = repo.get_chain('SPY', date(2024, 3, 15))
# Need underlying price at that date
spy_price = ...  # from data loader

result = select_put_to_sell(chain, spy_price, date(2024, 3, 15), S2SignalParams())
if result:
    print(f'Selected: strike={result.contract.strike}, exp={result.contract.expiration}, delta={result.delta}')
    print(f'Premium: \${result.expected_premium_per_contract:.2f}')
    print(f'Collateral: \${result.collateral_required_per_contract:.2f}')
assert result is not None
"
```

### Commit

```
[T-304] S2 signal: put selection logic

- Filter chain by DTE 30-45, delta ~-0.20, liquidity
- Position sizing based on collateral requirement
- VRP-aware sizing multiplier
- Rationale logging for backtest analysis

Refs: alembic_v2/01_strategy_design.md §S2
```

---

## T-305 — S2 Exit Logic

**Status**: OPEN
**Effort**: M (3-5d)
**Dependencies**: T-304

### Logic

Exit triggers:
1. **Profit target**: chiudi se hai catturato 50% del premio
2. **Stop loss**: chiudi se loss > 2× premio ricevuto
3. **Time decay**: chiudi se < 7 DTE rimanenti (assignment risk)
4. **Signal flip**: chiudi se nuovo signal direzionale negativo su SPY
5. **Assignment risk**: chiudi se delta scende sotto -0.50 (deep ITM)

```python
# alembic/strategies/s2_vrp/exit_logic.py
from dataclasses import dataclass
from datetime import date
from enum import Enum


class ExitReason(str, Enum):
    PROFIT_TARGET = "PROFIT_TARGET"
    STOP_LOSS = "STOP_LOSS"
    TIME_DECAY = "TIME_DECAY"
    SIGNAL_FLIP = "SIGNAL_FLIP"
    ASSIGNMENT_RISK = "ASSIGNMENT_RISK"
    EXPIRATION = "EXPIRATION"


@dataclass(frozen=True)
class ExitDecision:
    should_exit: bool
    reason: ExitReason | None
    urgency: str  # 'IMMEDIATE', 'EOD', 'NEXT_OPEN'


@dataclass(frozen=True)
class ExitParams:
    profit_target_pct: float = 0.5
    stop_loss_multiplier: float = 2.0
    min_dte: int = 7
    assignment_risk_delta: float = -0.50


def evaluate_exit(
    position_entry_premium: float,
    current_option_mid: float,
    current_delta: float,
    days_to_expiry: int,
    underlying_signal: float | None,
    params: ExitParams,
) -> ExitDecision:
    """Evaluate if a short put position should be closed.
    
    Args:
        position_entry_premium: premio incassato all'apertura (sempre positivo)
        current_option_mid: prezzo corrente del put (positivo)
        current_delta: delta corrente (negativo per put)
        days_to_expiry: giorni rimanenti
        underlying_signal: signal direzionale SPY (None se non disponibile)
        params: ExitParams
    """
    # Expired
    if days_to_expiry <= 0:
        return ExitDecision(True, ExitReason.EXPIRATION, "IMMEDIATE")
    
    # P&L corrente (short put: profitto se prezzo opzione scende)
    pnl = position_entry_premium - current_option_mid
    
    # Profit target
    if pnl >= params.profit_target_pct * position_entry_premium:
        return ExitDecision(True, ExitReason.PROFIT_TARGET, "EOD")
    
    # Stop loss
    if pnl <= -params.stop_loss_multiplier * position_entry_premium:
        return ExitDecision(True, ExitReason.STOP_LOSS, "IMMEDIATE")
    
    # Time decay
    if days_to_expiry <= params.min_dte:
        return ExitDecision(True, ExitReason.TIME_DECAY, "EOD")
    
    # Assignment risk (deep ITM)
    if current_delta <= params.assignment_risk_delta:
        return ExitDecision(True, ExitReason.ASSIGNMENT_RISK, "IMMEDIATE")
    
    # Signal flip
    if underlying_signal is not None and underlying_signal < -0.5:
        return ExitDecision(True, ExitReason.SIGNAL_FLIP, "EOD")
    
    return ExitDecision(False, None, "NEXT_OPEN")
```

### Acceptance

```bash
poetry run pytest tests/strategies/s2_vrp/test_exit_logic.py -v

# Tutti i test scenarios devono passare:
# - profit target hit @ 50% di premium catturato
# - stop loss hit @ -2× premium
# - time decay @ 7 DTE
# - assignment risk @ delta -0.55
# - signal flip @ underlying signal -0.6
```

### Commit

```
[T-305] S2 exit logic

- Profit target 50% premium captured
- Stop loss 2x premium received
- Time decay exit at 7 DTE
- Assignment risk monitor (delta < -0.50)
- Signal-flip exit hook (for T-307 integration)

Refs: alembic_v2/01_strategy_design.md §S2
```

---

## T-306 — S2 Regime Modulation Overlay

**Status**: OPEN
**Effort**: S (1-2d)
**Dependencies**: T-304, regime_classifier esistente

### Logic

Modula aggressività in base al regime macro classificato dal sistema esistente.

```python
# alembic/strategies/s2_vrp/regime_overlay.py
from dataclasses import dataclass
from enum import Enum

# Import dal regime classifier esistente
from alembic.regime.classifier import RegimeState  # path da verificare


@dataclass(frozen=True)
class RegimeModulation:
    size_multiplier: float  # 0.0 = no new positions, 1.0 = normal
    delta_target_adjustment: float  # add to base delta target
    block_new_positions: bool


def get_regime_modulation(regime: RegimeState) -> RegimeModulation:
    """Map regime to S2 behavior.
    
    Rationale:
    - RISK_ON: VRP harvest is best in calm bull markets → full size
    - GOLDILOCKS: similar → full size
    - RISK_OFF: VRP can spike but tail risk higher → half size, more OTM
    - STRESS: dangerous → block new, manage existing
    """
    if regime == RegimeState.RISK_ON or regime == RegimeState.GOLDILOCKS:
        return RegimeModulation(
            size_multiplier=1.0,
            delta_target_adjustment=0.0,
            block_new_positions=False,
        )
    elif regime == RegimeState.RISK_OFF:
        return RegimeModulation(
            size_multiplier=0.5,
            delta_target_adjustment=0.05,  # more OTM (delta from -0.20 → -0.15)
            block_new_positions=False,
        )
    elif regime == RegimeState.STRESS:
        return RegimeModulation(
            size_multiplier=0.0,
            delta_target_adjustment=0.0,
            block_new_positions=True,
        )
    # Default: conservative
    return RegimeModulation(0.5, 0.0, False)
```

### Acceptance

```bash
poetry run pytest tests/strategies/s2_vrp/test_regime_overlay.py -v
```

### Commit

```
[T-306] S2 regime modulation overlay

- Maps regime → size multiplier + delta adjustment + block flag
- RISK_ON/GOLDILOCKS: full aggression
- RISK_OFF: half size, more OTM
- STRESS: no new positions

Refs: alembic_v2/01_strategy_design.md §S2.Refinement
```

---

## T-307 — S2 Event Filter (LLM + News)

**Status**: OPEN
**Effort**: M (3-5d)
**Dependencies**: T-304, LLM ensemble esistente

### Logic

Blocca nuove posizioni quando:
- Sentiment LLM aggregato su SPY < -0.5
- Major events imminenti (FOMC, NFP, ECB) entro 7 giorni
- VIX term structure invertita (VIX9D > VIX3M)

```python
# alembic/strategies/s2_vrp/event_filter.py
from dataclasses import dataclass
from datetime import date, timedelta

# Riusa news + LLM ensemble esistenti
from alembic.signals.aggregator import AggregatedSignalRepository
from alembic.calendar.events import MajorEventsCalendar  # da creare/wrappare


@dataclass(frozen=True)
class EventFilterDecision:
    block: bool
    reasons: list[str]


def evaluate_event_filter(
    as_of: date,
    spy_sentiment: float | None,
    vix_9d: float | None,
    vix_3m: float | None,
    days_to_major_event: int | None,
    sentiment_threshold: float = -0.5,
    event_lookahead_days: int = 7,
) -> EventFilterDecision:
    reasons = []
    
    if spy_sentiment is not None and spy_sentiment < sentiment_threshold:
        reasons.append(f"SPY sentiment {spy_sentiment:.2f} < {sentiment_threshold}")
    
    if days_to_major_event is not None and days_to_major_event <= event_lookahead_days:
        reasons.append(f"Major event in {days_to_major_event} days")
    
    if vix_9d and vix_3m and vix_9d > vix_3m:
        reasons.append(f"VIX term structure inverted: VIX9D {vix_9d:.1f} > VIX3M {vix_3m:.1f}")
    
    return EventFilterDecision(block=len(reasons) > 0, reasons=reasons)
```

### Commit

```
[T-307] S2 event filter

- LLM sentiment threshold on SPY
- Major events calendar lookback (FOMC, NFP, ECB)
- VIX term structure inversion detector
- Composable: returns reasons for blocking

Refs: alembic_v2/01_strategy_design.md §S2.Refinement
```

---

## T-308 — S2 Backtest + Gates Run

**Status**: OPEN
**Effort**: L (1-2w)
**Dependencies**: T-302..T-307
**Reference docs**: `/alembic_v2/01_strategy_design.md` §S2, `/alembic_v2/05_validation_and_gates.md`

### Backtest engine extensions

S2 richiede un backtest engine **option-aware**:
- Option position tracking
- Option cost model (5% bid-ask del mid)
- Daily mark-to-market via greeks o option chain replay
- Assignment simulation

Crea `alembic/backtest/engine/option_portfolio.py` come estensione di VirtualPortfolio:

```python
"""Option-aware virtual portfolio.

Extends VirtualPortfolio to handle short put positions, daily mtm via chain replay,
expiration handling, and assignment simulation.
"""
from datetime import date, datetime
from dataclasses import dataclass

from alembic.backtest.engine.portfolio import VirtualPortfolio
from alembic.data.options.storage import OptionChainRepository


@dataclass(frozen=True)
class OptionPosition:
    contract_id: str  # underlying_expiration_right_strike
    underlying: str
    expiration: date
    strike: float
    right: str
    quantity: int  # negative = short
    open_price: float
    open_date: date


class OptionAwarePortfolio(VirtualPortfolio):
    def __init__(self, initial_cash: float, chain_repo: OptionChainRepository):
        super().__init__(initial_cash)
        self._option_positions: dict[str, OptionPosition] = {}
        self._chain_repo = chain_repo
    
    def open_short_put(
        self,
        underlying: str,
        expiration: date,
        strike: float,
        quantity: int,
        premium_per_contract: float,
        as_of: date,
    ):
        """Open short put position. Receives premium, locks up collateral."""
        contract_id = f"{underlying}_{expiration.isoformat()}_P_{strike}"
        # Cash in: receive premium * 100 per contract * quantity
        self._cash += premium_per_contract * 100 * quantity
        # Collateral locked: strike * 100 * quantity (not subtracted from cash, just tracked)
        self._option_positions[contract_id] = OptionPosition(
            contract_id=contract_id,
            underlying=underlying,
            expiration=expiration,
            strike=strike,
            right="P",
            quantity=-quantity,  # short = negative
            open_price=premium_per_contract,
            open_date=as_of,
        )
    
    def close_short_put(self, contract_id: str, close_price: float):
        """Close (buy back) short put position."""
        pos = self._option_positions.pop(contract_id)
        # Cash out: pay close_price * 100 * |qty|
        self._cash -= close_price * 100 * abs(pos.quantity)
    
    def handle_expirations(self, as_of: date, chain_repo: OptionChainRepository):
        """Process expirations + assignments."""
        for contract_id in list(self._option_positions.keys()):
            pos = self._option_positions[contract_id]
            if pos.expiration <= as_of:
                # Get underlying close at expiration
                underlying_price = ...  # from price data
                if underlying_price < pos.strike and pos.right == "P":
                    # Assignment: must buy underlying at strike
                    cost = pos.strike * 100 * abs(pos.quantity)
                    self._cash -= cost
                    # Now own underlying
                    self.apply_fill(...)  # synthetic buy fill
                # Remove option position
                del self._option_positions[contract_id]
```

### Backtest run

```bash
# Backtest S2 standalone (no overlay)
poetry run python -m alembic.backtest.gates.runner \
  --strategy s2_vrp \
  --start 2019-01-01 \
  --end 2024-12-31 \
  --output reports/s2/gates_baseline.html

# Backtest S2 con overlay completi (regime + event filter)
poetry run python -m alembic.backtest.gates.runner \
  --strategy s2_vrp \
  --start 2019-01-01 \
  --end 2024-12-31 \
  --overlays regime,event_filter \
  --output reports/s2/gates_full.html
```

### Acceptance criteria

**Tutti i gates devono passare** con criteri S2-specifici:

- Gate 1: DSR > 0.5 (è la metrica corretta per trading-based)
- Gate 2: OOS/IS Sharpe > 0.5
- Gate 3: Robustness, Sharpe median > 0.5 across param variants
- Gate 4: Eccezione documentata — accettato 2 regimi positivi + 1 neutro + 1 negativo (STRESS)
- Gate 5: **CRITICO** — DD in marzo 2020 < 25% con overlay attivi

**Numeri attesi**:
- Sharpe OOS netto costi: 0.8-1.1
- Annual return: 7-10%
- Max DD: 15-25%
- Skewness: fortemente negativa (atteso, è il "rischio assicurativo")

### On gate failure (S2-specific)

Se Gate 5 fail su marzo 2020:
1. **Check regime overlay**: con STRESS attivo, no new positions dopo 24 feb 2020. Verifica.
2. **Check event filter**: VIX term structure si è invertita 21 feb 2020. Verifica.
3. **Check stop-loss**: stop a -2× premium chiudeva posizioni in apertura del 9-13 marzo. Verifica timing fills.
4. **Cost model**: opzioni illiquide marzo 2020 → spread 20-30% del mid. Riprova con cost model più aggressivo.

Se ancora fail dopo questi fix → HG-5: la strategia non sopravvive a stress, **non procedere**.

### Commit

```
[T-308] S2 backtest + validation gates

- Option-aware portfolio extending VirtualPortfolio
- Full backtest 2019-2024 with overlays
- All 5 gates passed (Gate 4 with documented S2 exception):
  - Gate 1: DSR X.XX
  - Gate 5: March 2020 DD XX% (< 25%)
- Reports: reports/s2/gates_baseline.html, gates_full.html

Refs: alembic_v2/01_strategy_design.md §S2
```

---

## MILESTONE D — S2 validated

### 🛑 HUMAN_GATE [HG-Milestone-D]

```markdown
## 🛑 HUMAN_GATE [HG-Milestone-D]: S2 VRP validated

**Done**:
- IBKR adapter + option chain ingestion working
- Black-Scholes + greeks validated
- S2 signal + exit logic + regime overlay + event filter
- Backtest 2019-2024 completed, all gates passed
- March 2020 stress survived: DD XX% (< 25% threshold)

**Critical results**:
- OOS Sharpe: X.XX
- March 2020 DD: -XX%
- 2008 sim DD (no real option data, BS model): -XX%

**Risk acknowledgment**:
S2 ha skewness fortemente negativa per design. Aspettare tail events
in live anche se backtest era pulito. Allocazione MAX 30% del portfolio.

**Files for review**:
- `alembic/strategies/s2_vrp/`
- `reports/s2/gates_full.html`
- `alembic/brokers/ibkr_adapter.py`

**Awaiting**: tua approvazione + decisione su Polygon vs Tradier per long-term data
```
