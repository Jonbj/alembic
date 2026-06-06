# Contributing to Alembic

This guide is for developers adding new strategies, workers, or connectors to the system.

---

## Table of Contents

1. [Development Environment](#1-development-environment)
2. [Project Architecture Quick Reference](#2-project-architecture-quick-reference)
3. [Adding a New Strategy](#3-adding-a-new-strategy)
4. [Adding a New Celery Worker](#4-adding-a-new-celery-worker)
5. [Adding a New News Connector](#5-adding-a-new-news-connector)
6. [Adding a New API Endpoint](#6-adding-a-new-api-endpoint)
7. [Testing Conventions](#7-testing-conventions)
8. [Code Style](#8-code-style)

---

## 1. Development Environment

### Prerequisites

- Docker + Docker Compose
- Python 3.11+
- Node.js 20+ (frontend only)
- API keys: `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, LLM keys (see `.env.example`)

### Start the full stack

```bash
cp .env.example .env          # fill in your API keys
docker compose up -d          # starts postgres, redis, api, worker, beat, frontend
```

### Run tests

```bash
pytest tests/ -x -q           # all tests
pytest tests/workers/ -x -q   # workers only
```

All 1700+ tests must pass before opening a PR. CI blocks on any failure.

### Frontend development (hot reload)

```bash
cd frontend
npm install
npm run dev                   # Vite dev server on :5173 (proxies API to :8001)
```

---

## 2. Project Architecture Quick Reference

```
News sources → Redis queue → SentimentWorker → Redis/PG signals
                                                       │
                                              ExecutionWorker (every 15 min)
                                                       │
                                            Alpaca Paper/Live API
```

**Key constraint**: LLMs are **never called in the execution hot path**. Signals are pre-computed and cached in Redis with a 4-hour TTL. The execution worker reads from cache only.

**Config**: all runtime parameters live in `config/trading.yaml`. Workers read this file at task start — changes take effect on the next invocation without a restart.

---

## 3. Adding a New Strategy

Each strategy lives in `src/strategies/sN/` and follows a fixed interface.

### Step 1 — Create the package

```
src/strategies/s5/
  __init__.py        # package docstring describing the strategy
  config.py          # dataclass with all tunable parameters
  signal.py          # signal generation logic
  strategy.py        # BacktestOrchestrator-compatible class
  backtest.py        # CLI entry point for running the backtest
```

### Step 2 — Implement the strategy class

```python
# src/strategies/s5/strategy.py
class MyNewStrategy:
    """S5: brief description.

    Args:
        config: S5Config with all parameters.
    """
    def __init__(self, config: S5Config):
        self.config = config

    def generate_signals(self, snapshot: MarketSnapshot) -> list[Order]:
        """Return orders for this bar. Called by BacktestOrchestrator."""
        ...
```

The `generate_signals` method receives a `MarketSnapshot` (current prices, open positions, sentiment signals from Redis) and returns a list of `Order` objects. It must never call an LLM directly — read pre-computed signals from `snapshot.signals`.

### Step 3 — Register in `config/strategies.yaml`

```yaml
strategies:
  s5:
    enabled: false          # false until all gates pass
    allocation_pct: 0.0
    note: "R&D sleeve — gates not yet run"
```

### Step 4 — Run validation gates

All five gates must pass before a strategy enters the live portfolio:

| Gate | Test | Pass criterion |
|------|------|----------------|
| 1 — Code quality | Code review, deterministic backtest | No look-ahead, reproducible |
| 2 — Statistical significance | IC p-value | p < 0.05 |
| 3 — Walk-forward OOS | IC on 3+ OOS windows | Mean IC > 0.05 |
| 4 — Parameter robustness | ±20% parameter sensitivity | Edge persists |
| 5 — Cost drag | Gross alpha vs transaction costs | Costs < 50% of gross alpha |

Run gates via: `pytest tests/strategies/s5/ -v`

### Step 5 — Add to Portfolio Orchestrator (only after all gates pass)

Edit `src/portfolio/combiner.py` to include the new strategy's signal weight.

---

## 4. Adding a New Celery Worker

### Step 1 — Implement the task

Workers live in `src/workers/`. Each task is a Celery task decorated with `@app.task`:

```python
# src/workers/my_worker.py
"""MyWorker — brief description of what this task does.

Detailed docstring: what data it reads, what it writes, side effects.
"""
from src.workers.celery_app import app

@app.task(name="src.workers.my_worker.run_my_worker")
def run_my_worker() -> dict:
    """Task entry point. Returns a result dict for Celery task result tracking."""
    ...
    return {"processed": n, "status": "ok"}
```

**Pattern**: always return a dict with at least a `processed` or `status` key. This makes Celery Flower monitoring useful.

### Step 2 — Register in beat schedule

Edit `src/workers/celery_app.py`:

```python
app.conf.beat_schedule = {
    ...
    "my-worker": {
        "task": "src.workers.my_worker.run_my_worker",
        "schedule": crontab(hour=22, minute=30),
    },
}
```

### Step 3 — Write tests

```python
# tests/workers/test_my_worker.py
"""Tests for run_my_worker."""
from unittest.mock import patch, MagicMock
from src.workers.my_worker import run_my_worker

class TestMyWorker:
    def test_returns_processed_count(self):
        with patch("src.workers.my_worker.PostgreSQLStore") as mock_pg:
            mock_pg.return_value.fetch_something.return_value = [...]
            result = run_my_worker()
        assert result["processed"] == expected
```

### Step 4 — Add to `docs/ARCHITECTURE.md`

Add a row to the §2.7 Workers table and update the beat schedule table.

---

## 5. Adding a New News Connector

Connectors live in `src/connectors/`. Each connector produces `NewsItem` objects and pushes them to the Redis queue.

### Interface

```python
# src/connectors/my_source.py
"""MySource connector — brief description.

Rate limits, authentication method, data quality notes.
"""
from src.models.news import NewsItem

class MySourceConnector:
    """Fetches news from MySource API."""

    def fetch_recent(self, symbols: list[str], since: datetime) -> list[NewsItem]:
        """Fetch articles published after `since` for the given symbols."""
        ...
```

### Registration

1. Add to `src/workers/ingestion.py` alongside the existing GDELT/MarketAux/Alpaca calls
2. Add API credentials to `.env.example` and `src/config.py`
3. Add to `config/trading.yaml` under `news_sources:`
4. Write tests in `tests/connectors/test_my_source.py`

---

## 6. Adding a New API Endpoint

### Step 1 — Choose the right router

| Domain | File |
|--------|------|
| Trades, analytics, decisions | `src/api/routes/trading.py` |
| Signals | `src/api/routes/signals.py` |
| Admin, kill-switch, mode | `src/api/routes/admin.py` |
| Config read/write | `src/api/routes/config_routes.py` |
| New domain | Create `src/api/routes/my_domain.py` and register in `src/api/main.py` |

### Step 2 — Write the endpoint

```python
@router.get("/my-endpoint")
def get_something(
    pg: Annotated[object, Depends(get_pg_store)],
    days: int = Query(default=7, ge=1, le=90),
) -> list[dict]:
    """One-line description of what this returns.

    Longer explanation if the semantics are non-obvious.
    """
    return pg.fetch_something(days=days)
```

FastAPI automatically generates OpenAPI docs from the function signature and docstring. Always add a docstring — it appears in `/docs` (Swagger UI).

**Route ordering**: specific paths (`/trades/summary`, `/trades/analytics/*`) must be declared **before** parameterised paths (`/trades/{id}`). FastAPI matches routes in declaration order.

### Step 3 — Add to `docs/API.md`

Add a new section with: endpoint URL, method, auth requirement, query params, response schema, and an example response JSON.

---

## 7. Testing Conventions

### File placement

```
tests/
  workers/       → Celery task tests
  api/           → FastAPI endpoint tests (use TestClient)
  store/         → Redis/PG store method tests
  strategies/    → Strategy unit + integration tests
  connectors/    → Connector tests (mock HTTP responses with responses library)
```

### Mock pattern for store dependencies

```python
from unittest.mock import MagicMock
from src.store.pg_store import PostgreSQLStore
from src.store.redis_store import RedisStore

def _make_pg():
    pg = MagicMock(spec=PostgreSQLStore)
    pg.fetch_trades.return_value = []
    return pg

def _make_redis():
    redis = MagicMock(spec=RedisStore)
    redis.get_feedback_entry_threshold.return_value = None
    redis.get_feedback_regime_scale.return_value = None
    return redis
```

Using `spec=` prevents tests from silently passing when a method is renamed or removed.

### What to test

- **Happy path**: correct inputs → correct output
- **Empty/zero case**: no data → returns empty list, not exception
- **Error isolation**: store raises exception → task logs warning and continues
- **Redis fallback**: Redis unavailable → falls back to module constant, does not crash

---

## 8. Code Style

- **Python 3.11+** — use `X | Y` union types, `match` statements where appropriate
- **No synchronous LLM calls in workers** — all LLM inference through `run_inference()` in `sentiment.py`
- **No bare `except:`** — always catch specific exceptions or at minimum `Exception as e` and log
- **Docstrings**: every public function, class, and module must have a docstring. One-liners are fine for obvious utilities.
- **Comments**: only when the *why* is non-obvious. Never comment what the code does — use descriptive names instead.
- **Type hints**: all function signatures must be fully typed. Run `mypy src/` to check.
- **Secrets**: never hardcode API keys. All credentials via environment variables accessed through `src/config.py`.

### Linting and formatting

```bash
ruff check src/ tests/          # linter
ruff format src/ tests/         # formatter (replaces black)
mypy src/ --ignore-missing-imports
```

All three must pass cleanly before opening a PR.
