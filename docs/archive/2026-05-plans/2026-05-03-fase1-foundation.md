# LLM Trading System — Fase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Alpha Miner foundation: data ingestion connectors → ensemble LLM sentiment pipeline (3 models + FinBERT fallback) → Redis/PostgreSQL signal store → QuantConnect Lean custom feed → Performance Worker (observational IC tracking + daily Telegram report).

**Architecture:** Monolite modulare Python. Celery workers computano segnali LLM offline su batch di notizie, scrivono in Redis (hot, TTL 4h) e PostgreSQL (audit). QuantConnect Lean legge segnali pre-calcolati via `LLMSignalData` PythonData custom feed. FastAPI espone un control plane HTTP + kill-switch. Performance Worker misura IC dei segnali vs rendimenti reali (sola lettura in Fase 1 — nessun auto-update pesi).

**Tech Stack:** Python 3.11+, FastAPI 0.115+, Celery 5.4+, Redis 7, PostgreSQL 16, Pydantic v2, transformers 4.40+ (FinBERT), numpy, scipy, yfinance, aiohttp, feedparser, python-telegram-bot 20+, bleach, pytest 8+, pytest-asyncio, httpx, python-dotenv.

**Scope note:** Questo piano copre solo Fase 1. Fasi 2–4 avranno piani separati che dipendono da questo come prerequisito.

---

## File Structure

```
trading/
├── pyproject.toml
├── docker-compose.yml
├── .env.example
├── config/
│   ├── connectors.yaml
│   ├── workers.yaml
│   └── trading.yaml
├── migrations/
│   └── 001_initial.sql
├── src/
│   ├── config.py                    # load .env, parse YAML configs
│   ├── text/
│   │   └── sanitizer.py             # NFKC, bleach, invisible chars, homoglyph, truncate
│   ├── models/
│   │   ├── news.py                  # NewsItem dataclass
│   │   ├── signals.py               # SentimentResult, RegimeResult
│   │   └── performance.py           # PerformanceReport, PostMortem
│   ├── connectors/
│   │   ├── base.py                  # NewsConnector ABC
│   │   ├── deduplicator.py          # Redis hash-based dedup
│   │   ├── rss.py                   # RSSConnector
│   │   ├── gdelt.py                 # GDELTConnector
│   │   └── sec_edgar.py             # SECEdgarConnector
│   ├── llm/
│   │   ├── client.py                # LLMClient ABC
│   │   ├── opus.py                  # OpusClient (claude cli)
│   │   ├── qwen35.py                # Qwen35Client (claude cli)
│   │   ├── deepseek.py              # DeepseekClient (claude cli)
│   │   ├── finbert.py               # FinBERT fallback, entropic mapping
│   │   └── ensemble.py              # EnsembleAggregator, Consensus Gate
│   ├── store/
│   │   ├── redis_store.py           # signal write/read, kill-switch, divergence log
│   │   └── pg_store.py              # insert signals, bulk insert, query for IC
│   ├── api/
│   │   ├── main.py                  # FastAPI app, lifespan
│   │   ├── auth.py                  # X-API-Key dependency
│   │   └── routes/
│   │       ├── signals.py           # GET /api/signals/{symbol}
│   │       ├── admin.py             # POST /api/admin/mode, /killswitch
│   │       └── performance.py       # GET /api/performance, /api/weights
│   ├── workers/
│   │   ├── celery_app.py            # Celery app + beat schedule
│   │   ├── sentiment.py             # SentimentWorker Celery task
│   │   └── performance.py           # PerformanceWorker Celery task
│   ├── performance/
│   │   ├── ic.py                    # composite IC, ICIR, Newey-West
│   │   ├── weights.py               # compute_purified_icir, compute_new_weights
│   │   ├── drift.py                 # compute_psi, CUSUM, circuit breakers
│   │   ├── postmortem.py            # should_trigger_postmortem, diagnose
│   │   └── threshold.py             # bucket IC analysis, suggestion logic
│   └── notifications/
│       └── telegram.py              # send_alert, format_performance_report
├── quantconnect/
│   ├── signal_data.py               # LLMSignalData PythonData feed
│   └── intraday_strategy.py         # Intraday 1h strategy + risk manager
└── tests/
    ├── conftest.py
    ├── text/test_sanitizer.py
    ├── models/test_models.py
    ├── connectors/test_rss.py
    ├── connectors/test_gdelt.py
    ├── llm/test_ensemble.py
    ├── llm/test_finbert.py
    ├── store/test_redis_store.py
    ├── store/test_pg_store.py
    ├── api/test_api.py
    └── performance/
        ├── test_ic.py
        ├── test_weights.py
        ├── test_drift.py
        └── test_postmortem.py
```

---

### Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `tests/conftest.py`
- Create: all `__init__.py` stubs

- [ ] **Step 1: Write the failing test**

```python
# tests/test_imports.py
def test_src_importable():
    import src.config
    import src.models.news
    import src.models.signals
    import src.models.performance
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_imports.py -v
```
Expected: `ModuleNotFoundError: No module named 'src'`

- [ ] **Step 3: Create pyproject.toml**

```toml
# pyproject.toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "trading"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "celery[redis]>=5.4",
    "redis>=5.0",
    "psycopg2-binary>=2.9",
    "sqlalchemy>=2.0",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
    "python-dotenv>=1.0",
    "aiohttp>=3.9",
    "feedparser>=6.0",
    "bleach>=6.1",
    "transformers>=4.40",
    "torch>=2.2",
    "numpy>=1.26",
    "scipy>=1.13",
    "yfinance>=0.2.38",
    "python-telegram-bot>=20.0",
    "httpx>=0.27",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-mock>=3.14",
    "httpx>=0.27",
]

[tool.setuptools.packages.find]
where = ["."]
include = ["src*"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 4: Create directory structure + __init__.py files**

```bash
mkdir -p src/{text,models,connectors,llm,store,api/routes,workers,performance,notifications}
mkdir -p quantconnect tests/{text,models,connectors,llm,store,api,performance}
touch src/__init__.py src/text/__init__.py src/models/__init__.py
touch src/connectors/__init__.py src/llm/__init__.py src/store/__init__.py
touch src/api/__init__.py src/api/routes/__init__.py
touch src/workers/__init__.py src/performance/__init__.py src/notifications/__init__.py
touch quantconnect/__init__.py
touch tests/__init__.py tests/text/__init__.py tests/models/__init__.py
touch tests/connectors/__init__.py tests/llm/__init__.py tests/store/__init__.py
touch tests/api/__init__.py tests/performance/__init__.py
```

- [ ] **Step 5: Create docker-compose.yml**

```yaml
# docker-compose.yml
version: "3.9"
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: trading
      POSTGRES_USER: trading
      POSTGRES_PASSWORD: trading
    ports: ["5432:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  api:
    build: .
    command: uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
    env_file: .env
    ports: ["8000:8000"]
    depends_on: [postgres, redis]

  worker:
    build: .
    command: celery -A src.workers.celery_app worker --loglevel=info
    env_file: .env
    depends_on: [postgres, redis]

  beat:
    build: .
    command: celery -A src.workers.celery_app beat --loglevel=info
    env_file: .env
    depends_on: [postgres, redis]

volumes:
  pgdata:
```

- [ ] **Step 6: Create .env.example**

```bash
# .env.example
DATABASE_URL=postgresql://trading:trading@localhost:5432/trading
REDIS_URL=redis://localhost:6379/0
ADMIN_API_KEY=change-me-in-production

# LLM (Claude CLI — must be authenticated via `claude auth`)
CLAUDE_CLI_PATH=claude
LLM_DAILY_BUDGET_USD=5.00
LLM_TIMEOUT_SECONDS=30

# Connectors
NEWSAPI_KEY=
FRED_API_KEY=
DEEPL_API_KEY=

# Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

- [ ] **Step 7: Create tests/conftest.py**

```python
# tests/conftest.py
import pytest

@pytest.fixture
def sample_news_text():
    return "Apple Inc. reported record quarterly earnings of $1.2B, beating analyst estimates."

@pytest.fixture
def sample_scores():
    return [0.6, 0.5, -0.2, 0.8, -0.1, 0.4, 0.7, -0.3, 0.2, 0.5]

@pytest.fixture
def sample_returns():
    return [0.02, 0.01, -0.015, 0.03, -0.005, 0.01, 0.025, -0.02, 0.005, 0.015]
```

- [ ] **Step 8: Install deps and run test**

```bash
pip install -e ".[dev]"
pytest tests/test_imports.py -v
```
Expected: FAIL (src.config doesn't exist yet — that's fine, we'll fix in Task 2)

- [ ] **Step 9: Commit**

```bash
git init
git add pyproject.toml docker-compose.yml .env.example tests/conftest.py
git add src/ quantconnect/ tests/
git commit -m "feat: project scaffold — directories, deps, docker-compose"
```

---

### Task 2: Core Data Models

**Files:**
- Create: `src/models/news.py`
- Create: `src/models/signals.py`
- Create: `src/models/performance.py`
- Create: `src/config.py`
- Test: `tests/models/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/models/test_models.py
from datetime import datetime, timezone
from uuid import uuid4
from src.models.news import NewsItem
from src.models.signals import SentimentResult
from src.models.performance import PostMortem, PerformanceReport

def test_news_item_creation():
    item = NewsItem(
        id="abc123",
        source="reuters",
        timestamp=datetime.now(timezone.utc),
        title="Fed raises rates",
        body="The Federal Reserve raised interest rates by 25bp.",
        url="https://reuters.com/article/123",
        language="en",
        asset_tags=["SPY", "QQQ"],
    )
    assert item.source == "reuters"
    assert "SPY" in item.asset_tags

def test_sentiment_result_score_bounds():
    result = SentimentResult(
        symbol="AAPL",
        polarity=0.7,
        confidence=0.85,
        score=0.595,
        reasoning="Strong earnings beat.",
        source_ids=["news-1"],
        generated_at=datetime.now(timezone.utc),
        model_id="ensemble:opus+qwen3.5+deepseek",
        worker_version="1.0.0",
        fallback_used=False,
        worker_type="ensemble_llm",
    )
    assert -1.0 <= result.score <= 1.0
    assert result.fallback_used is False

def test_sentiment_result_rejects_out_of_bounds():
    import pytest
    with pytest.raises(Exception):
        SentimentResult(
            symbol="AAPL", polarity=1.5, confidence=0.5, score=0.5,
            reasoning="", source_ids=[], generated_at=datetime.now(timezone.utc),
            model_id="test", worker_version="1.0", fallback_used=False,
            worker_type="ensemble_llm",
        )

def test_postmortem_diagnosis_enum():
    pm = PostMortem(
        trade_id=uuid4(),
        symbol="AAPL",
        loss_pct=0.035,
        signal_score=0.65,
        signal_confidence=0.8,
        ensemble_std=0.1,
        regime_at_trade="risk_on",
        reasoning_summary="Bull case cited strong iPhone demand...",
        diagnosis="low_confidence_passed",
    )
    assert pm.diagnosis in PostMortem.VALID_DIAGNOSES
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/models/test_models.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create src/models/news.py**

```python
# src/models/news.py
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class NewsItem:
    id: str
    source: str
    timestamp: datetime
    title: str
    body: str
    url: str
    language: str
    asset_tags: list[str] = field(default_factory=list)
```

- [ ] **Step 4: Create src/models/signals.py**

```python
# src/models/signals.py
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

class SentimentResult(BaseModel):
    symbol: str
    polarity: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    score: float = Field(ge=-1.0, le=1.0)
    reasoning: str
    source_ids: list[str]
    generated_at: datetime
    model_id: str
    worker_version: str
    fallback_used: bool
    worker_type: Literal["ensemble_llm", "single_llm", "finbert"]

class RegimeResult(BaseModel):
    label: Literal["risk_on", "risk_off", "high_vol", "trending", "ranging", "uncertain"]
    confidence: float = Field(ge=0.0, le=1.0)
    key_factors: list[str]
    valid_until: datetime
    position_multiplier: float

    MULTIPLIERS: dict[str, float] = {
        "risk_on": 1.0, "trending": 0.8, "ranging": 0.6,
        "high_vol": 0.5, "risk_off": 0.3, "uncertain": 0.3,
    }

    model_config = {"arbitrary_types_allowed": True}
```

- [ ] **Step 5: Create src/models/performance.py**

```python
# src/models/performance.py
from datetime import date, datetime
from uuid import UUID
from pydantic import BaseModel, field_validator

class PostMortem(BaseModel):
    trade_id: UUID
    symbol: str
    loss_pct: float
    signal_score: float
    signal_confidence: float
    ensemble_std: float
    regime_at_trade: str
    reasoning_summary: str
    diagnosis: str

    VALID_DIAGNOSES: frozenset[str] = frozenset({
        "low_confidence_passed", "ensemble_divergence_ignored", "regime_mismatch",
        "news_staleness", "market_gap", "stop_too_tight",
        "correlated_portfolio_loss", "model_drift_active",
        "threshold_boundary", "unknown",
    })

    @field_validator("diagnosis")
    @classmethod
    def validate_diagnosis(cls, v: str) -> str:
        valid = {
            "low_confidence_passed", "ensemble_divergence_ignored", "regime_mismatch",
            "news_staleness", "market_gap", "stop_too_tight",
            "correlated_portfolio_loss", "model_drift_active",
            "threshold_boundary", "unknown",
        }
        if v not in valid:
            raise ValueError(f"diagnosis must be one of {valid}, got {v!r}")
        return v

    model_config = {"arbitrary_types_allowed": True}

class PerformanceReport(BaseModel):
    period_start: date
    period_end: date
    overall_ic: float
    icir: float
    hit_rate: float
    model_ic: dict[str, float]
    model_icir: dict[str, float]
    recommended_weights: dict[str, float]
    weight_change_applied: bool
    threshold_analysis: dict[str, float]
    threshold_suggestion: float | None
    drift_alerts: list[str]
    post_mortems: list[PostMortem]
    generated_at: datetime
    report_version: str
```

- [ ] **Step 6: Create src/config.py**

```python
# src/config.py
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL: str = os.environ["DATABASE_URL"]
REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
ADMIN_API_KEY: str = os.environ["ADMIN_API_KEY"]

CLAUDE_CLI_PATH: str = os.environ.get("CLAUDE_CLI_PATH", "claude")
LLM_DAILY_BUDGET_USD: float = float(os.environ.get("LLM_DAILY_BUDGET_USD", "5.00"))
LLM_TIMEOUT_SECONDS: int = int(os.environ.get("LLM_TIMEOUT_SECONDS", "30"))

TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.environ.get("TELEGRAM_CHAT_ID", "")

SIGNAL_MAX_AGE_MIN: int = int(os.environ.get("SIGNAL_MAX_AGE_MIN", "30"))
WORKER_VERSION: str = "1.0.0"
```

- [ ] **Step 7: Run test to verify it passes**

```bash
pytest tests/models/test_models.py -v
```
Expected: 4 PASSED

- [ ] **Step 8: Commit**

```bash
git add src/models/ src/config.py tests/models/
git commit -m "feat: core data models — NewsItem, SentimentResult, PostMortem, PerformanceReport"
```

---

### Task 3: Text Sanitizer

**Files:**
- Create: `src/text/sanitizer.py`
- Test: `tests/text/test_sanitizer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/text/test_sanitizer.py
import pytest
from src.text.sanitizer import sanitize, verify_ticker_ascii, TickerHomoglyphError

def test_nfkc_normalization():
    # Full-width latin letters should be normalized
    text = "Ａｐｐｌｅ reported earnings"
    result = sanitize(text)
    assert "Ａｐｐｌｅ" not in result
    assert "Apple" in result

def test_html_stripped():
    text = "<b>Apple</b> reported <script>alert(1)</script> earnings"
    result = sanitize(text)
    assert "<b>" not in result
    assert "<script>" not in result
    assert "Apple" in result
    assert "earnings" in result

def test_invisible_chars_removed():
    # Zero-width space U+200B
    text = "Buy​APPL​stock"
    result = sanitize(text)
    assert "​" not in result
    assert "APPL" in result

def test_truncation():
    long_text = "A" * 20000
    result = sanitize(long_text)
    assert len(result) <= 16000

def test_ticker_homoglyph_raises():
    # Cyrillic А looks like Latin A
    text = "Buy АPPL stock"  # first char is Cyrillic А (U+0410)
    with pytest.raises(TickerHomoglyphError):
        verify_ticker_ascii(text)

def test_clean_text_passes():
    text = "Buy AAPL stock — strong earnings beat estimates by 15%."
    result = sanitize(text)
    assert result == "Buy AAPL stock — strong earnings beat estimates by 15%."
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/text/test_sanitizer.py -v
```
Expected: `ModuleNotFoundError: No module named 'src.text.sanitizer'`

- [ ] **Step 3: Implement src/text/sanitizer.py**

```python
# src/text/sanitizer.py
import re
import unicodedata
import bleach

MAX_CHARS = 16_000

# Zero-width, invisible formatting, soft-hyphen, variation selectors
_INVISIBLE_PATTERN = re.compile(
    r"[​-‍⁠﻿­͏឴឵"
    r"᠋-᠍️؀-؅؜۝܏"
    r"࣢᠎  ‪- ⁠-⁯]+"
)

# Detects mixed-script tokens that look like tickers (Latin + Cyrillic/Greek)
_HOMOGLYPH_PATTERN = re.compile(
    r"\b(?:[А-Яа-яΑ-Ωα-ωА-ЯА-яёЁЀ-ӿ][A-Z0-9]{1,4}"
    r"|[A-Z][А-Яа-яΑ-Ωα-ωЀ-ӿ][A-Z0-9]{0,3})\b"
)


class TickerHomoglyphError(ValueError):
    pass


def verify_ticker_ascii(text: str) -> None:
    match = _HOMOGLYPH_PATTERN.search(text)
    if match:
        raise TickerHomoglyphError(
            f"Possible ticker homoglyph attack: {match.group()!r} at pos {match.start()}"
        )


def sanitize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = bleach.clean(text, tags=[], strip=True)
    text = _INVISIBLE_PATTERN.sub("", text)
    text = text[:MAX_CHARS]
    verify_ticker_ascii(text)
    return text
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/text/test_sanitizer.py -v
```
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/text/sanitizer.py tests/text/test_sanitizer.py
git commit -m "feat: text sanitizer — NFKC, HTML strip, invisible chars, ticker homoglyph detection"
```

---

### Task 4: NewsConnector ABC + Redis Deduplicator

**Files:**
- Create: `src/connectors/base.py`
- Create: `src/connectors/deduplicator.py`
- Test: `tests/connectors/test_deduplicator.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/connectors/test_deduplicator.py
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from src.models.news import NewsItem
from src.connectors.deduplicator import Deduplicator, compute_dedup_hash

def make_item(title: str, body: str) -> NewsItem:
    return NewsItem(
        id="x", source="test", timestamp=datetime.now(timezone.utc),
        title=title, body=body, url="http://test.com", language="en",
        asset_tags=["AAPL"],
    )

def test_hash_deterministic():
    item = make_item("Fed raises rates", "The Fed raised rates by 25bp.")
    h1 = compute_dedup_hash(item)
    h2 = compute_dedup_hash(item)
    assert h1 == h2

def test_hash_differs_on_content():
    a = make_item("Fed raises rates", "body A")
    b = make_item("Fed raises rates", "body B")
    assert compute_dedup_hash(a) != compute_dedup_hash(b)

def test_deduplicator_first_seen_returns_false():
    mock_redis = MagicMock()
    mock_redis.set.return_value = True   # SET NX succeeded = first time
    dedup = Deduplicator(mock_redis)
    item = make_item("title", "body")
    assert dedup.is_duplicate(item) is False

def test_deduplicator_second_seen_returns_true():
    mock_redis = MagicMock()
    mock_redis.set.return_value = None   # SET NX failed = already exists
    dedup = Deduplicator(mock_redis)
    item = make_item("title", "body")
    assert dedup.is_duplicate(item) is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/connectors/test_deduplicator.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create src/connectors/base.py**

```python
# src/connectors/base.py
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from src.models.news import NewsItem

class NewsConnector(ABC):
    @abstractmethod
    async def fetch(self) -> AsyncIterator[NewsItem]:
        """Yield NewsItem objects. Items are already sanitized (body = sanitize(raw))."""
        ...
```

- [ ] **Step 4: Create src/connectors/deduplicator.py**

```python
# src/connectors/deduplicator.py
import hashlib
import unicodedata
from redis import Redis
from src.models.news import NewsItem

_DEDUP_TTL_SECONDS = 2 * 3600  # 2 hours


def compute_dedup_hash(item: NewsItem) -> str:
    norm_title = unicodedata.normalize("NFKC", item.title).lower().strip()
    norm_body  = unicodedata.normalize("NFKC", item.body[:500]).lower().strip()
    return hashlib.sha256(f"{norm_title}|{norm_body}".encode()).hexdigest()


class Deduplicator:
    def __init__(self, redis: Redis):
        self._r = redis

    def is_duplicate(self, item: NewsItem) -> bool:
        key = f"dedup:{compute_dedup_hash(item)}"
        # SET NX returns True on first insert, None if key exists
        result = self._r.set(key, 1, ex=_DEDUP_TTL_SECONDS, nx=True)
        return result is None
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/connectors/test_deduplicator.py -v
```
Expected: 4 PASSED

- [ ] **Step 6: Commit**

```bash
git add src/connectors/base.py src/connectors/deduplicator.py tests/connectors/test_deduplicator.py
git commit -m "feat: NewsConnector ABC + Redis deduplicator (SHA-256, 2h TTL)"
```

---

### Task 5: RSSConnector

**Files:**
- Create: `src/connectors/rss.py`
- Create: `config/connectors.yaml`
- Test: `tests/connectors/test_rss.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/connectors/test_rss.py
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timezone
from src.connectors.rss import RSSConnector

SAMPLE_FEED = {
    "entries": [
        {
            "id": "http://reuters.com/1",
            "title": "Fed raises rates by 25bp",
            "summary": "The Federal Reserve raised interest rates by 25 basis points.",
            "link": "http://reuters.com/1",
            "published_parsed": (2026, 5, 3, 10, 0, 0, 5, 123, 0),
            "tags": [{"term": "ECONOMY"}],
        }
    ]
}

@pytest.mark.asyncio
async def test_rss_yields_news_items():
    connector = RSSConnector(
        feed_url="http://feeds.reuters.com/reuters/businessNews",
        source_name="reuters",
        asset_tags=["SPY"],
    )
    with patch("feedparser.parse", return_value=SAMPLE_FEED):
        items = []
        async for item in connector.fetch():
            items.append(item)
    assert len(items) == 1
    assert items[0].source == "reuters"
    assert items[0].language == "en"
    assert "SPY" in items[0].asset_tags

@pytest.mark.asyncio
async def test_rss_skips_empty_body():
    connector = RSSConnector(
        feed_url="http://example.com/rss",
        source_name="test",
        asset_tags=[],
    )
    empty_feed = {"entries": [{"id": "1", "title": "Title", "summary": "",
                               "link": "http://x.com", "published_parsed": None}]}
    with patch("feedparser.parse", return_value=empty_feed):
        items = [item async for item in connector.fetch()]
    assert len(items) == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/connectors/test_rss.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create src/connectors/rss.py**

```python
# src/connectors/rss.py
import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from time import struct_time
import feedparser
from src.connectors.base import NewsConnector
from src.models.news import NewsItem
from src.text.sanitizer import sanitize

class RSSConnector(NewsConnector):
    def __init__(self, feed_url: str, source_name: str, asset_tags: list[str]):
        self.feed_url = feed_url
        self.source_name = source_name
        self.asset_tags = asset_tags

    async def fetch(self) -> AsyncIterator[NewsItem]:
        loop = asyncio.get_event_loop()
        feed = await loop.run_in_executor(None, feedparser.parse, self.feed_url)
        for entry in feed.get("entries", []):
            body = entry.get("summary", "") or entry.get("content", [{}])[0].get("value", "")
            if not body.strip():
                continue
            try:
                clean_body = sanitize(body)
                clean_title = sanitize(entry.get("title", ""))
            except ValueError:
                continue  # homoglyph attack — skip item

            ts = entry.get("published_parsed")
            if ts and isinstance(ts, struct_time):
                timestamp = datetime(*ts[:6], tzinfo=timezone.utc)
            else:
                timestamp = datetime.now(timezone.utc)

            yield NewsItem(
                id=entry.get("id", entry.get("link", "")),
                source=self.source_name,
                timestamp=timestamp,
                title=clean_title,
                body=clean_body,
                url=entry.get("link", ""),
                language="en",
                asset_tags=self.asset_tags,
            )
```

- [ ] **Step 4: Create config/connectors.yaml**

```yaml
# config/connectors.yaml
rss_feeds:
  - url: "https://feeds.reuters.com/reuters/businessNews"
    source: "reuters"
    asset_tags: ["SPY", "QQQ"]
    poll_interval_seconds: 60

  - url: "https://feeds.marketwatch.com/marketwatch/topstories/"
    source: "marketwatch"
    asset_tags: ["SPY"]
    poll_interval_seconds: 60

  - url: "https://www.cnbc.com/id/100003114/device/rss/rss.html"
    source: "cnbc"
    asset_tags: ["SPY", "QQQ", "DIA"]
    poll_interval_seconds: 60

gdelt:
  poll_interval_seconds: 900
  max_articles_per_poll: 50

sec_edgar:
  form_types: ["8-K", "10-Q", "10-K"]
  poll_interval_seconds: 300
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/connectors/test_rss.py -v
```
Expected: 2 PASSED

- [ ] **Step 6: Commit**

```bash
git add src/connectors/rss.py config/connectors.yaml tests/connectors/test_rss.py
git commit -m "feat: RSSConnector with sanitization + connectors.yaml config"
```

---

### Task 6: GDELTConnector + SECEdgarConnector

**Files:**
- Create: `src/connectors/gdelt.py`
- Create: `src/connectors/sec_edgar.py`
- Test: `tests/connectors/test_gdelt.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/connectors/test_gdelt.py
import pytest
from unittest.mock import patch, AsyncMock
from src.connectors.gdelt import GDELTConnector

SAMPLE_GDELT_RESPONSE = {
    "articles": [
        {
            "url": "https://example.com/article",
            "title": "Fed raises rates",
            "seendate": "20260503T100000Z",
            "sourcecountry": "United States",
            "language": "English",
            "domain": "reuters.com",
        }
    ]
}

@pytest.mark.asyncio
async def test_gdelt_yields_items():
    connector = GDELTConnector(query="Federal Reserve interest rates", asset_tags=["SPY"])
    mock_response = AsyncMock()
    mock_response.json = AsyncMock(return_value=SAMPLE_GDELT_RESPONSE)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession.get", return_value=mock_response):
        items = [item async for item in connector.fetch()]

    assert len(items) == 1
    assert items[0].source == "gdelt"

@pytest.mark.asyncio
async def test_gdelt_empty_response():
    connector = GDELTConnector(query="test", asset_tags=[])
    mock_response = AsyncMock()
    mock_response.json = AsyncMock(return_value={"articles": []})
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession.get", return_value=mock_response):
        items = [item async for item in connector.fetch()]
    assert items == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/connectors/test_gdelt.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create src/connectors/gdelt.py**

```python
# src/connectors/gdelt.py
from collections.abc import AsyncIterator
from datetime import datetime, timezone
import aiohttp
from src.connectors.base import NewsConnector
from src.models.news import NewsItem
from src.text.sanitizer import sanitize

_GDELT_DOC2_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


class GDELTConnector(NewsConnector):
    def __init__(self, query: str, asset_tags: list[str], max_records: int = 50):
        self.query = query
        self.asset_tags = asset_tags
        self.max_records = max_records

    async def fetch(self) -> AsyncIterator[NewsItem]:
        params = {
            "query": self.query,
            "mode": "artlist",
            "maxrecords": self.max_records,
            "format": "json",
            "timespan": "15min",
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(_GDELT_DOC2_URL, params=params) as resp:
                data = await resp.json(content_type=None)

        for article in data.get("articles", []):
            title = article.get("title", "")
            if not title:
                continue
            try:
                clean_title = sanitize(title)
            except ValueError:
                continue

            raw_date = article.get("seendate", "")
            try:
                ts = datetime.strptime(raw_date, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                ts = datetime.now(timezone.utc)

            yield NewsItem(
                id=article.get("url", ""),
                source="gdelt",
                timestamp=ts,
                title=clean_title,
                body=clean_title,   # GDELT artlist provides title only; body = title as proxy
                url=article.get("url", ""),
                language="en",
                asset_tags=self.asset_tags,
            )
```

- [ ] **Step 4: Create src/connectors/sec_edgar.py**

```python
# src/connectors/sec_edgar.py
from collections.abc import AsyncIterator
from datetime import datetime, timezone
import aiohttp
from src.connectors.base import NewsConnector
from src.models.news import NewsItem
from src.text.sanitizer import sanitize

_EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"


class SECEdgarConnector(NewsConnector):
    def __init__(self, form_types: list[str] | None = None):
        self.form_types = form_types or ["8-K", "10-Q", "10-K"]

    async def fetch(self) -> AsyncIterator[NewsItem]:
        forms_q = " OR ".join(f'"{f}"' for f in self.form_types)
        params = {"q": forms_q, "dateRange": "custom", "startdt": "2026-05-03", "hits.hits.total.value": 20}
        async with aiohttp.ClientSession() as session:
            async with session.get(_EDGAR_SEARCH_URL, params=params) as resp:
                if resp.status != 200:
                    return
                data = await resp.json(content_type=None)

        for hit in data.get("hits", {}).get("hits", []):
            src = hit.get("_source", {})
            title = src.get("display_names", [""])[0] + " — " + src.get("form_type", "")
            body = src.get("period_of_report", "") + " " + src.get("entity_name", "")
            try:
                clean_title = sanitize(title)
                clean_body = sanitize(body)
            except ValueError:
                continue

            raw_date = src.get("file_date", "")
            try:
                ts = datetime.strptime(raw_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                ts = datetime.now(timezone.utc)

            ticker = src.get("ticker_symbol", "")
            yield NewsItem(
                id=src.get("id", ""),
                source="sec_edgar",
                timestamp=ts,
                title=clean_title,
                body=clean_body,
                url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={src.get('entity_id','')}",
                language="en",
                asset_tags=[ticker] if ticker else [],
            )
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/connectors/ -v
```
Expected: 6 PASSED

- [ ] **Step 6: Commit**

```bash
git add src/connectors/gdelt.py src/connectors/sec_edgar.py tests/connectors/test_gdelt.py
git commit -m "feat: GDELTConnector + SECEdgarConnector"
```

---

### Task 7: Database Migrations

**Files:**
- Create: `migrations/001_initial.sql`
- Create: `migrations/run_migrations.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/store/test_migrations.py
import psycopg2
import pytest
import os

@pytest.fixture
def pg_conn():
    url = os.environ.get("DATABASE_URL", "postgresql://trading:trading@localhost:5432/trading")
    conn = psycopg2.connect(url)
    conn.autocommit = True
    yield conn
    conn.close()

def test_all_tables_exist(pg_conn):
    with pg_conn.cursor() as cur:
        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
        """)
        tables = {row[0] for row in cur.fetchall()}
    assert "sentiment_signals" in tables
    assert "regime_signals" in tables
    assert "audit_log" in tables
    assert "performance_metrics" in tables
    assert "model_weights" in tables

def test_enums_exist(pg_conn):
    with pg_conn.cursor() as cur:
        cur.execute("SELECT typname FROM pg_type WHERE typcategory = 'E'")
        enums = {row[0] for row in cur.fetchall()}
    assert "worker_type_enum" in enums
    assert "regime_label_enum" in enums
    assert "audit_action_enum" in enums
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/store/test_migrations.py -v
```
Expected: FAIL (tables don't exist yet)

- [ ] **Step 3: Create migrations/001_initial.sql**

```sql
-- migrations/001_initial.sql

-- ENUMs
CREATE TYPE worker_type_enum AS ENUM ('ensemble_llm', 'single_llm', 'finbert');
CREATE TYPE regime_label_enum AS ENUM ('risk_on', 'risk_off', 'high_vol', 'trending', 'ranging', 'uncertain');
CREATE TYPE audit_action_enum AS ENUM (
    'order_placed', 'order_rejected', 'mode_changed',
    'killswitch', 'extreme_score_approval', 'extreme_score_rejected',
    'worker_degraded', 'budget_alert'
);

-- Sentiment signals
CREATE TABLE sentiment_signals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol          VARCHAR(20) NOT NULL,
    generated_at    TIMESTAMPTZ NOT NULL,
    polarity        FLOAT NOT NULL CHECK (polarity BETWEEN -1.0 AND 1.0),
    confidence      FLOAT NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
    score           FLOAT NOT NULL CHECK (score BETWEEN -1.0 AND 1.0),
    source_ids      TEXT[],
    reasoning       TEXT,
    worker_type     worker_type_enum NOT NULL,
    model_id        VARCHAR(100) NOT NULL,
    worker_version  VARCHAR(20) NOT NULL,
    fallback_used   BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX idx_sentiment_symbol_time ON sentiment_signals (symbol, generated_at DESC);
CREATE INDEX idx_sentiment_time_brin ON sentiment_signals USING BRIN (generated_at);
CREATE INDEX idx_sentiment_fallback ON sentiment_signals (generated_at) WHERE fallback_used = TRUE;

-- Regime signals
CREATE TABLE regime_signals (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    generated_at        TIMESTAMPTZ NOT NULL,
    label               regime_label_enum NOT NULL,
    confidence          FLOAT NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
    key_factors         TEXT[],
    valid_until         TIMESTAMPTZ NOT NULL,
    position_multiplier FLOAT NOT NULL,
    model_id            VARCHAR(100) NOT NULL,
    worker_version      VARCHAR(20) NOT NULL
);
CREATE INDEX idx_regime_time ON regime_signals (generated_at DESC);

-- Audit log
CREATE TABLE audit_log (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp     TIMESTAMPTZ NOT NULL DEFAULT now(),
    action        audit_action_enum NOT NULL,
    symbol        VARCHAR(20),
    quantity      FLOAT,
    price         FLOAT,
    signal_score  FLOAT,
    signal_id     UUID REFERENCES sentiment_signals(id),
    guardrail     VARCHAR(50),
    approved_by   VARCHAR(50),
    reason        TEXT
);
CREATE INDEX idx_audit_timestamp ON audit_log (timestamp DESC);
CREATE INDEX idx_audit_symbol ON audit_log (symbol, timestamp DESC) WHERE symbol IS NOT NULL;

-- Performance metrics
CREATE TABLE performance_metrics (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    period_start    DATE NOT NULL,
    period_end      DATE NOT NULL,
    model_id        VARCHAR(100),
    symbol          VARCHAR(20),
    regime          regime_label_enum,
    ic              FLOAT,
    icir            FLOAT,
    hit_rate        FLOAT,
    sample_count    INTEGER,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_perf_period ON performance_metrics (period_end DESC, model_id);

-- Model weights
CREATE TABLE model_weights (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    effective_from  TIMESTAMPTZ NOT NULL,
    model_id        VARCHAR(100) NOT NULL,
    weight          FLOAT NOT NULL CHECK (weight BETWEEN 0.0 AND 1.0),
    icir_basis      FLOAT,
    auto_applied    BOOLEAN NOT NULL DEFAULT FALSE,
    approved_by     VARCHAR(50),
    notes           TEXT
);
CREATE INDEX idx_weights_model_time ON model_weights (model_id, effective_from DESC);
```

- [ ] **Step 4: Create migrations/run_migrations.py**

```python
#!/usr/bin/env python3
# migrations/run_migrations.py
import sys
import psycopg2
from pathlib import Path
from src.config import DATABASE_URL

def run():
    sql = (Path(__file__).parent / "001_initial.sql").read_text()
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.close()
    print("Migrations applied successfully.")

if __name__ == "__main__":
    run()
```

- [ ] **Step 5: Run migration, then test**

```bash
docker-compose up -d postgres
python migrations/run_migrations.py
pytest tests/store/test_migrations.py -v
```
Expected: 2 PASSED

- [ ] **Step 6: Commit**

```bash
git add migrations/ tests/store/test_migrations.py
git commit -m "feat: PostgreSQL migrations — ENUMs, sentiment/regime/audit/performance/weights tables"
```

---

### Task 8: Redis Store

**Files:**
- Create: `src/store/redis_store.py`
- Test: `tests/store/test_redis_store.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/store/test_redis_store.py
import json
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from src.store.redis_store import RedisStore
from src.models.signals import SentimentResult

def make_result(symbol: str = "AAPL") -> SentimentResult:
    return SentimentResult(
        symbol=symbol, polarity=0.6, confidence=0.8, score=0.48,
        reasoning="Strong beat.", source_ids=["n1"],
        generated_at=datetime.now(timezone.utc),
        model_id="ensemble", worker_version="1.0",
        fallback_used=False, worker_type="ensemble_llm",
    )

def test_write_and_read_signal():
    mock_redis = MagicMock()
    stored = {}
    mock_redis.setex.side_effect = lambda k, ttl, v: stored.__setitem__(k, v)
    mock_redis.get.side_effect = lambda k: stored.get(k)

    store = RedisStore(mock_redis)
    result = make_result("AAPL")
    store.write_sentiment(result)

    retrieved = store.read_sentiment("AAPL")
    assert retrieved is not None
    assert retrieved.symbol == "AAPL"
    assert retrieved.score == pytest.approx(0.48)

def test_read_missing_returns_none():
    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    store = RedisStore(mock_redis)
    assert store.read_sentiment("MISSING") is None

def test_killswitch_activate():
    mock_redis = MagicMock()
    store = RedisStore(mock_redis)
    store.activate_killswitch()
    mock_redis.set.assert_called_once_with("killswitch_active", 1)

def test_killswitch_is_active():
    mock_redis = MagicMock()
    mock_redis.get.return_value = b"1"
    store = RedisStore(mock_redis)
    assert store.is_killswitch_active() is True

def test_killswitch_is_inactive():
    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    store = RedisStore(mock_redis)
    assert store.is_killswitch_active() is False

def test_log_divergence():
    mock_redis = MagicMock()
    store = RedisStore(mock_redis)
    store.log_divergence("AAPL", std=0.31, model_scores={"opus": 0.7, "qwen35": -0.1, "deepseek": 0.2})
    mock_redis.lpush.assert_called_once()
    mock_redis.expire.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/store/test_redis_store.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create src/store/redis_store.py**

```python
# src/store/redis_store.py
import json
from datetime import datetime, timezone
from redis import Redis
from src.models.signals import SentimentResult

_SENTIMENT_TTL = 4 * 3600       # 4 hours
_DIVERGENCE_TTL = 24 * 3600     # 24 hours


class RedisStore:
    def __init__(self, redis: Redis):
        self._r = redis

    # --- Sentiment signals ---

    def write_sentiment(self, result: SentimentResult) -> None:
        key = f"signal:{result.symbol}:sentiment"
        self._r.setex(key, _SENTIMENT_TTL, result.model_dump_json())

    def read_sentiment(self, symbol: str) -> SentimentResult | None:
        raw = self._r.get(f"signal:{symbol}:sentiment")
        if raw is None:
            return None
        return SentimentResult.model_validate_json(raw)

    # --- Kill-switch ---

    def activate_killswitch(self) -> None:
        self._r.set("killswitch_active", 1)

    def deactivate_killswitch(self) -> None:
        self._r.delete("killswitch_active")

    def is_killswitch_active(self) -> bool:
        return self._r.get("killswitch_active") is not None

    # --- Divergence log ---

    def log_divergence(self, symbol: str, std: float, model_scores: dict[str, float]) -> None:
        entry = json.dumps({
            "symbol": symbol,
            "std": std,
            "scores": model_scores,
            "ts": datetime.now(timezone.utc).isoformat(),
        })
        self._r.lpush("ensemble:divergence:log", entry)
        self._r.expire("ensemble:divergence:log", _DIVERGENCE_TTL)

    # --- Operating mode ---

    def get_mode(self) -> str:
        raw = self._r.get("system:mode")
        return raw.decode() if raw else "backtest"

    def set_mode(self, mode: str) -> None:
        self._r.set("system:mode", mode)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/store/test_redis_store.py -v
```
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/store/redis_store.py tests/store/test_redis_store.py
git commit -m "feat: RedisStore — sentiment read/write, kill-switch, divergence log, mode"
```

---

### Task 9: PostgreSQL Store

**Files:**
- Create: `src/store/pg_store.py`
- Test: `tests/store/test_pg_store.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/store/test_pg_store.py
import pytest
from unittest.mock import MagicMock, patch, call
from datetime import datetime, timezone, date
from uuid import uuid4
from src.store.pg_store import PgStore
from src.models.signals import SentimentResult

def make_result(symbol: str = "AAPL") -> SentimentResult:
    return SentimentResult(
        symbol=symbol, polarity=0.6, confidence=0.8, score=0.48,
        reasoning="Beat estimates.", source_ids=["n1"],
        generated_at=datetime.now(timezone.utc),
        model_id="ensemble", worker_version="1.0",
        fallback_used=False, worker_type="ensemble_llm",
    )

def test_insert_sentiment_calls_execute():
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    store = PgStore(mock_conn)
    result = make_result()
    store.insert_sentiment(result)

    mock_cursor.execute.assert_called_once()
    call_args = mock_cursor.execute.call_args
    sql = call_args[0][0]
    assert "INSERT INTO sentiment_signals" in sql

def test_bulk_insert_multiple_rows():
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    store = PgStore(mock_conn)
    results = [make_result(s) for s in ["AAPL", "MSFT", "GOOGL"]]
    store.bulk_insert_sentiment(results)

    assert mock_cursor.executemany.call_count == 1

def test_fetch_signals_for_ic_returns_rows():
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [
        (0.5, 0.02, "2026-05-01", "opus", False),
        (0.3, -0.01, "2026-05-02", "opus", False),
    ]
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    store = PgStore(mock_conn)
    rows = store.fetch_signals_for_ic(symbol="AAPL", days=30)
    assert len(rows) == 2
    assert rows[0][0] == 0.5
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/store/test_pg_store.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create src/store/pg_store.py**

```python
# src/store/pg_store.py
from datetime import datetime, timezone
from psycopg2.extras import execute_values
from src.models.signals import SentimentResult

_INSERT_SENTIMENT = """
    INSERT INTO sentiment_signals
        (symbol, generated_at, polarity, confidence, score, source_ids,
         reasoning, worker_type, model_id, worker_version, fallback_used)
    VALUES
        (%s, %s, %s, %s, %s, %s, %s, %s::worker_type_enum, %s, %s, %s)
"""

_FETCH_FOR_IC = """
    SELECT score, NULL as forward_return, generated_at, model_id, fallback_used
    FROM sentiment_signals
    WHERE symbol = %s
      AND generated_at >= now() - INTERVAL '%s days'
      AND fallback_used = FALSE
    ORDER BY generated_at ASC
"""


class PgStore:
    def __init__(self, conn):
        self._conn = conn

    def _row(self, r: SentimentResult) -> tuple:
        return (
            r.symbol, r.generated_at, r.polarity, r.confidence, r.score,
            r.source_ids, r.reasoning, r.worker_type, r.model_id,
            r.worker_version, r.fallback_used,
        )

    def insert_sentiment(self, result: SentimentResult) -> None:
        with self._conn.cursor() as cur:
            cur.execute(_INSERT_SENTIMENT, self._row(result))
        self._conn.commit()

    def bulk_insert_sentiment(self, results: list[SentimentResult]) -> None:
        with self._conn.cursor() as cur:
            cur.executemany(_INSERT_SENTIMENT, [self._row(r) for r in results])
        self._conn.commit()

    def fetch_signals_for_ic(self, symbol: str, days: int) -> list[tuple]:
        with self._conn.cursor() as cur:
            cur.execute(_FETCH_FOR_IC, (symbol, days))
            return cur.fetchall()

    def insert_model_weights(self, weights: dict[str, float], icir_basis: dict[str, float],
                              auto_applied: bool, approved_by: str = "auto") -> None:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        with self._conn.cursor() as cur:
            for model_id, weight in weights.items():
                cur.execute(
                    """INSERT INTO model_weights
                       (effective_from, model_id, weight, icir_basis, auto_applied, approved_by)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (now, model_id, weight, icir_basis.get(model_id), auto_applied, approved_by),
                )
        self._conn.commit()

    def insert_performance_metric(self, period_start, period_end, model_id,
                                   ic, icir, hit_rate, sample_count) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """INSERT INTO performance_metrics
                   (period_start, period_end, model_id, ic, icir, hit_rate, sample_count)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (period_start, period_end, model_id, ic, icir, hit_rate, sample_count),
            )
        self._conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/store/test_pg_store.py -v
```
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/store/pg_store.py tests/store/test_pg_store.py
git commit -m "feat: PgStore — insert/bulk sentiment, fetch for IC, model weights, performance metrics"
```

---

### Task 10: LLMClient ABC + 3 Claude CLI Clients

**Files:**
- Create: `src/llm/client.py`
- Create: `src/llm/opus.py`
- Create: `src/llm/qwen35.py`
- Create: `src/llm/deepseek.py`
- Test: `tests/llm/test_clients.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/llm/test_clients.py
import pytest
from unittest.mock import patch, MagicMock
from pydantic import BaseModel
from src.llm.opus import OpusClient

class SampleOutput(BaseModel):
    verdict: str
    score: float

@pytest.mark.asyncio
async def test_opus_client_parses_json_response():
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = '{"verdict": "bullish", "score": 0.72}'

    with patch("subprocess.run", return_value=mock_proc):
        client = OpusClient()
        result = await client.complete("Analyze AAPL", SampleOutput)

    assert result.verdict == "bullish"
    assert result.score == pytest.approx(0.72)

@pytest.mark.asyncio
async def test_opus_client_raises_on_nonzero_exit():
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stderr = "auth error"

    with patch("subprocess.run", return_value=mock_proc):
        client = OpusClient()
        with pytest.raises(RuntimeError, match="Claude CLI"):
            await client.complete("test", SampleOutput)

@pytest.mark.asyncio
async def test_client_retry_on_parse_failure():
    responses = [
        MagicMock(returncode=0, stdout="not valid json"),
        MagicMock(returncode=0, stdout='{"verdict": "bearish", "score": -0.3}'),
    ]
    call_count = 0
    def fake_run(*args, **kwargs):
        nonlocal call_count
        result = responses[call_count]
        call_count += 1
        return result

    with patch("subprocess.run", side_effect=fake_run):
        client = OpusClient()
        result = await client.complete("test", SampleOutput)
    assert result.verdict == "bearish"
    assert call_count == 2
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/llm/test_clients.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create src/llm/client.py**

```python
# src/llm/client.py
from abc import ABC, abstractmethod
from typing import TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

class LLMClient(ABC):
    model_id: str = ""
    timeout_seconds: int = 30
    max_retries: int = 2

    @abstractmethod
    async def complete(self, prompt: str, response_schema: type[T]) -> T:
        ...
```

- [ ] **Step 4: Create src/llm/opus.py**

```python
# src/llm/opus.py
import asyncio
import json
import subprocess
from typing import TypeVar
from pydantic import BaseModel, ValidationError
from src.llm.client import LLMClient
from src import config

T = TypeVar("T", bound=BaseModel)

class OpusClient(LLMClient):
    model_id = "opus"

    async def complete(self, prompt: str, response_schema: type[T]) -> T:
        loop = asyncio.get_event_loop()
        for attempt in range(self.max_retries + 1):
            result = await loop.run_in_executor(None, self._call_cli, prompt)
            try:
                # Extract JSON from the response (model may wrap it in text)
                raw = result.strip()
                start = raw.find("{")
                end = raw.rfind("}") + 1
                if start >= 0 and end > start:
                    raw = raw[start:end]
                return response_schema.model_validate_json(raw)
            except (ValidationError, json.JSONDecodeError, ValueError):
                if attempt == self.max_retries:
                    raise
        raise RuntimeError("Exhausted retries")  # unreachable

    def _call_cli(self, prompt: str) -> str:
        proc = subprocess.run(
            [config.CLAUDE_CLI_PATH, "--model", self.model_id, "--print"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=config.LLM_TIMEOUT_SECONDS,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"Claude CLI error (model={self.model_id}): {proc.stderr[:200]}")
        return proc.stdout
```

- [ ] **Step 5: Create src/llm/qwen35.py and src/llm/deepseek.py**

```python
# src/llm/qwen35.py
from src.llm.opus import OpusClient

class Qwen35Client(OpusClient):
    model_id = "qwen3.5:cloud"
```

```python
# src/llm/deepseek.py
from src.llm.opus import OpusClient

class DeepseekClient(OpusClient):
    model_id = "deepseek-v4-pro:cloud"
```

- [ ] **Step 6: Run test to verify it passes**

```bash
pytest tests/llm/test_clients.py -v
```
Expected: 3 PASSED

- [ ] **Step 7: Commit**

```bash
git add src/llm/client.py src/llm/opus.py src/llm/qwen35.py src/llm/deepseek.py tests/llm/test_clients.py
git commit -m "feat: LLMClient ABC + OpusClient/Qwen35Client/DeepseekClient (Claude CLI subprocess + retry)"
```

---

### Task 11: FinBERT Fallback (Entropic Confidence Mapping)

**Files:**
- Create: `src/llm/finbert.py`
- Test: `tests/llm/test_finbert.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/llm/test_finbert.py
import pytest
from unittest.mock import patch, MagicMock
from src.llm.finbert import FinBERTClient, entropic_confidence

def test_entropic_confidence_uniform():
    # Uniform distribution → max entropy → min confidence
    probs = [1/3, 1/3, 1/3]
    conf = entropic_confidence(probs)
    assert conf < 0.5

def test_entropic_confidence_peaked():
    # Peaked distribution → low entropy → high confidence
    probs = [0.95, 0.03, 0.02]
    conf = entropic_confidence(probs)
    assert conf > 0.7

def test_entropic_confidence_bounds():
    for probs in [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1/3, 1/3, 1/3]]:
        conf = entropic_confidence(probs)
        assert 0.0 <= conf <= 1.0

def test_finbert_positive_maps_to_positive_polarity():
    mock_pipeline = MagicMock(return_value=[[
        {"label": "positive", "score": 0.85},
        {"label": "neutral",  "score": 0.10},
        {"label": "negative", "score": 0.05},
    ]])
    with patch("src.llm.finbert.pipeline", return_value=mock_pipeline):
        client = FinBERTClient()
        result = client.analyze("Apple beats earnings estimates.")
    assert result.polarity > 0
    assert result.confidence > 0.5
    assert result.worker_type == "finbert"

def test_finbert_negative_maps_to_negative_polarity():
    mock_pipeline = MagicMock(return_value=[[
        {"label": "negative", "score": 0.88},
        {"label": "neutral",  "score": 0.09},
        {"label": "positive", "score": 0.03},
    ]])
    with patch("src.llm.finbert.pipeline", return_value=mock_pipeline):
        client = FinBERTClient()
        result = client.analyze("Mass layoffs announced.")
    assert result.polarity < 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/llm/test_finbert.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create src/llm/finbert.py**

```python
# src/llm/finbert.py
"""
FinBERT fallback with Approach 3 — entropic confidence mapping.

FinBERT outputs 3-class probabilities: positive, neutral, negative.
Confidence is derived from 1 - normalized_entropy, so a peaked distribution
→ high confidence, uniform distribution → low confidence (~0).
Polarity maps the positive/negative balance accounting for neutral dampening.
"""
import math
import numpy as np
from dataclasses import dataclass
from typing import Literal

_LABEL_SIGN = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}
_MODEL_NAME = "ProsusAI/finbert"
_PIPELINE: object = None  # lazy singleton


def entropic_confidence(probs: list[float]) -> float:
    """Confidence = 1 - H(p) / H_max where H_max = log2(n_classes)."""
    n = len(probs)
    h_max = math.log2(n)
    entropy = -sum(p * math.log2(p + 1e-12) for p in probs)
    return float(1.0 - entropy / h_max)


@dataclass
class FinBERTResult:
    polarity: float        # [-1, +1]
    confidence: float      # [0, 1] — entropic
    worker_type: Literal["finbert"] = "finbert"


class FinBERTClient:
    def __init__(self):
        self._pipe = None

    def _get_pipeline(self):
        if self._pipe is None:
            from transformers import pipeline  # lazy import — avoids slow load at startup
            self._pipe = pipeline(
                "text-classification",
                model=_MODEL_NAME,
                return_all_scores=True,
                device=-1,  # CPU
            )
        return self._pipe

    def analyze(self, text: str) -> FinBERTResult:
        pipe = self._get_pipeline()
        scores_list = pipe(text[:512])  # FinBERT max 512 tokens
        scores = {item["label"]: item["score"] for item in scores_list[0]}

        probs = [scores.get("positive", 0), scores.get("neutral", 0), scores.get("negative", 0)]
        confidence = entropic_confidence(probs)

        # Polarity: positive contribution - negative contribution, dampened by neutral
        polarity = (scores.get("positive", 0) - scores.get("negative", 0))
        polarity *= (1.0 - scores.get("neutral", 0))  # neutral dampens conviction
        polarity = max(-1.0, min(1.0, polarity))

        return FinBERTResult(polarity=polarity, confidence=confidence)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/llm/test_finbert.py -v
```
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/llm/finbert.py tests/llm/test_finbert.py
git commit -m "feat: FinBERT fallback with entropic confidence mapping (Approach 3)"
```

---

### Task 12: EnsembleAggregator (Consensus Gate)

**Files:**
- Create: `src/llm/ensemble.py`
- Test: `tests/llm/test_ensemble.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/llm/test_ensemble.py
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from src.llm.ensemble import EnsembleAggregator, ModelOutput

def make_output(polarity: float, confidence: float, model_id: str) -> ModelOutput:
    return ModelOutput(
        symbol="AAPL",
        polarity=polarity,
        confidence=confidence,
        reasoning="test reasoning",
        model_id=model_id,
    )

def test_consensus_below_threshold_aggregates():
    agg = EnsembleAggregator(divergence_threshold=0.25)
    outputs = [
        make_output(0.6, 0.85, "opus"),
        make_output(0.5, 0.80, "qwen35"),
        make_output(0.55, 0.75, "deepseek"),
    ]
    result = agg.aggregate(outputs)
    assert result is not None
    assert result.fallback_used is False
    assert result.polarity > 0
    # Confidence-weighted: (0.6*0.85 + 0.5*0.80 + 0.55*0.75) / (0.85+0.80+0.75)
    expected_polarity = (0.6*0.85 + 0.5*0.80 + 0.55*0.75) / (0.85 + 0.80 + 0.75)
    assert result.polarity == pytest.approx(expected_polarity, abs=0.01)

def test_divergence_above_threshold_returns_none():
    agg = EnsembleAggregator(divergence_threshold=0.25)
    outputs = [
        make_output(0.8, 0.9, "opus"),
        make_output(-0.7, 0.85, "qwen35"),
        make_output(0.1, 0.8, "deepseek"),
    ]
    result = agg.aggregate(outputs)
    assert result is None  # caller must use FinBERT fallback

def test_low_confidence_model_excluded():
    agg = EnsembleAggregator(divergence_threshold=0.25, min_confidence=0.4)
    outputs = [
        make_output(0.7, 0.85, "opus"),
        make_output(0.6, 0.80, "qwen35"),
        make_output(-0.5, 0.30, "deepseek"),   # below min_confidence — excluded
    ]
    result = agg.aggregate(outputs)
    assert result is not None
    assert result.polarity > 0  # deepseek's negative vote excluded

def test_compute_std():
    agg = EnsembleAggregator()
    outputs = [make_output(0.6, 0.8, "a"), make_output(0.5, 0.8, "b"), make_output(0.55, 0.8, "c")]
    import numpy as np
    polarities = [0.6, 0.5, 0.55]
    expected_std = float(np.std(polarities))
    assert agg._std(outputs) == pytest.approx(expected_std, abs=0.001)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/llm/test_ensemble.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create src/llm/ensemble.py**

```python
# src/llm/ensemble.py
import numpy as np
from dataclasses import dataclass
from datetime import datetime, timezone
from src import config

@dataclass
class ModelOutput:
    symbol: str
    polarity: float
    confidence: float
    reasoning: str
    model_id: str


@dataclass
class AggregatedResult:
    symbol: str
    polarity: float
    confidence: float
    reasoning: str          # from the highest-confidence model
    model_ids: list[str]
    ensemble_std: float
    fallback_used: bool = False


class EnsembleAggregator:
    def __init__(
        self,
        divergence_threshold: float = 0.25,
        min_confidence: float = 0.4,
    ):
        self.divergence_threshold = divergence_threshold
        self.min_confidence = min_confidence

    def _std(self, outputs: list[ModelOutput]) -> float:
        return float(np.std([o.polarity for o in outputs]))

    def aggregate(self, outputs: list[ModelOutput]) -> AggregatedResult | None:
        if not outputs:
            return None

        # Exclude models below minimum confidence
        eligible = [o for o in outputs if o.confidence >= self.min_confidence]
        if not eligible:
            return None

        std = self._std(eligible)
        if std >= self.divergence_threshold:
            return None  # divergence → caller falls back to FinBERT

        # Confidence-weighted average polarity
        total_conf = sum(o.confidence for o in eligible)
        weighted_polarity = sum(o.polarity * o.confidence for o in eligible) / total_conf
        mean_confidence = total_conf / len(eligible)

        # Reasoning from highest-confidence model
        best = max(eligible, key=lambda o: o.confidence)

        return AggregatedResult(
            symbol=eligible[0].symbol,
            polarity=max(-1.0, min(1.0, weighted_polarity)),
            confidence=mean_confidence,
            reasoning=best.reasoning,
            model_ids=[o.model_id for o in eligible],
            ensemble_std=std,
        )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/llm/test_ensemble.py -v
```
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/llm/ensemble.py tests/llm/test_ensemble.py
git commit -m "feat: EnsembleAggregator — Consensus Gate with divergence threshold + confidence filtering"
```

---

### Task 13: SentimentWorker (Celery Task)

**Files:**
- Create: `src/workers/celery_app.py`
- Create: `src/workers/sentiment.py`
- Create: `config/workers.yaml`
- Test: `tests/workers/test_sentiment_worker.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/workers/test_sentiment_worker.py
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone
from src.models.news import NewsItem
from src.models.signals import SentimentResult
from src.workers.sentiment import process_news_batch

def make_news(n: int = 3) -> list[NewsItem]:
    return [
        NewsItem(
            id=f"n{i}", source="reuters",
            timestamp=datetime.now(timezone.utc),
            title=f"News {i}: Apple Q{i} results", body=f"Apple reported earnings for Q{i}.",
            url=f"http://reuters.com/{i}", language="en", asset_tags=["AAPL"],
        )
        for i in range(n)
    ]

@pytest.mark.asyncio
async def test_process_batch_returns_sentiment_results():
    mock_ensemble_result = MagicMock()
    mock_ensemble_result.polarity = 0.6
    mock_ensemble_result.confidence = 0.8
    mock_ensemble_result.reasoning = "Strong earnings beat."
    mock_ensemble_result.model_ids = ["opus", "qwen35", "deepseek"]
    mock_ensemble_result.ensemble_std = 0.05

    mock_agg = MagicMock()
    mock_agg.aggregate.return_value = mock_ensemble_result

    mock_opus = AsyncMock()
    mock_opus.complete.return_value = MagicMock(polarity=0.6, confidence=0.85, reasoning="r1")
    mock_qwen = AsyncMock()
    mock_qwen.complete.return_value = MagicMock(polarity=0.55, confidence=0.80, reasoning="r2")
    mock_deepseek = AsyncMock()
    mock_deepseek.complete.return_value = MagicMock(polarity=0.65, confidence=0.78, reasoning="r3")

    news = make_news(2)
    results = await process_news_batch(
        news_items=news,
        clients=[mock_opus, mock_qwen, mock_deepseek],
        aggregator=mock_agg,
        finbert=None,
        redis_store=MagicMock(),
        pg_store=MagicMock(),
    )
    assert len(results) > 0
    for r in results:
        assert isinstance(r, SentimentResult)
        assert r.fallback_used is False

@pytest.mark.asyncio
async def test_process_batch_uses_finbert_on_divergence():
    mock_agg = MagicMock()
    mock_agg.aggregate.return_value = None  # divergence → None

    mock_finbert = MagicMock()
    mock_finbert.analyze.return_value = MagicMock(polarity=-0.3, confidence=0.65)

    mock_client = AsyncMock()
    mock_client.complete.return_value = MagicMock(polarity=0.7, confidence=0.8, reasoning="r")

    news = make_news(1)
    results = await process_news_batch(
        news_items=news,
        clients=[mock_client, mock_client, mock_client],
        aggregator=mock_agg,
        finbert=mock_finbert,
        redis_store=MagicMock(),
        pg_store=MagicMock(),
    )
    assert results[0].fallback_used is True
    assert results[0].worker_type == "finbert"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/workers/test_sentiment_worker.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create src/workers/celery_app.py**

```python
# src/workers/celery_app.py
from celery import Celery
from celery.schedules import crontab
from src import config

app = Celery("trading", broker=config.REDIS_URL, backend=config.REDIS_URL)
app.conf.task_serializer = "json"
app.conf.result_serializer = "json"
app.conf.accept_content = ["json"]
app.conf.timezone = "UTC"
app.conf.enable_utc = True

app.conf.beat_schedule = {
    # Sentiment Worker every 15 min during market hours (Mon-Fri 14:00-21:00 UTC = 9am-4pm ET)
    "sentiment-worker": {
        "task": "src.workers.sentiment.run_sentiment_worker",
        "schedule": crontab(minute="*/15", hour="14-21", day_of_week="1-5"),
    },
    # Performance daily report at 03:00 UTC
    "performance-daily": {
        "task": "src.workers.performance.run_daily_report",
        "schedule": crontab(hour=3, minute=0),
    },
    # Performance weekly weight suggestion on Mondays at 04:00 UTC
    "performance-weekly": {
        "task": "src.workers.performance.run_weekly_weights",
        "schedule": crontab(hour=4, minute=0, day_of_week=1),
    },
    # Drift detection every Sunday at 04:30 UTC
    "drift-detection": {
        "task": "src.workers.performance.run_drift_detection",
        "schedule": crontab(hour=4, minute=30, day_of_week=0),
    },
}

app.autodiscover_tasks(["src.workers"])
```

- [ ] **Step 4: Create src/workers/sentiment.py**

```python
# src/workers/sentiment.py
import asyncio
import logging
from datetime import datetime, timezone
from src import config
from src.models.news import NewsItem
from src.models.signals import SentimentResult
from src.llm.client import LLMClient
from src.llm.ensemble import EnsembleAggregator, ModelOutput
from src.llm.finbert import FinBERTClient
from src.store.redis_store import RedisStore
from src.store.pg_store import PgStore
from src.workers.celery_app import app

log = logging.getLogger(__name__)

_DK_COT_PROMPT = """You are a buy-side equity analyst. Analyze the following news item and provide a sentiment assessment.

Think step-by-step:
1. What does this mean for the company's revenue and cash flows?
2. How does this compare to competitor performance?
3. What is the bull case? What is the bear case?
4. What is your overall verdict?

News: {text}
Ticker: {symbol}

Respond ONLY with valid JSON matching this schema:
{{"polarity": <float -1.0 to 1.0>, "confidence": <float 0.0 to 1.0>, "reasoning": "<bull/bear analysis in one sentence>"}}"""


async def process_news_batch(
    news_items: list[NewsItem],
    clients: list[LLMClient],
    aggregator: EnsembleAggregator,
    finbert: FinBERTClient | None,
    redis_store: RedisStore,
    pg_store: PgStore,
) -> list[SentimentResult]:
    from pydantic import BaseModel

    class LLMSentimentOutput(BaseModel):
        polarity: float
        confidence: float
        reasoning: str

    results: list[SentimentResult] = []

    for item in news_items:
        symbol = item.asset_tags[0] if item.asset_tags else "UNKNOWN"
        prompt = _DK_COT_PROMPT.format(text=item.body[:2000], symbol=symbol)

        # Call all 3 models in parallel
        tasks = [client.complete(prompt, LLMSentimentOutput) for client in clients]
        raw_outputs = []
        for i, coro in enumerate(asyncio.as_completed(tasks)):
            try:
                out = await coro
                raw_outputs.append(ModelOutput(
                    symbol=symbol,
                    polarity=out.polarity,
                    confidence=out.confidence,
                    reasoning=out.reasoning,
                    model_id=clients[i].model_id,
                ))
            except Exception as e:
                log.warning("Client %d failed: %s", i, e)

        aggregated = aggregator.aggregate(raw_outputs) if raw_outputs else None

        if aggregated is None:
            # Divergence or all failed → FinBERT
            if finbert is None:
                continue
            fb = finbert.analyze(item.body[:512])
            result = SentimentResult(
                symbol=symbol,
                polarity=fb.polarity,
                confidence=fb.confidence,
                score=fb.polarity * fb.confidence,
                reasoning="FinBERT fallback",
                source_ids=[item.id],
                generated_at=datetime.now(timezone.utc),
                model_id="finbert",
                worker_version=config.WORKER_VERSION,
                fallback_used=True,
                worker_type="finbert",
            )
        else:
            score = aggregated.polarity * aggregated.confidence
            result = SentimentResult(
                symbol=symbol,
                polarity=aggregated.polarity,
                confidence=aggregated.confidence,
                score=max(-1.0, min(1.0, score)),
                reasoning=aggregated.reasoning,
                source_ids=[item.id],
                generated_at=datetime.now(timezone.utc),
                model_id=f"ensemble:{'+'.join(aggregated.model_ids)}",
                worker_version=config.WORKER_VERSION,
                fallback_used=False,
                worker_type="ensemble_llm",
            )

        redis_store.write_sentiment(result)
        pg_store.insert_sentiment(result)
        results.append(result)

    return results


@app.task(name="src.workers.sentiment.run_sentiment_worker")
def run_sentiment_worker():
    """Celery entry-point: pulls from Redis queue, runs sentiment pipeline."""
    from redis import Redis
    import psycopg2
    from src.llm.opus import OpusClient
    from src.llm.qwen35 import Qwen35Client
    from src.llm.deepseek import DeepseekClient

    redis = Redis.from_url(config.REDIS_URL)
    pg = psycopg2.connect(config.DATABASE_URL)

    clients = [OpusClient(), Qwen35Client(), DeepseekClient()]
    agg = EnsembleAggregator()
    finbert = FinBERTClient()
    redis_store = RedisStore(redis)
    pg_store = PgStore(pg)

    # Pull up to 10 items from Redis queue
    raw_items: list[NewsItem] = []
    for _ in range(10):
        item_json = redis.lpop("news:queue")
        if item_json is None:
            break
        import json
        d = json.loads(item_json)
        raw_items.append(NewsItem(**d))

    if not raw_items:
        return

    asyncio.run(process_news_batch(raw_items, clients, agg, finbert, redis_store, pg_store))
    pg.close()
```

- [ ] **Step 5: Create config/workers.yaml**

```yaml
# config/workers.yaml
sentiment_worker:
  batch_size: 10
  divergence_threshold: 0.25
  min_confidence: 0.4
  llm_timeout_seconds: 30
  max_retries: 2
  consecutive_fallback_alert_threshold: 3

performance_worker:
  min_samples_intraday: 300
  min_samples_swing_4h: 200
  min_samples_swing_1d: 150
  forward_return_window_intraday_hours: 4
  forward_return_window_swing_4h_hours: 24
  forward_return_window_swing_1d_hours: 72
  ic_smoothing_alpha: 0.25
  weight_floor: 0.10
  weight_cap: 0.70
  weight_max_delta: 0.10
  icir_auto_apply_threshold: 0.1
  report_version: "1.0"
```

- [ ] **Step 6: Run test to verify it passes**

```bash
pytest tests/workers/test_sentiment_worker.py -v
```
Expected: 2 PASSED

- [ ] **Step 7: Commit**

```bash
git add src/workers/ config/workers.yaml tests/workers/
git commit -m "feat: SentimentWorker — Celery task, DK-CoT prompt, ensemble + FinBERT fallback, Celery beat schedule"
```

---

### Task 14: FastAPI App + Auth + All Routes

**Files:**
- Create: `src/api/auth.py`
- Create: `src/api/main.py`
- Create: `src/api/routes/signals.py`
- Create: `src/api/routes/admin.py`
- Create: `src/api/routes/performance.py`
- Test: `tests/api/test_api.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_api.py
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport
from src.api.main import app, get_redis_store
from src.models.signals import SentimentResult

def make_result(symbol: str = "AAPL") -> SentimentResult:
    return SentimentResult(
        symbol=symbol, polarity=0.6, confidence=0.8, score=0.48,
        reasoning="Strong beat.", source_ids=["n1"],
        generated_at=datetime.now(timezone.utc),
        model_id="ensemble", worker_version="1.0",
        fallback_used=False, worker_type="ensemble_llm",
    )

@pytest.fixture
def mock_redis_store():
    store = MagicMock()
    store.read_sentiment.return_value = make_result("AAPL")
    store.is_killswitch_active.return_value = False
    store.get_mode.return_value = "backtest"
    return store

@pytest.mark.asyncio
async def test_get_signal_returns_sentiment(mock_redis_store):
    app.dependency_overrides[get_redis_store] = lambda: mock_redis_store
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/signals/AAPL")
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "AAPL"
    assert data["score"] == pytest.approx(0.48)
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_get_signal_404_when_missing(mock_redis_store):
    mock_redis_store.read_sentiment.return_value = None
    app.dependency_overrides[get_redis_store] = lambda: mock_redis_store
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/signals/UNKN")
    assert resp.status_code == 404
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_admin_mode_requires_api_key(mock_redis_store):
    app.dependency_overrides[get_redis_store] = lambda: mock_redis_store
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/admin/mode", json={"mode": "paper"})
    assert resp.status_code == 403
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_admin_mode_with_valid_key(mock_redis_store):
    import os
    os.environ["ADMIN_API_KEY"] = "test-key"
    app.dependency_overrides[get_redis_store] = lambda: mock_redis_store
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/admin/mode",
            json={"mode": "paper"},
            headers={"X-API-Key": "test-key"},
        )
    assert resp.status_code == 200
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

@pytest.mark.asyncio
async def test_killswitch_requires_api_key():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/admin/killswitch")
    assert resp.status_code == 403
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/api/test_api.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create src/api/auth.py**

```python
# src/api/auth.py
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader
from src import config

_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def require_api_key(key: str | None = Security(_header)) -> str:
    if key is None or key != config.ADMIN_API_KEY:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")
    return key
```

- [ ] **Step 4: Create src/api/routes/signals.py**

```python
# src/api/routes/signals.py
from fastapi import APIRouter, Depends, HTTPException
from src.store.redis_store import RedisStore
from src.api.main import get_redis_store

router = APIRouter(prefix="/api/signals")

@router.get("/{symbol}")
async def get_signal(symbol: str, store: RedisStore = Depends(get_redis_store)):
    result = store.read_sentiment(symbol.upper())
    if result is None:
        raise HTTPException(status_code=404, detail=f"No signal for {symbol}")
    return result.model_dump(mode="json")
```

- [ ] **Step 5: Create src/api/routes/admin.py**

```python
# src/api/routes/admin.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from src.api.auth import require_api_key
from src.store.redis_store import RedisStore
from src.api.main import get_redis_store

router = APIRouter(prefix="/api/admin")

_VALID_MODES = {"backtest", "paper", "semi_auto", "full_auto", "halted"}

class ModeRequest(BaseModel):
    mode: str

@router.post("/mode", dependencies=[Depends(require_api_key)])
async def set_mode(req: ModeRequest, store: RedisStore = Depends(get_redis_store)):
    if req.mode not in _VALID_MODES:
        from fastapi import HTTPException
        raise HTTPException(400, f"mode must be one of {_VALID_MODES}")
    store.set_mode(req.mode)
    return {"mode": req.mode, "status": "ok"}

@router.post("/killswitch", dependencies=[Depends(require_api_key)])
async def activate_killswitch(store: RedisStore = Depends(get_redis_store)):
    store.activate_killswitch()
    store.set_mode("halted")
    return {"killswitch": "activated", "mode": "halted"}
```

- [ ] **Step 6: Create src/api/routes/performance.py**

```python
# src/api/routes/performance.py
from fastapi import APIRouter, Depends, HTTPException
from src.api.auth import require_api_key
from src.api.main import get_redis_store

router = APIRouter(prefix="/api")

@router.get("/performance/latest")
async def get_latest_performance():
    # Reads from Redis key set by PerformanceWorker
    from redis import Redis
    from src import config
    r = Redis.from_url(config.REDIS_URL)
    raw = r.get("performance:latest_report")
    if raw is None:
        raise HTTPException(404, "No performance report available yet")
    import json
    return json.loads(raw)

@router.get("/weights/current")
async def get_current_weights():
    from redis import Redis
    from src import config
    r = Redis.from_url(config.REDIS_URL)
    raw = r.get("ensemble:weights:current")
    if raw is None:
        return {"weights": {"opus": 0.34, "qwen35": 0.33, "deepseek": 0.33}, "source": "default"}
    import json
    return json.loads(raw)

@router.post("/weights/approve", dependencies=[Depends(require_api_key)])
async def approve_weights(weights: dict[str, float]):
    from redis import Redis
    import json
    from src import config
    r = Redis.from_url(config.REDIS_URL)
    r.set("ensemble:weights:current", json.dumps({"weights": weights, "source": "manual_approval"}))
    return {"approved": weights}
```

- [ ] **Step 7: Create src/api/main.py**

```python
# src/api/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from redis import Redis
from src import config
from src.store.redis_store import RedisStore

_redis_client: Redis | None = None

def get_redis_store() -> RedisStore:
    return RedisStore(_redis_client)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis_client
    _redis_client = Redis.from_url(config.REDIS_URL)
    yield
    _redis_client.close()

app = FastAPI(title="LLM Trading Signal API", lifespan=lifespan)

from src.api.routes import signals, admin, performance  # noqa: E402
app.include_router(signals.router)
app.include_router(admin.router)
app.include_router(performance.router)

@app.get("/api/health")
async def health():
    return {"status": "ok", "mode": get_redis_store().get_mode()}
```

- [ ] **Step 8: Fix circular import in routes**

The routes import `get_redis_store` from `main.py`. Update `signals.py` to use `Annotated`:

```python
# src/api/routes/signals.py  (updated)
from fastapi import APIRouter, Depends, HTTPException
from typing import Annotated
from src.store.redis_store import RedisStore

router = APIRouter(prefix="/api/signals")

def _get_store():
    # Late import to avoid circular
    from src.api.main import get_redis_store
    return get_redis_store()

@router.get("/{symbol}")
async def get_signal(symbol: str, store: Annotated[RedisStore, Depends(_get_store)]):
    result = store.read_sentiment(symbol.upper())
    if result is None:
        raise HTTPException(status_code=404, detail=f"No signal for {symbol}")
    return result.model_dump(mode="json")
```

Apply same pattern to `admin.py`:
```python
# src/api/routes/admin.py  (updated)
from fastapi import APIRouter, Depends, HTTPException
from typing import Annotated
from pydantic import BaseModel
from src.api.auth import require_api_key
from src.store.redis_store import RedisStore

router = APIRouter(prefix="/api/admin")
_VALID_MODES = {"backtest", "paper", "semi_auto", "full_auto", "halted"}

def _get_store():
    from src.api.main import get_redis_store
    return get_redis_store()

class ModeRequest(BaseModel):
    mode: str

@router.post("/mode", dependencies=[Depends(require_api_key)])
async def set_mode(req: ModeRequest, store: Annotated[RedisStore, Depends(_get_store)]):
    if req.mode not in _VALID_MODES:
        raise HTTPException(400, f"mode must be one of {_VALID_MODES}")
    store.set_mode(req.mode)
    return {"mode": req.mode, "status": "ok"}

@router.post("/killswitch", dependencies=[Depends(require_api_key)])
async def activate_killswitch(store: Annotated[RedisStore, Depends(_get_store)]):
    store.activate_killswitch()
    store.set_mode("halted")
    return {"killswitch": "activated", "mode": "halted"}
```

- [ ] **Step 9: Run test to verify it passes**

```bash
pytest tests/api/test_api.py -v
```
Expected: 6 PASSED

- [ ] **Step 10: Commit**

```bash
git add src/api/ tests/api/
git commit -m "feat: FastAPI app — signal/admin/performance routes, X-API-Key auth, kill-switch endpoint"
```

---

*Tasks 15–25 continue in `2026-05-03-fase1-part2.md`*
