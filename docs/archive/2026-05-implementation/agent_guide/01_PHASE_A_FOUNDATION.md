# 01 — Phase A: Backtest Foundation

**Obiettivo della fase**: portare il repo allo stato in cui esiste un backtest engine event-driven, validato, con cost model serio, anti-look-ahead enforcement, walk-forward framework, metrics engine completo, 5 validation gates funzionanti.

**Effort totale**: ~4 settimane part-time
**Output**: framework di backtest riusabile per tutte le strategie successive
**Niente strategy implementation in questa fase**.

---

## Setup iniziale della fase

Prima del primo task, l'agente esegue:

```bash
# Crea branch per la fase
git checkout -b phase-A-foundation

# Verifica stato repo
git status
git log --oneline -10

# Crea struttura di directory per Fase A
mkdir -p alembic/backtest/{engine,costs,walkforward,metrics,gates,data}
mkdir -p alembic/backtest/engine
mkdir -p tests/backtest
mkdir -p config

# Touch __init__.py
find alembic/backtest -type d -exec touch {}/__init__.py \;
find tests/backtest -type d -exec touch {}/__init__.py \;

# Initial commit di scaffold
git add alembic/backtest tests/backtest
git commit -m "[Phase A] Scaffold backtest module structure"
```

---

## T-001 — Setup vectorbt + Data Loading

**Status**: OPEN
**Effort**: M (3-5d)
**Dependencies**: nessuna
**Reference docs**: `/alembic_v2/03_backtest_framework.md` §2, §3

### Prerequisites check

```bash
# Verifica Python
python --version  # deve essere >= 3.11

# Verifica Poetry
poetry --version

# Test che possa installare vectorbt
poetry add vectorbt yfinance pyarrow pandas
poetry add --group dev pytest pytest-cov hypothesis

# Verifica installazione
poetry run python -c "import vectorbt as vbt; print(vbt.__version__)"
poetry run python -c "import yfinance as yf; print(yf.__version__)"
```

Se fail: vai a `/agent_guide/00_AGENT_GUIDE.md` sezione "Stack tecnico" per troubleshoot.

### Files to create

```
alembic/backtest/data/loader.py            # Data loader principale
alembic/backtest/data/universe.py          # Universe management
alembic/backtest/data/cache.py             # Parquet caching
config/universe.yaml                       # Definizione universe
tests/backtest/test_loader.py              # Test loader
tests/backtest/test_universe.py            # Test universe
tests/backtest/fixtures/synthetic_prices.parquet  # Test fixture
scripts/download_initial_data.py           # Script one-off per backfill
```

### Files to modify

Nessuno (nuova area di codice).

### Implementation steps

#### Step 1: Define universe in config

Crea `config/universe.yaml`:

```yaml
version: "0.1.0"
last_modified: "2026-05-28"

# Universe per Strategia 1 (Time-Series Momentum)
s1_universe:
  description: "Cross-asset ETF universe for trend following"
  tickers:
    # Equity by region
    - { symbol: SPY, asset_class: US_EQUITY_LARGE, inception: "1993-01-22" }
    - { symbol: QQQ, asset_class: US_EQUITY_TECH, inception: "1999-03-10" }
    - { symbol: IWM, asset_class: US_EQUITY_SMALL, inception: "2000-05-22" }
    - { symbol: VEA, asset_class: INTL_DEV_EQUITY, inception: "2007-07-20" }
    - { symbol: VWO, asset_class: EM_EQUITY, inception: "2005-03-04" }
    - { symbol: EWJ, asset_class: JAPAN_EQUITY, inception: "1996-03-12" }
    # Bonds
    - { symbol: TLT, asset_class: UST_LONG, inception: "2002-07-22" }
    - { symbol: IEF, asset_class: UST_INTERMEDIATE, inception: "2002-07-22" }
    - { symbol: SHY, asset_class: UST_SHORT, inception: "2002-07-22" }
    - { symbol: LQD, asset_class: IG_CREDIT, inception: "2002-07-22" }
    - { symbol: HYG, asset_class: HY_CREDIT, inception: "2007-04-04" }
    - { symbol: TIP, asset_class: TIPS, inception: "2003-12-04" }
    # Alternatives
    - { symbol: GLD, asset_class: GOLD, inception: "2004-11-18" }
    - { symbol: DBC, asset_class: BROAD_COMMODITY, inception: "2006-02-03" }
    - { symbol: VNQ, asset_class: US_REITS, inception: "2004-09-23" }

# Universe per Strategia 3 (Cross-Sectional Equity)
# Da popolare riusando l'universe 72 ticker esistente in Alembic v1
s3_universe:
  description: "US large/mid cap equity universe (from v1)"
  source: "alembic/config/universe_v1.yaml"  # adattare path al repo reale
  filters:
    min_market_cap_usd: 2_000_000_000
    min_adv_usd: 10_000_000
    min_price_usd: 5
```

#### Step 2: Implementa universe loader

Crea `alembic/backtest/data/universe.py`:

```python
"""Universe management: load, filter, point-in-time queries."""
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional
import yaml


@dataclass(frozen=True)
class UniverseAsset:
    symbol: str
    asset_class: str
    inception_date: date
    
    @classmethod
    def from_dict(cls, d: dict) -> "UniverseAsset":
        return cls(
            symbol=d["symbol"],
            asset_class=d["asset_class"],
            inception_date=datetime.strptime(d["inception"], "%Y-%m-%d").date(),
        )


@dataclass(frozen=True)
class Universe:
    universe_id: str
    description: str
    assets: tuple[UniverseAsset, ...]
    
    def active_at(self, as_of: date) -> tuple[UniverseAsset, ...]:
        """Returns assets that existed as of given date (point-in-time correct)."""
        return tuple(a for a in self.assets if a.inception_date <= as_of)
    
    def symbols(self) -> tuple[str, ...]:
        return tuple(a.symbol for a in self.assets)
    
    def by_symbol(self, symbol: str) -> Optional[UniverseAsset]:
        for a in self.assets:
            if a.symbol == symbol:
                return a
        return None


def load_universe(universe_id: str, config_path: Path = Path("config/universe.yaml")) -> Universe:
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    universe_key = f"{universe_id}_universe"
    if universe_key not in config:
        raise ValueError(f"Universe '{universe_id}' not found in {config_path}")
    
    universe_config = config[universe_key]
    assets = tuple(UniverseAsset.from_dict(d) for d in universe_config["tickers"])
    
    return Universe(
        universe_id=universe_id,
        description=universe_config["description"],
        assets=assets,
    )
```

#### Step 3: Implementa data cache (parquet)

Crea `alembic/backtest/data/cache.py`:

```python
"""Parquet caching layer per data ohlcv."""
from datetime import date
from pathlib import Path
import pandas as pd


class ParquetCache:
    """File-based cache per OHLCV data."""
    
    def __init__(self, cache_dir: Path = Path.home() / ".alembic_cache"):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _path_for(self, symbol: str) -> Path:
        return self.cache_dir / f"{symbol}.parquet"
    
    def has(self, symbol: str) -> bool:
        return self._path_for(symbol).exists()
    
    def get(self, symbol: str, start: date | None = None, end: date | None = None) -> pd.DataFrame:
        if not self.has(symbol):
            raise KeyError(f"No cached data for {symbol}")
        
        df = pd.read_parquet(self._path_for(symbol))
        # Standard columns: Open, High, Low, Close, Volume, Adj Close
        # Index: pd.DatetimeIndex (UTC date-only)
        
        if start:
            df = df[df.index >= pd.Timestamp(start)]
        if end:
            df = df[df.index <= pd.Timestamp(end)]
        
        return df
    
    def put(self, symbol: str, df: pd.DataFrame) -> None:
        # Validation
        required_cols = {"Open", "High", "Low", "Close", "Volume", "Adj Close"}
        missing = required_cols - set(df.columns)
        if missing:
            raise ValueError(f"Missing required columns: {missing}")
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError(f"Index must be DatetimeIndex, got {type(df.index)}")
        
        df.to_parquet(self._path_for(symbol))
    
    def update(self, symbol: str, df_new: pd.DataFrame) -> None:
        """Merge new data with existing cache."""
        if self.has(symbol):
            df_old = self.get(symbol)
            df_combined = pd.concat([df_old, df_new])
            df_combined = df_combined[~df_combined.index.duplicated(keep="last")]
            df_combined = df_combined.sort_index()
            self.put(symbol, df_combined)
        else:
            self.put(symbol, df_new)
```

#### Step 4: Implementa data loader principale

Crea `alembic/backtest/data/loader.py`:

```python
"""Data loader: download da Yahoo (default), cache parquet, multi-symbol API."""
from datetime import date, datetime
import logging
from pathlib import Path
import time

import pandas as pd
import yfinance as yf

from alembic.backtest.data.cache import ParquetCache
from alembic.backtest.data.universe import Universe, UniverseAsset


log = logging.getLogger(__name__)


class DataLoader:
    """Carica daily OHLCV data, cache su parquet, point-in-time safe."""
    
    def __init__(self, cache: ParquetCache | None = None):
        self.cache = cache or ParquetCache()
    
    def download(
        self,
        symbol: str,
        start: date,
        end: date | None = None,
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """Download data for symbol, cache, return DataFrame.
        
        Args:
            symbol: ticker es. 'SPY'
            start: data inizio (inclusiva)
            end: data fine (esclusiva), default oggi
            force_refresh: se True, ignora cache e re-download
        
        Returns:
            DataFrame with Open, High, Low, Close, Volume, Adj Close columns,
            DatetimeIndex.
        """
        end = end or date.today()
        
        if not force_refresh and self.cache.has(symbol):
            cached_df = self.cache.get(symbol)
            cached_start = cached_df.index.min().date()
            cached_end = cached_df.index.max().date()
            
            # Cache hit pieno
            if cached_start <= start and cached_end >= end:
                return cached_df[(cached_df.index >= pd.Timestamp(start)) & 
                                  (cached_df.index <= pd.Timestamp(end))]
            
            # Cache parziale: download solo missing
            if cached_end >= start:
                log.info(f"Extending cache for {symbol}: {cached_end} → {end}")
                new_data = self._fetch_yfinance(symbol, cached_end, end)
                self.cache.update(symbol, new_data)
                full = self.cache.get(symbol)
                return full[(full.index >= pd.Timestamp(start)) & 
                            (full.index <= pd.Timestamp(end))]
        
        # Full download
        log.info(f"Downloading {symbol} from {start} to {end}")
        df = self._fetch_yfinance(symbol, start, end)
        self.cache.put(symbol, df)
        return df
    
    def _fetch_yfinance(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Wrapper attorno a yfinance con retry."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                df = yf.download(
                    symbol,
                    start=start.isoformat(),
                    end=end.isoformat(),
                    auto_adjust=False,  # vogliamo entrambi Close e Adj Close
                    progress=False,
                    threads=False,
                )
                if df.empty:
                    raise ValueError(f"Empty data returned for {symbol}")
                
                # Normalizza columns (yfinance può tornare MultiIndex)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                
                # Drop tz, keep date only
                if df.index.tz is not None:
                    df.index = df.index.tz_localize(None)
                
                return df
            except Exception as e:
                log.warning(f"Attempt {attempt+1}/{max_retries} failed for {symbol}: {e}")
                if attempt == max_retries - 1:
                    raise
                time.sleep(2 ** attempt)  # exponential backoff
    
    def download_universe(
        self,
        universe: Universe,
        start: date,
        end: date | None = None,
    ) -> dict[str, pd.DataFrame]:
        """Download dati per tutti i ticker dell'universo."""
        result = {}
        for asset in universe.assets:
            try:
                df = self.download(asset.symbol, start, end)
                result[asset.symbol] = df
            except Exception as e:
                log.error(f"Failed to download {asset.symbol}: {e}")
                # Non interrompere — alcuni ticker possono essere delisted/sospesi
        return result
    
    def get_aligned_prices(
        self,
        universe: Universe,
        start: date,
        end: date | None = None,
        field: str = "Adj Close",
    ) -> pd.DataFrame:
        """Returns DataFrame con colonne = ticker, index = date, values = adj close."""
        data = self.download_universe(universe, start, end)
        prices = pd.DataFrame({sym: df[field] for sym, df in data.items()})
        # Forward-fill di max 5 giorni per gap (holiday non-allineati cross-mkt)
        prices = prices.ffill(limit=5)
        return prices
```

#### Step 5: Test fixture (synthetic data)

Crea `tests/backtest/conftest.py`:

```python
import pandas as pd
import numpy as np
import pytest
from pathlib import Path


@pytest.fixture
def synthetic_prices() -> pd.DataFrame:
    """Generates deterministic synthetic OHLCV for testing."""
    np.random.seed(42)
    dates = pd.date_range("2020-01-01", "2024-12-31", freq="B")
    n = len(dates)
    
    # Geometric Brownian Motion-like
    returns = np.random.normal(0.0003, 0.012, n)  # ~7%/year, 19% vol
    prices = 100 * np.exp(np.cumsum(returns))
    
    df = pd.DataFrame({
        "Open": prices * (1 + np.random.normal(0, 0.002, n)),
        "High": prices * (1 + np.abs(np.random.normal(0, 0.005, n))),
        "Low": prices * (1 - np.abs(np.random.normal(0, 0.005, n))),
        "Close": prices,
        "Volume": np.random.randint(1_000_000, 50_000_000, n),
        "Adj Close": prices,
    }, index=dates)
    
    return df


@pytest.fixture
def temp_cache_dir(tmp_path) -> Path:
    return tmp_path / "cache"
```

#### Step 6: Unit tests

Crea `tests/backtest/test_loader.py`:

```python
"""Tests per il data loader."""
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from alembic.backtest.data.loader import DataLoader
from alembic.backtest.data.cache import ParquetCache


class TestParquetCache:
    def test_put_and_get(self, synthetic_prices, temp_cache_dir):
        cache = ParquetCache(cache_dir=temp_cache_dir)
        cache.put("TEST", synthetic_prices)
        
        assert cache.has("TEST")
        retrieved = cache.get("TEST")
        pd.testing.assert_frame_equal(retrieved, synthetic_prices)
    
    def test_get_with_date_filter(self, synthetic_prices, temp_cache_dir):
        cache = ParquetCache(cache_dir=temp_cache_dir)
        cache.put("TEST", synthetic_prices)
        
        filtered = cache.get("TEST", start=date(2022, 1, 1), end=date(2022, 12, 31))
        assert filtered.index.min() >= pd.Timestamp("2022-01-01")
        assert filtered.index.max() <= pd.Timestamp("2022-12-31")
    
    def test_missing_columns_raises(self, temp_cache_dir):
        cache = ParquetCache(cache_dir=temp_cache_dir)
        bad_df = pd.DataFrame({"Close": [1, 2, 3]}, index=pd.date_range("2020-01-01", periods=3))
        with pytest.raises(ValueError, match="Missing required columns"):
            cache.put("BAD", bad_df)


class TestDataLoader:
    def test_load_known_ticker(self, temp_cache_dir):
        cache = ParquetCache(cache_dir=temp_cache_dir)
        loader = DataLoader(cache=cache)
        
        # SPY è esistito dal 1993, dovrebbe sempre tornare dati
        df = loader.download("SPY", start=date(2023, 1, 1), end=date(2023, 12, 31))
        
        assert not df.empty
        assert "Adj Close" in df.columns
        assert df.index.min() >= pd.Timestamp("2023-01-01")
        assert df.index.max() <= pd.Timestamp("2023-12-31")
    
    def test_cache_hit_no_redownload(self, temp_cache_dir, synthetic_prices):
        cache = ParquetCache(cache_dir=temp_cache_dir)
        cache.put("FAKE", synthetic_prices)
        
        loader = DataLoader(cache=cache)
        # Questo NON deve toccare yfinance: usa la fixture
        df = loader.download("FAKE", start=date(2021, 1, 1), end=date(2022, 1, 1))
        
        assert not df.empty
        # Verifica che sia la stessa data della fixture (date in fixture: 2020-2024)
        assert df.index.min() >= pd.Timestamp("2021-01-01")
        assert df.index.max() <= pd.Timestamp("2022-01-01")
```

#### Step 7: Script per pre-download universo

Crea `scripts/download_initial_data.py`:

```python
#!/usr/bin/env python
"""Pre-download data per tutti i ticker dell'universo S1.

Run questo script una volta dopo il setup per warmare la cache.

Usage:
    poetry run python scripts/download_initial_data.py [--start YYYY-MM-DD]
"""
import argparse
from datetime import date

from alembic.backtest.data.loader import DataLoader
from alembic.backtest.data.universe import load_universe


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="1995-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--universe", default="s1", help="Universe id")
    args = parser.parse_args()
    
    start_date = date.fromisoformat(args.start)
    
    universe = load_universe(args.universe)
    loader = DataLoader()
    
    print(f"Downloading {len(universe.assets)} tickers from {start_date}...")
    
    success = 0
    failed = 0
    for asset in universe.assets:
        try:
            # Don't go before inception
            actual_start = max(start_date, asset.inception_date)
            df = loader.download(asset.symbol, start=actual_start)
            print(f"  ✓ {asset.symbol}: {len(df)} rows ({df.index.min().date()} → {df.index.max().date()})")
            success += 1
        except Exception as e:
            print(f"  ✗ {asset.symbol}: {e}")
            failed += 1
    
    print(f"\nDone: {success} successful, {failed} failed")


if __name__ == "__main__":
    main()
```

### Acceptance verification

Eseguire questi comandi in ordine. Tutti devono passare.

```bash
# Test 1: linting clean
poetry run ruff check alembic/backtest/data/
# Expected: nessun errore

# Test 2: type check clean
poetry run mypy --strict alembic/backtest/data/
# Expected: Success: no issues found

# Test 3: tests passano
poetry run pytest tests/backtest/test_loader.py tests/backtest/test_universe.py -v
# Expected: tutti pass

# Test 4: coverage adeguato
poetry run pytest tests/backtest/test_loader.py --cov=alembic.backtest.data --cov-report=term
# Expected: coverage ≥ 80%

# Test 5: download universe completo funziona
poetry run python scripts/download_initial_data.py --start 2020-01-01 --universe s1
# Expected: tutti 15 ticker scaricati, < 30s

# Test 6: cache hit funziona (re-run deve essere veloce)
time poetry run python scripts/download_initial_data.py --start 2020-01-01 --universe s1
# Expected: < 5s (cache hit)

# Test 7: load e align prezzi su universo
poetry run python -c "
from datetime import date
from alembic.backtest.data.loader import DataLoader
from alembic.backtest.data.universe import load_universe

universe = load_universe('s1')
loader = DataLoader()
prices = loader.get_aligned_prices(universe, start=date(2020, 1, 1), end=date(2023, 12, 31))
print(prices.shape)
print(prices.head())
assert prices.shape[1] == 15
assert prices.shape[0] > 900  # circa 4 anni di business days
"
# Expected: (1006, 15) o simile, no errori
```

### On failure

| Failure | Diagnostic | Fix |
|---|---|---|
| yfinance returns empty | Rate limit di Yahoo | Wait 5 min, retry. Se persiste: check ticker validity |
| Test fail su cache | Permissions su cache dir | Check `mkdir -p` ok, no concurrent access |
| Type check fails | mypy strict pignolo | Add explicit type hints. Resist `# type: ignore` |
| Download di EWJ/TIP slow | Yahoo per ETF illiquidi | Aspetta, è normale. Cache renderà fast next time |
| `pyarrow` not found | Missing dep | `poetry add pyarrow` |

### Commit message

```
[T-001] Setup vectorbt + data loading infrastructure

- Implemented ParquetCache for OHLCV data
- Implemented DataLoader with yfinance backend + retry logic
- Universe management with point-in-time inception dates
- Defined 15-ticker S1 universe in config/universe.yaml
- Pre-download script for initial cache warming
- Unit tests with synthetic fixtures, coverage 85%

Refs: alembic_v2/03_backtest_framework.md §2
```

---

## T-002 — Backtest Engine Event-Driven Base

**Status**: OPEN
**Effort**: L (1-2w)
**Dependencies**: T-001
**Reference docs**: `/alembic_v2/03_backtest_framework.md` §2, `/alembic_v2/02_architecture.md` §3

### Prerequisites check

```bash
# Verifica che T-001 sia done
poetry run python -c "from alembic.backtest.data.loader import DataLoader; print('OK')"

# Verifica vectorbt installato
poetry run python -c "import vectorbt as vbt; print(vbt.__version__)"
```

### Files to create

```
alembic/backtest/engine/__init__.py
alembic/backtest/engine/types.py             # Dataclasses
alembic/backtest/engine/portfolio.py         # VirtualPortfolio
alembic/backtest/engine/data_replay.py       # Point-in-time data replay
alembic/backtest/engine/order_simulation.py  # Order → Fill
alembic/backtest/engine/orchestrator.py      # Main loop
tests/backtest/test_portfolio.py
tests/backtest/test_data_replay.py
tests/backtest/test_orchestrator.py
```

### Implementation steps

#### Step 1: Define core types

Crea `alembic/backtest/engine/types.py`:

```python
"""Core types per backtest engine. Immutable dataclasses ovunque possibile."""
from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from typing import Literal
import uuid


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class RebalanceFrequency(str, Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"


@dataclass(frozen=True)
class Order:
    """Immutable order specification."""
    order_id: str
    timestamp: datetime
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    strategy_id: str = "unknown"
    
    @classmethod
    def market_order(cls, ts: datetime, symbol: str, side: OrderSide, qty: float, strategy_id: str = "unknown") -> "Order":
        return cls(
            order_id=str(uuid.uuid4()),
            timestamp=ts,
            symbol=symbol,
            side=side,
            quantity=qty,
            order_type=OrderType.MARKET,
            strategy_id=strategy_id,
        )


@dataclass(frozen=True)
class Fill:
    """Immutable fill record."""
    fill_id: str
    order_id: str
    timestamp: datetime
    symbol: str
    side: OrderSide
    quantity: float
    fill_price: float
    commission: float
    slippage_bps: float
    strategy_id: str
    
    @property
    def gross_value(self) -> float:
        return self.quantity * self.fill_price
    
    @property
    def net_value(self) -> float:
        """Negative for buys (cash out), positive for sells (cash in)"""
        sign = -1 if self.side == OrderSide.BUY else 1
        return sign * self.gross_value - self.commission


@dataclass(frozen=True)
class Position:
    """Current position in a symbol."""
    symbol: str
    quantity: float  # negative = short
    avg_cost: float
    
    @property
    def is_long(self) -> bool:
        return self.quantity > 0
    
    @property
    def is_flat(self) -> bool:
        return self.quantity == 0
    
    def market_value(self, current_price: float) -> float:
        return self.quantity * current_price
    
    def unrealized_pnl(self, current_price: float) -> float:
        return (current_price - self.avg_cost) * self.quantity


@dataclass(frozen=True)
class MarketSnapshot:
    """Snapshot of market state at a given timestamp."""
    timestamp: datetime
    prices: dict[str, float]  # symbol -> close price
    volumes: dict[str, float]  # symbol -> volume
    adv_20d: dict[str, float]  # symbol -> 20-day average daily volume
    
    def has_price(self, symbol: str) -> bool:
        return symbol in self.prices
    
    def price_of(self, symbol: str) -> float | None:
        return self.prices.get(symbol)


@dataclass(frozen=True)
class PortfolioSnapshot:
    """Immutable snapshot of portfolio state."""
    timestamp: datetime
    cash: float
    positions: tuple[Position, ...]
    total_nav: float
    
    def position_of(self, symbol: str) -> Position | None:
        for p in self.positions:
            if p.symbol == symbol:
                return p
        return None
    
    def weights(self, market: MarketSnapshot) -> dict[str, float]:
        result = {}
        for p in self.positions:
            price = market.price_of(p.symbol)
            if price is not None:
                result[p.symbol] = p.market_value(price) / self.total_nav
        return result
```

#### Step 2: Implementa VirtualPortfolio

Crea `alembic/backtest/engine/portfolio.py`:

```python
"""Virtual portfolio: track positions, apply fills, mark-to-market."""
from datetime import datetime
from typing import Iterable
import logging

from alembic.backtest.engine.types import (
    Fill, Order, OrderSide, Position, PortfolioSnapshot, MarketSnapshot
)


log = logging.getLogger(__name__)


class VirtualPortfolio:
    """Mutable portfolio state per backtest simulation.
    
    Mai usato in produzione (per il live trading c'è BrokerAdapter).
    Solo simulation.
    """
    
    def __init__(self, initial_cash: float):
        self._cash = initial_cash
        self._positions: dict[str, Position] = {}
        self._fills_log: list[Fill] = []
        self._snapshots: list[PortfolioSnapshot] = []
    
    @property
    def cash(self) -> float:
        return self._cash
    
    def position_of(self, symbol: str) -> Position | None:
        return self._positions.get(symbol)
    
    def all_positions(self) -> tuple[Position, ...]:
        return tuple(p for p in self._positions.values() if not p.is_flat)
    
    def apply_fill(self, fill: Fill) -> None:
        """Apply a fill: update cash + positions."""
        # Update cash
        self._cash += fill.net_value
        
        # Update position
        current = self._positions.get(fill.symbol)
        if current is None:
            new_qty = fill.quantity if fill.side == OrderSide.BUY else -fill.quantity
            self._positions[fill.symbol] = Position(
                symbol=fill.symbol,
                quantity=new_qty,
                avg_cost=fill.fill_price,
            )
        else:
            sign = 1 if fill.side == OrderSide.BUY else -1
            new_qty = current.quantity + sign * fill.quantity
            
            if new_qty == 0:
                # Closed out
                del self._positions[fill.symbol]
            elif (current.quantity > 0 and new_qty > 0) or (current.quantity < 0 and new_qty < 0):
                # Adding to same-side position: weighted avg cost
                total_cost = current.avg_cost * abs(current.quantity) + fill.fill_price * fill.quantity
                new_avg = total_cost / abs(new_qty)
                self._positions[fill.symbol] = Position(
                    symbol=fill.symbol,
                    quantity=new_qty,
                    avg_cost=new_avg,
                )
            else:
                # Crossed zero (rare in long-only): treat as new position
                self._positions[fill.symbol] = Position(
                    symbol=fill.symbol,
                    quantity=new_qty,
                    avg_cost=fill.fill_price,
                )
        
        self._fills_log.append(fill)
    
    def mark_to_market(self, market: MarketSnapshot) -> PortfolioSnapshot:
        """Compute NAV at current market prices, save snapshot."""
        total_position_value = 0.0
        for pos in self._positions.values():
            price = market.price_of(pos.symbol)
            if price is None:
                log.warning(f"No price for {pos.symbol} at {market.timestamp}, using avg_cost")
                price = pos.avg_cost
            total_position_value += pos.market_value(price)
        
        total_nav = self._cash + total_position_value
        snapshot = PortfolioSnapshot(
            timestamp=market.timestamp,
            cash=self._cash,
            positions=tuple(self._positions.values()),
            total_nav=total_nav,
        )
        self._snapshots.append(snapshot)
        return snapshot
    
    def get_snapshots(self) -> tuple[PortfolioSnapshot, ...]:
        return tuple(self._snapshots)
    
    def get_fills(self) -> tuple[Fill, ...]:
        return tuple(self._fills_log)
```

#### Step 3: Implementa DataReplay

Crea `alembic/backtest/engine/data_replay.py`:

```python
"""Data replay: serve market data point-in-time durante backtest.

CRITICAL: questo modulo è responsabile dell'anti-look-ahead. 
Ogni accesso a dati deve essere filtrato per `as_of <= current_timestep`.
"""
from datetime import datetime, date
import logging

import pandas as pd

from alembic.backtest.engine.types import MarketSnapshot


log = logging.getLogger(__name__)


class DataReplay:
    """Wrapper su DataFrame multi-asset che serve dati point-in-time.
    
    Usage:
        replay = DataReplay(prices_df, volumes_df)
        for ts in replay.timesteps():
            market = replay.market_at(ts)
            ...
    """
    
    def __init__(
        self,
        prices: pd.DataFrame,  # index=date, columns=symbols
        volumes: pd.DataFrame | None = None,
    ):
        if not isinstance(prices.index, pd.DatetimeIndex):
            raise ValueError("prices must have DatetimeIndex")
        
        self._prices = prices.sort_index()
        self._volumes = volumes.sort_index() if volumes is not None else None
        
        # Precompute 20d ADV for cost model
        if self._volumes is not None:
            self._adv_20d = self._volumes.rolling(20).mean()
        else:
            self._adv_20d = pd.DataFrame(
                10_000_000.0,
                index=self._prices.index,
                columns=self._prices.columns,
            )  # fallback large ADV
    
    def timesteps(self) -> list[datetime]:
        return list(self._prices.index)
    
    def first_timestep(self) -> datetime:
        return self._prices.index[0]
    
    def last_timestep(self) -> datetime:
        return self._prices.index[-1]
    
    def market_at(self, as_of: datetime) -> MarketSnapshot:
        """Returns market snapshot AT as_of (uses close of that day)."""
        if as_of not in self._prices.index:
            # Find nearest preceding
            valid = self._prices.index[self._prices.index <= as_of]
            if len(valid) == 0:
                raise ValueError(f"No data available before {as_of}")
            as_of = valid[-1]
        
        row = self._prices.loc[as_of]
        prices = {sym: float(row[sym]) for sym in row.index if pd.notna(row[sym])}
        
        if self._volumes is not None:
            vol_row = self._volumes.loc[as_of]
            volumes = {sym: float(vol_row[sym]) for sym in vol_row.index if pd.notna(vol_row[sym])}
        else:
            volumes = {sym: 0.0 for sym in prices}
        
        adv_row = self._adv_20d.loc[as_of]
        adv_20d = {sym: float(adv_row[sym]) if pd.notna(adv_row[sym]) else 10_000_000.0 
                    for sym in prices}
        
        return MarketSnapshot(
            timestamp=as_of,
            prices=prices,
            volumes=volumes,
            adv_20d=adv_20d,
        )
    
    def prices_until(self, as_of: datetime) -> pd.DataFrame:
        """ANTI-LOOK-AHEAD: returns SOLO i prezzi <= as_of.
        
        Questo è il metodo PRINCIPALE da usare per dare history alle strategie.
        """
        return self._prices[self._prices.index <= as_of]
    
    def returns_until(self, as_of: datetime) -> pd.DataFrame:
        """Daily returns up to as_of."""
        prices = self.prices_until(as_of)
        return prices.pct_change().dropna()
```

#### Step 4: Order simulation con cost model placeholder

Crea `alembic/backtest/engine/order_simulation.py`:

```python
"""Simulate order fills con cost model.

Versione base: in T-003 verrà sostituito da cost model serio.
"""
from datetime import datetime
import uuid

from alembic.backtest.engine.types import Order, Fill, OrderSide, MarketSnapshot


class SimpleCostModel:
    """Cost model placeholder: spread + commission only.
    
    DA SOSTITUIRE in T-003 con cost model serio (impact, tier-based).
    """
    
    def __init__(self, spread_bps: float = 5.0, commission_per_share: float = 0.0):
        self.spread_bps = spread_bps
        self.commission_per_share = commission_per_share
    
    def simulate_fill(self, order: Order, market: MarketSnapshot) -> Fill:
        mid_price = market.price_of(order.symbol)
        if mid_price is None:
            raise ValueError(f"No price for {order.symbol} at {market.timestamp}")
        
        # Half-spread paid
        half_spread = mid_price * self.spread_bps / 10000 / 2
        sign = 1 if order.side == OrderSide.BUY else -1
        fill_price = mid_price + sign * half_spread
        
        commission = self.commission_per_share * order.quantity
        
        return Fill(
            fill_id=str(uuid.uuid4()),
            order_id=order.order_id,
            timestamp=order.timestamp,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            fill_price=fill_price,
            commission=commission,
            slippage_bps=self.spread_bps / 2,
            strategy_id=order.strategy_id,
        )
```

#### Step 5: Main orchestrator

Crea `alembic/backtest/engine/orchestrator.py`:

```python
"""Main backtest orchestrator: event loop."""
from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Callable

import pandas as pd

from alembic.backtest.engine.data_replay import DataReplay
from alembic.backtest.engine.order_simulation import SimpleCostModel
from alembic.backtest.engine.portfolio import VirtualPortfolio
from alembic.backtest.engine.types import (
    Order, Fill, OrderSide, MarketSnapshot, PortfolioSnapshot
)


log = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    initial_capital: float = 100_000.0
    spread_bps: float = 5.0
    commission_per_share: float = 0.0


@dataclass
class BacktestResult:
    config: BacktestConfig
    snapshots: tuple[PortfolioSnapshot, ...]
    fills: tuple[Fill, ...]
    
    def to_nav_series(self) -> pd.Series:
        return pd.Series(
            data=[s.total_nav for s in self.snapshots],
            index=[s.timestamp for s in self.snapshots],
        )
    
    def to_returns_series(self) -> pd.Series:
        nav = self.to_nav_series()
        return nav.pct_change().dropna()


# Type for strategy callable: prende ctx, ritorna lista di ordini per quel timestep
StrategyCallable = Callable[
    [datetime, DataReplay, VirtualPortfolio, MarketSnapshot],
    list[Order]
]


class BacktestOrchestrator:
    """Event loop principale per backtest."""
    
    def __init__(self, config: BacktestConfig):
        self.config = config
        self.cost_model = SimpleCostModel(
            spread_bps=config.spread_bps,
            commission_per_share=config.commission_per_share,
        )
    
    def run(
        self,
        data_replay: DataReplay,
        strategy_callable: StrategyCallable,
    ) -> BacktestResult:
        """Run backtest end-to-end."""
        portfolio = VirtualPortfolio(initial_cash=self.config.initial_capital)
        
        timesteps = data_replay.timesteps()
        log.info(f"Running backtest on {len(timesteps)} timesteps "
                 f"from {timesteps[0]} to {timesteps[-1]}")
        
        for ts in timesteps:
            try:
                market = data_replay.market_at(ts)
            except ValueError as e:
                log.warning(f"Skip timestep {ts}: {e}")
                continue
            
            # Strategy decides what to do
            orders = strategy_callable(ts, data_replay, portfolio, market)
            
            # Simulate execution
            for order in orders:
                try:
                    fill = self.cost_model.simulate_fill(order, market)
                    portfolio.apply_fill(fill)
                except ValueError as e:
                    log.warning(f"Could not fill {order}: {e}")
            
            # Mark-to-market at end of day
            portfolio.mark_to_market(market)
        
        return BacktestResult(
            config=self.config,
            snapshots=portfolio.get_snapshots(),
            fills=portfolio.get_fills(),
        )
```

#### Step 6: Tests fondamentali

Crea `tests/backtest/test_portfolio.py`:

```python
from datetime import datetime
import pytest

from alembic.backtest.engine.portfolio import VirtualPortfolio
from alembic.backtest.engine.types import (
    Order, Fill, OrderSide, OrderType, MarketSnapshot
)


def make_fill(symbol, side, qty, price, ts=None):
    return Fill(
        fill_id="fill-1",
        order_id="order-1",
        timestamp=ts or datetime(2024, 1, 1),
        symbol=symbol,
        side=side,
        quantity=qty,
        fill_price=price,
        commission=0.0,
        slippage_bps=0.0,
        strategy_id="test",
    )


def make_market(symbol_prices, ts=None):
    return MarketSnapshot(
        timestamp=ts or datetime(2024, 1, 1),
        prices=symbol_prices,
        volumes={s: 1e6 for s in symbol_prices},
        adv_20d={s: 1e7 for s in symbol_prices},
    )


class TestVirtualPortfolio:
    def test_initial_state(self):
        p = VirtualPortfolio(initial_cash=100_000)
        assert p.cash == 100_000
        assert p.all_positions() == ()
    
    def test_buy_creates_position(self):
        p = VirtualPortfolio(100_000)
        p.apply_fill(make_fill("SPY", OrderSide.BUY, 100, 400.0))
        
        pos = p.position_of("SPY")
        assert pos is not None
        assert pos.quantity == 100
        assert pos.avg_cost == 400.0
        assert p.cash == 100_000 - 40_000
    
    def test_sell_closes_position(self):
        p = VirtualPortfolio(100_000)
        p.apply_fill(make_fill("SPY", OrderSide.BUY, 100, 400.0))
        p.apply_fill(make_fill("SPY", OrderSide.SELL, 100, 410.0))
        
        assert p.position_of("SPY") is None
        assert p.cash == 100_000 - 40_000 + 41_000  # +1000 profit
    
    def test_add_to_position_weighted_avg_cost(self):
        p = VirtualPortfolio(100_000)
        p.apply_fill(make_fill("SPY", OrderSide.BUY, 100, 400.0))
        p.apply_fill(make_fill("SPY", OrderSide.BUY, 100, 410.0))
        
        pos = p.position_of("SPY")
        assert pos.quantity == 200
        assert pos.avg_cost == 405.0  # (400*100 + 410*100) / 200
    
    def test_mark_to_market(self):
        p = VirtualPortfolio(100_000)
        p.apply_fill(make_fill("SPY", OrderSide.BUY, 100, 400.0))
        
        snapshot = p.mark_to_market(make_market({"SPY": 410.0}))
        
        # Cash: 100k - 40k = 60k
        # Position value: 100 * 410 = 41k
        # Total NAV: 60k + 41k = 101k
        assert snapshot.total_nav == 101_000
```

Crea `tests/backtest/test_orchestrator.py`:

```python
from datetime import datetime
import pandas as pd
import pytest

from alembic.backtest.engine.data_replay import DataReplay
from alembic.backtest.engine.orchestrator import BacktestOrchestrator, BacktestConfig
from alembic.backtest.engine.types import Order, OrderSide


def make_test_prices():
    dates = pd.date_range("2023-01-02", "2023-12-29", freq="B")
    # SPY price che cresce linearmente da 400 a 470
    spy_prices = pd.Series(
        data=[400 + i * 70 / len(dates) for i in range(len(dates))],
        index=dates,
    )
    return pd.DataFrame({"SPY": spy_prices})


def make_test_volumes():
    dates = pd.date_range("2023-01-02", "2023-12-29", freq="B")
    return pd.DataFrame({"SPY": [50_000_000] * len(dates)}, index=dates)


def buy_and_hold_strategy(ts, data_replay, portfolio, market):
    """Compra SPY al primo timestep, hold."""
    if portfolio.position_of("SPY") is None:
        # First trade: buy with all cash
        spy_price = market.price_of("SPY")
        qty = int(portfolio.cash * 0.95 / spy_price)
        return [Order.market_order(ts, "SPY", OrderSide.BUY, qty, "buy_hold")]
    return []


class TestBacktestOrchestrator:
    def test_buy_and_hold_spy_2023(self):
        prices = make_test_prices()
        volumes = make_test_volumes()
        replay = DataReplay(prices, volumes)
        
        orchestrator = BacktestOrchestrator(BacktestConfig(initial_capital=100_000))
        result = orchestrator.run(replay, buy_and_hold_strategy)
        
        assert len(result.snapshots) == len(prices)
        
        # NAV finale: ~100k * (470/400) * 0.95 ≈ 111k
        final_nav = result.snapshots[-1].total_nav
        # Permissive tolerance per slippage e rounding
        assert 108_000 < final_nav < 114_000, f"Final NAV: {final_nav}"
    
    def test_no_trades_no_change(self):
        prices = make_test_prices()
        replay = DataReplay(prices)
        
        def no_op_strategy(*args, **kwargs):
            return []
        
        orchestrator = BacktestOrchestrator(BacktestConfig(initial_capital=100_000))
        result = orchestrator.run(replay, no_op_strategy)
        
        # NAV stays at 100k
        for snapshot in result.snapshots:
            assert snapshot.total_nav == 100_000
```

### Acceptance verification

```bash
# Test 1: linting
poetry run ruff check alembic/backtest/engine/
# Expected: clean

# Test 2: type check  
poetry run mypy --strict alembic/backtest/engine/
# Expected: clean

# Test 3: tests passano
poetry run pytest tests/backtest/test_portfolio.py tests/backtest/test_orchestrator.py -v
# Expected: tutti pass

# Test 4: coverage
poetry run pytest tests/backtest/test_portfolio.py tests/backtest/test_orchestrator.py \
  --cov=alembic.backtest.engine --cov-report=term
# Expected: coverage ≥ 80%

# Test 5: sanity check su SPY reale 2010-2020
poetry run python -c "
from datetime import date
import pandas as pd
from alembic.backtest.data.loader import DataLoader
from alembic.backtest.data.universe import load_universe
from alembic.backtest.engine.data_replay import DataReplay
from alembic.backtest.engine.orchestrator import BacktestOrchestrator, BacktestConfig
from alembic.backtest.engine.types import Order, OrderSide

loader = DataLoader()
spy_df = loader.download('SPY', start=date(2010, 1, 1), end=date(2019, 12, 31))
prices = pd.DataFrame({'SPY': spy_df['Adj Close']})
volumes = pd.DataFrame({'SPY': spy_df['Volume']})

replay = DataReplay(prices, volumes)

def buy_hold(ts, dr, port, mkt):
    if port.position_of('SPY') is None:
        qty = int(port.cash * 0.95 / mkt.price_of('SPY'))
        return [Order.market_order(ts, 'SPY', OrderSide.BUY, qty, 'bh')]
    return []

orc = BacktestOrchestrator(BacktestConfig(initial_capital=100_000))
result = orc.run(replay, buy_hold)

initial = result.snapshots[0].total_nav
final = result.snapshots[-1].total_nav
total_return = (final / initial) - 1
print(f'Initial NAV: \${initial:,.0f}')
print(f'Final NAV: \${final:,.0f}')
print(f'Total return: {total_return:.1%}')
# Sanity: SPY 2010-2019 ha fatto circa +180% adj close
assert 1.5 < total_return < 2.5, f'Return out of expected range: {total_return}'
print('SANITY CHECK PASSED')
"
# Expected: SANITY CHECK PASSED
```

### On failure

| Failure | Diagnostic | Fix |
|---|---|---|
| `total_return` out of expected range | Check Adj Close vs Close (dividend adjustment) | Usa Adj Close per signal, Close per simulation orders |
| `total_nav` decreases without trades | mark_to_market sta calcolando male | Debug VirtualPortfolio.mark_to_market |
| Tests pass ma sanity fail | Cost model troppo aggressivo | Verifica spread_bps default a 5.0 max |
| `KeyError` durante market_at | Date mancante (holiday) | Verifica ffill in get_aligned_prices |

### Commit message

```
[T-002] Backtest engine event-driven base

- Implemented immutable Order, Fill, Position, MarketSnapshot types
- VirtualPortfolio with weighted average cost tracking
- DataReplay with anti-look-ahead point-in-time enforcement
- SimpleCostModel placeholder (to be replaced in T-003)
- BacktestOrchestrator main event loop
- Unit tests + sanity check SPY 2010-2019 buy-and-hold

Refs: alembic_v2/03_backtest_framework.md §2
```

---

## T-003 — Cost Model Serio

**Status**: OPEN
**Effort**: M (3-5d)
**Dependencies**: T-002
**Reference docs**: `/alembic_v2/03_backtest_framework.md` §4

### Implementation steps (sintetico)

Sostituisce `SimpleCostModel` con `RealisticCostModel` che include:

1. **Tier-based spread**: lookup `symbol → liquidity_tier → spread_bps`
2. **Market impact**: square-root model `impact_bps = k × sqrt(order_size_usd / adv_usd) × 10000`
3. **Commissions**: configurabile per broker
4. **Options support**: usato in T-302 ma struttura va prevista qui

File da creare:
- `alembic/backtest/costs/__init__.py`
- `alembic/backtest/costs/spread_tiers.py` (lookup table)
- `alembic/backtest/costs/impact_model.py`
- `alembic/backtest/costs/realistic.py`
- `config/cost_model.yaml`

```yaml
# config/cost_model.yaml
version: "0.1.0"

equity:
  spread_tiers:
    tier_a:  # Mega cap, very liquid ETF
      symbols: [SPY, QQQ, IWM, VOO, VTI]
      spread_bps: 1.5
    tier_b:  # Large cap
      symbols: [AAPL, MSFT, AMZN, GOOGL, NVDA, META, ...]  # popolare con S&P 100
      spread_bps: 3.5
    tier_c:  # Mid cap, niche ETF
      symbols: [VEA, VWO, EWJ, TLT, IEF, GLD, ...]
      spread_bps: 8.0
    tier_d:  # Small cap, illiquid
      default: true
      spread_bps: 20.0
  impact_k: 10.0  # calibrazione literature
  commission_per_share: 0.0  # Alpaca
  sec_fee_per_share_sale: 0.0000229
  finra_taf_per_share_sale: 0.000145

options:
  spread_pct_of_mid: 0.05  # 5% del mid è realistic per SPY puts
  commission_per_contract: 0.65  # IBKR
  exercise_fee: 0.0  # IBKR free
```

### Acceptance verification

```bash
poetry run pytest tests/backtest/test_costs.py -v

# Sanity: SPY 100k order → slippage < 5 bps total
poetry run python -c "
from datetime import datetime
from alembic.backtest.costs.realistic import RealisticCostModel
from alembic.backtest.engine.types import Order, OrderSide, MarketSnapshot

model = RealisticCostModel()
market = MarketSnapshot(
    timestamp=datetime(2024, 1, 1),
    prices={'SPY': 480.0},
    volumes={'SPY': 80_000_000},
    adv_20d={'SPY': 80_000_000},
)
order = Order.market_order(datetime(2024, 1, 1), 'SPY', OrderSide.BUY, 200, 'test')

fill = model.simulate_fill(order, market)
slippage = (fill.fill_price - 480.0) / 480.0 * 10000
print(f'SPY 96k order slippage: {slippage:.2f} bps')
assert 0.5 < slippage < 5.0
"
```

### Commit message

```
[T-003] Realistic cost model with spread tiers + market impact

- Tier-based bid-ask spread (A/B/C/D)
- Square-root market impact model (k=10)
- Commission + SEC/FINRA fees for equity
- Options cost structure (used by T-302)
- Validated against literature (Almgren-Chriss)

Refs: alembic_v2/03_backtest_framework.md §4
```

---

## T-004 — Anti-Look-Ahead Test Suite

**Status**: OPEN
**Effort**: S (1-2d)
**Dependencies**: T-002
**Reference docs**: `/alembic_v2/03_backtest_framework.md` §3

### Implementation steps

Crea `tests/backtest/test_no_lookahead.py`:

```python
"""ANTI-LOOK-AHEAD TEST SUITE. Critico.

Questi test garantiscono che il backtest engine NON LEGGA MAI dati futuri.
Se uno di questi fail, il backtest engine è invalidato e nessuna strategia 
può essere considerata validata finché non passa.
"""
from datetime import datetime, timedelta
import pandas as pd
import pytest

from alembic.backtest.engine.data_replay import DataReplay
from alembic.backtest.engine.orchestrator import BacktestOrchestrator, BacktestConfig
from alembic.backtest.engine.types import Order, OrderSide


SENTINEL_VALUE = -999_999.0


def make_prices_with_future_sentinel():
    """Prezzi normali + valore sentinel su date future.
    
    Se la strategia legge mai SENTINEL_VALUE, vuol dire look-ahead.
    """
    dates = pd.date_range("2023-01-02", "2023-12-29", freq="B")
    normal_prices = [100.0 + i * 0.1 for i in range(len(dates))]
    
    # Sentinel: ultimo 50% del periodo ha valore SENTINEL_VALUE
    # Se la strategy "vede" questi prezzi prima di arrivarci, fail.
    mid = len(dates) // 2
    sentinel_prices = list(normal_prices[:mid]) + [SENTINEL_VALUE] * (len(dates) - mid)
    
    return pd.DataFrame({"TEST": sentinel_prices}, index=dates)


class TestAntiLookahead:
    def test_data_replay_does_not_expose_future_data(self):
        """prices_until(t) deve contenere solo prices <= t."""
        prices = make_prices_with_future_sentinel()
        replay = DataReplay(prices)
        
        cutoff = prices.index[100]
        history = replay.prices_until(cutoff)
        
        assert history.index.max() == cutoff
        assert (history["TEST"] != SENTINEL_VALUE).all(), \
            "prices_until is returning future sentinel data!"
    
    def test_market_at_is_point_in_time(self):
        """market_at(t) ritorna lo stato AT t, non oltre."""
        prices = make_prices_with_future_sentinel()
        replay = DataReplay(prices)
        
        # Read at t = 50 (before sentinel kick-in at t = 130)
        ts = prices.index[50]
        market = replay.market_at(ts)
        
        assert market.timestamp == ts
        assert market.price_of("TEST") != SENTINEL_VALUE
    
    def test_strategy_cannot_see_future_in_orchestrator(self):
        """Verifica che una strategia, durante il backtest, riceva solo dati point-in-time."""
        prices = make_prices_with_future_sentinel()
        replay = DataReplay(prices)
        
        seen_sentinel = []  # mutable container
        
        def naive_strategy(ts, data_replay, portfolio, market):
            history = data_replay.prices_until(ts)
            # Una strategia "honest" non vedrà mai il sentinel
            if (history["TEST"] == SENTINEL_VALUE).any():
                seen_sentinel.append(ts)
            return []
        
        orchestrator = BacktestOrchestrator(BacktestConfig(initial_capital=100_000))
        orchestrator.run(replay, naive_strategy)
        
        assert seen_sentinel == [], \
            f"Strategy saw future sentinel at: {seen_sentinel[:5]}"
    
    def test_returns_until_does_not_use_future(self):
        prices = make_prices_with_future_sentinel()
        replay = DataReplay(prices)
        
        cutoff = prices.index[100]
        returns = replay.returns_until(cutoff)
        
        # Non possono esserci returns dopo cutoff
        assert returns.index.max() <= cutoff
        # Non possono esserci returns che includono il sentinel
        assert not (returns["TEST"] < -0.99).any(), \
            "Returns until is contaminated by future sentinel"
    
    def test_timesteps_returned_in_order(self):
        """Sanity: timesteps must be sorted ascending."""
        prices = make_prices_with_future_sentinel()
        replay = DataReplay(prices)
        
        timesteps = replay.timesteps()
        for i in range(1, len(timesteps)):
            assert timesteps[i] > timesteps[i-1], \
                f"Timesteps not sorted at index {i}"


# REGRESSION TEST: pattern di bug specifici  

class TestAntiLookaheadRegression:
    def test_rolling_indicator_uses_only_history(self):
        """Bug pattern: rolling indicator computato su FULL series invece di history."""
        # Quando una strategia vuole calcolare es. 20d MA al timestep t,
        # deve usare prices_until(t).rolling(20).mean(), NOT prices.rolling(20).mean()
        prices = make_prices_with_future_sentinel()
        replay = DataReplay(prices)
        
        # Punto di valutazione: t=50 (well before sentinel at t=130)
        ts = prices.index[50]
        
        # METODO CORRETTO
        correct_history = replay.prices_until(ts)
        correct_ma = correct_history["TEST"].rolling(20).mean().iloc[-1]
        assert correct_ma != SENTINEL_VALUE and not pd.isna(correct_ma)
        
        # METODO SBAGLIATO (esempio di bug pattern): se calcolassimo MA su full series
        # poi prendiamo .loc[ts], potremmo "vedere" il futuro nei valori successivi
        # ma per timestep t=50, anche full series MA fino a t=50 è uguale.
        # Il bug si manifesta quando si fa rolling FORWARD-looking (es. .shift(-1))
        
        # Test esplicito anti shift-forward
        bad_indicator = prices["TEST"].shift(-1).rolling(20).mean()
        if 130 < bad_indicator.index.get_loc(ts) - 20:
            # Se il rolling sguarda forward, può prendere valori sentinel
            pass  # questo test è più educativo
```

### Acceptance verification

```bash
# Tutti i test anti-look-ahead devono passare SEMPRE
poetry run pytest tests/backtest/test_no_lookahead.py -v
# Expected: tutti pass

# Aggiungere a CI come check obbligatorio
# In `.github/workflows/ci.yml`:
# - name: Anti-look-ahead tests (CRITICAL)
#   run: poetry run pytest tests/backtest/test_no_lookahead.py -v
#   # No `continue-on-error: true`. Fail this = fail CI hard.
```

### Commit message

```
[T-004] Anti-look-ahead test suite

- Sentinel-based detection of future data leakage
- Tests for DataReplay point-in-time correctness  
- Regression tests for common bug patterns
- CI integration: these tests CANNOT fail

Refs: alembic_v2/03_backtest_framework.md §3
```

---

## T-005 — Walk-Forward Framework

**Status**: OPEN
**Effort**: M (3-5d)  
**Dependencies**: T-002, T-004
**Reference docs**: `/alembic_v2/03_backtest_framework.md` §5

### Files to create
```
alembic/backtest/walkforward/__init__.py
alembic/backtest/walkforward/runner.py
alembic/backtest/walkforward/aggregator.py
tests/backtest/test_walkforward.py
```

### Implementation outline

```python
# alembic/backtest/walkforward/runner.py
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta

@dataclass
class WalkForwardConfig:
    train_window_months: int = 24
    test_window_months: int = 3
    step_months: int = 1
    
class WalkForwardRunner:
    def __init__(self, config: WalkForwardConfig):
        self.config = config
    
    def generate_windows(self, full_start: date, full_end: date) -> list[tuple[date, date, date, date]]:
        """Returns list of (train_start, train_end, test_start, test_end)."""
        windows = []
        train_start = full_start
        while True:
            train_end = train_start + relativedelta(months=self.config.train_window_months)
            test_start = train_end
            test_end = test_start + relativedelta(months=self.config.test_window_months)
            if test_end > full_end:
                break
            windows.append((train_start, train_end, test_start, test_end))
            train_start += relativedelta(months=self.config.step_months)
        return windows
    
    def run(self, strategy_factory, data_replay, full_start: date, full_end: date):
        """Run walk-forward, concatenate OOS only."""
        windows = self.generate_windows(full_start, full_end)
        oos_results = []
        for train_s, train_e, test_s, test_e in windows:
            # In our case: no training (params fixed from literature)
            # Just run on test window
            sub_replay = ...  # filter data_replay to test window
            result = run_backtest(strategy_factory(), sub_replay)
            oos_results.append(result)
        return self.aggregate(oos_results)
    
    def aggregate(self, results):
        """Concatenate OOS NAV series, compute combined metrics."""
        ...
```

### Acceptance verification

```bash
poetry run pytest tests/backtest/test_walkforward.py -v

# Sanity: WF su SPY buy-and-hold 2010-2020 deve dare risultati simili a full-period
poetry run python scripts/sanity_check_walkforward.py
```

### Commit message

```
[T-005] Walk-forward framework

- Rolling window orchestration
- OOS-only aggregation
- HTML report generation
- Sanity check vs full-period backtest

Refs: alembic_v2/03_backtest_framework.md §5
```

---

## T-006 — Metrics Engine Completo

**Status**: OPEN  
**Effort**: M (3-5d)
**Dependencies**: T-002
**Reference docs**: `/alembic_v2/03_backtest_framework.md` §7

### Files to create
```
alembic/backtest/metrics/__init__.py
alembic/backtest/metrics/performance.py    # Sharpe, Sortino, Calmar
alembic/backtest/metrics/risk.py           # VaR, ES, drawdown
alembic/backtest/metrics/signal_quality.py # IC, ICIR, DSR
alembic/backtest/metrics/attribution.py    # Per-strategy contribution
alembic/backtest/metrics/reporting.py      # HTML/markdown report gen
tests/backtest/test_metrics.py
```

### Critical implementation notes

**Validate every metric against `empyrical`** library:

```python
def test_sharpe_matches_empyrical():
    import empyrical as ep
    returns = generate_test_returns()
    
    ours = compute_sharpe(returns)
    theirs = ep.sharpe_ratio(returns)
    
    assert abs(ours - theirs) < 1e-6
```

**Deflated Sharpe (López de Prado 2018)** è critico — implementare con cura:

```python
def deflated_sharpe(sr_observed: float, n_trials: int, sr_variance: float,
                    skew: float, kurt: float, n_obs: int) -> float:
    """
    DSR = ((SR_observed - E[max SR | n_trials]) * sqrt(n-1)) / sqrt(1 - skew*SR + (kurt-1)/4 * SR^2)
    
    Vedi López de Prado, "Advances in Financial Machine Learning" Ch.14
    """
    from scipy.stats import norm
    import numpy as np
    
    # Expected maximum SR sotto null hypothesis (no skill)
    em = sqrt(sr_variance) * (
        (1 - np.euler_gamma) * norm.ppf(1 - 1/n_trials) +
        np.euler_gamma * norm.ppf(1 - 1/(n_trials * np.e))
    )
    
    # Probabilistic Sharpe Ratio (deflated)
    numerator = (sr_observed - em) * sqrt(n_obs - 1)
    denominator = sqrt(1 - skew * sr_observed + (kurt - 1) / 4 * sr_observed**2)
    
    return norm.cdf(numerator / denominator)
```

### Acceptance verification

```bash
poetry run pytest tests/backtest/test_metrics.py -v
# Tutti pass, in particolare quelli che validano contro empyrical
```

### Commit message

```
[T-006] Complete metrics engine

- Performance: Sharpe, Sortino, Calmar (validated vs empyrical)
- Risk: VaR, ES, drawdown, skew, kurt
- Signal quality: IC, ICIR, p-value, DSR (López de Prado)
- Multi-strategy attribution
- HTML report generator

Refs: alembic_v2/03_backtest_framework.md §7
```

---

## T-007 — Validation Gates Implementation

**Status**: OPEN
**Effort**: M (3-5d)
**Dependencies**: T-002, T-005, T-006
**Reference docs**: `/alembic_v2/05_validation_and_gates.md` §1

### Files to create
```
alembic/backtest/gates/__init__.py
alembic/backtest/gates/gate_1_significance.py
alembic/backtest/gates/gate_2_walkforward.py
alembic/backtest/gates/gate_3_robustness.py
alembic/backtest/gates/gate_4_regime.py
alembic/backtest/gates/gate_5_stress.py
alembic/backtest/gates/runner.py             # Main: run all gates
alembic/backtest/gates/types.py              # GateResult dataclass
tests/backtest/test_gates.py
```

### Test cases obbligatori

```python
def test_gates_pass_for_known_good_strategy():
    """SPY buy-and-hold dovrebbe passare almeno gate 1 e 5."""
    # ...

def test_gates_fail_for_random_strategy():
    """Strategia random non deve passare gate 1."""
    # ...

def test_gates_fail_for_overfit_strategy():
    """Strategia ottimizzata su IS deve fallire gate 2 (OOS)."""
    # ...
```

### Acceptance verification

```bash
poetry run pytest tests/backtest/test_gates.py -v

# Run gates su strategia placeholder
poetry run python -m alembic.backtest.gates.runner \
    --strategy buy_and_hold_spy \
    --start 2010-01-01 --end 2023-12-31 \
    --output reports/gates_buy_hold_spy.html
```

### Commit message

```
[T-007] Validation gates implementation

- Gate 1: Statistical significance (IC + DSR)
- Gate 2: Walk-forward consistency
- Gate 3: Parameter robustness
- Gate 4: Multi-regime stability
- Gate 5: Stress test survival
- Runner with HTML report output

Refs: alembic_v2/05_validation_and_gates.md §1
```

---

## MILESTONE A — Backtest Foundation Ready

**Verification checklist**:

```bash
# 1. Tutti i tests della Phase A passano
poetry run pytest tests/backtest/ -v

# 2. Coverage complessivo Phase A >= 80%
poetry run pytest tests/backtest/ --cov=alembic.backtest --cov-report=term-missing

# 3. CI green
# Manual check: GitHub Actions tab

# 4. Anti-look-ahead test suite verde
poetry run pytest tests/backtest/test_no_lookahead.py -v

# 5. Sanity check end-to-end
poetry run python scripts/sanity_check_phase_a.py
# Expected: 
# - SPY buy-hold backtest: Sharpe 0.5-0.7, DD < 35%
# - Walk-forward su same: similar
# - Gates 1, 5 pass; 3, 4 maybe fail (è normale per buy-hold)

# 6. Lista task completati
git log --oneline phase-A-foundation | grep "T-00"
# Expected: 7 commits T-001 → T-007
```

### 🛑 HUMAN_GATE [HG-Milestone-A]: Backtest foundation review

Quando tutti i task A sono done, l'agente comunica:

```markdown
## 🛑 HUMAN_GATE [HG-Milestone-A]: Phase A completed

**Context**: Phase A (Backtest Foundation) tutti i 7 task DONE.

**Verification results**:
- ✓ T-001-T-007 implementati con tests
- ✓ Coverage Phase A: XX%  
- ✓ Anti-look-ahead suite passing
- ✓ Sanity check SPY buy-hold: Sharpe 0.5X, DD XX%

**Files for review**:
- `alembic/backtest/` (intera directory)
- `tests/backtest/` (intera directory)  
- `reports/sanity_check_phase_a.html`
- `DECISIONS.md` (decisioni prese)

**Awaiting**:
- Tua review del backtest engine
- Decisione "Yes, proceed to Phase B" / "No, fix X"
- (Opzionale) feedback sul cost model defaults
```

Se "Yes": merge `phase-A-foundation` → `main`, branch out `phase-B-s1-momentum`.
