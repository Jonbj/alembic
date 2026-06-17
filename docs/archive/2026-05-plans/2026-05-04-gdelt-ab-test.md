# GDELT A/B Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone CLI script that fetches GDELT historical news, scores with FinBERT, and gates GDELT integration via `delta_Sharpe ≥ 0.10` vs buy-and-hold baseline.

**Architecture:** Four new files + one extended connector. Pure functions in `src/analysis/backtest.py` are TDD'd with synthetic data. FinBERT and GDELT calls are mocked in tests — no network or model download needed to run the test suite.

**Tech Stack:** yfinance (prices), transformers/torch (FinBERT), argparse (CLI), numpy/scipy (IC), tqdm (progress), aiohttp (GDELT), pytest/pytest-asyncio (tests).

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `requirements.txt` | Add yfinance, transformers, torch, tqdm |
| Create | `src/analysis/__init__.py` | Package marker |
| Create | `src/analysis/backtest.py` | `compute_sharpe`, `compute_signal_returns`, `run_ab_comparison`, `ABResult` |
| Create | `src/analysis/finbert.py` | `score_article`, `score_articles` (FinBERT singleton) |
| Modify | `src/connectors/gdelt.py` | Add `fetch_historical`, extract `_parse_articles` |
| Create | `tests/analysis/__init__.py` | Package marker |
| Create | `tests/analysis/test_backtest.py` | Unit tests for pure backtest functions |
| Create | `tests/analysis/test_finbert.py` | Unit tests for FinBERT scoring (mocked pipeline) |
| Create | `tests/connectors/test_gdelt_historical.py` | Tests for `fetch_historical` |
| Create | `scripts/__init__.py` | Makes scripts importable in tests |
| Create | `scripts/gdelt_ab_test.py` | CLI entry point + `run_ab_test` orchestration |
| Create | `tests/analysis/test_gdelt_ab_cli.py` | Integration tests with all external deps mocked |

---

## Task 1: Add Dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Update requirements.txt**

Replace the file contents with:

```
# LLM Trading System - Dependencies

# Core
pydantic>=2.0
numpy>=1.24
scipy>=1.10

# Database
psycopg2-binary>=2.9
redis>=5.0

# Async
asyncio>=3.4

# HTTP
httpx>=0.25
aiohttp>=3.9

# API
fastapi>=0.104
uvicorn>=0.24

# Worker
celery>=5.4

# Testing
pytest>=7.4
pytest-asyncio>=0.21

# Text processing
transformers>=4.40
torch>=2.0
tqdm>=4.66

# Finance
yfinance>=0.2.40
```

- [ ] **Step 2: Install new packages**

Run: `pip install yfinance transformers torch tqdm`

Verify:
```bash
python -c "import yfinance, transformers, torch, tqdm; print('OK')"
```
Expected output: `OK`

---

## Task 2: Pure Backtest Module (TDD)

**Files:**
- Create: `src/analysis/__init__.py` (empty)
- Create: `tests/analysis/__init__.py` (empty)
- Create: `tests/analysis/test_backtest.py`
- Create: `src/analysis/backtest.py`

- [ ] **Step 1: Create empty `__init__.py` files**

Create two empty files:
- `src/analysis/__init__.py`
- `tests/analysis/__init__.py`

- [ ] **Step 2: Write the failing tests**

Create `tests/analysis/test_backtest.py`:

```python
"""Tests for pure backtest functions."""
import numpy as np
import pytest

from src.analysis.backtest import ABResult, compute_sharpe, compute_signal_returns, run_ab_comparison


class TestComputeSharpe:
    def test_positive_mean_returns_positive_sharpe(self):
        returns = [0.001, 0.002, -0.001, 0.003, 0.001] * 50
        assert compute_sharpe(returns) > 0

    def test_zero_std_returns_zero(self):
        # Identical values → std=0 → no division, returns 0
        assert compute_sharpe([0.005] * 50) == 0.0

    def test_empty_returns_zero(self):
        assert compute_sharpe([]) == 0.0

    def test_single_element_returns_zero(self):
        assert compute_sharpe([0.01]) == 0.0

    def test_annualization_factor(self):
        returns = [0.001, -0.002, 0.003, -0.001, 0.002] * 20
        s252 = compute_sharpe(returns, annualization=252)
        s1 = compute_sharpe(returns, annualization=1)
        # s252 / s1 should equal sqrt(252)
        assert abs(s252 / s1 - 252 ** 0.5) < 1e-9


class TestComputeSignalReturns:
    def test_positive_score_goes_long(self):
        assert compute_signal_returns([0.5], [0.02]) == [0.02]

    def test_negative_score_goes_short(self):
        assert compute_signal_returns([-0.5], [0.02]) == [-0.02]

    def test_zero_score_neutral(self):
        assert compute_signal_returns([0.0], [0.02]) == [0.0]

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError, match="same length"):
            compute_signal_returns([0.5, 0.3], [0.02])

    def test_multiple_days(self):
        scores = [0.5, -0.3, 0.0, 0.1]
        fwd = [0.01, 0.02, -0.01, -0.03]
        assert compute_signal_returns(scores, fwd) == [0.01, -0.02, 0.0, -0.03]


class TestRunABComparison:
    def test_gate_passes_with_perfect_predictor(self):
        rng = np.random.default_rng(0)
        fwd = rng.normal(0, 0.01, 252).tolist()
        # Perfect predictor: score has same sign as forward return
        scores = [abs(f) if f > 0 else -abs(f) for f in fwd]
        result = run_ab_comparison(scores, fwd, n_articles=500, threshold=0.1)
        assert result.gate_passed

    def test_gate_fails_with_zero_scores(self):
        # All-zero scores → no GDELT edge → GDELT Sharpe = 0
        fwd = [0.001] * 252
        scores = [0.0] * 252
        result = run_ab_comparison(scores, fwd, n_articles=0, threshold=0.1)
        assert not result.gate_passed
        assert result.sharpe_gdelt == 0.0

    def test_result_fields_populated(self):
        fwd = [0.01, -0.02, 0.005, 0.015]
        scores = [0.5, -0.3, 0.0, 0.8]
        result = run_ab_comparison(scores, fwd, n_articles=10, threshold=0.1)
        assert isinstance(result, ABResult)
        assert result.n_signals == 10
        assert result.n_trading_days == 4
        assert result.coverage_pct == 75.0   # 3/4 non-zero
        assert isinstance(result.delta_sharpe, float)
        assert isinstance(result.composite_ic, float)

    def test_coverage_pct_all_zeros(self):
        result = run_ab_comparison([0.0] * 10, [0.01] * 10, n_articles=0)
        assert result.coverage_pct == 0.0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/analysis/test_backtest.py -v`

Expected: `ModuleNotFoundError: No module named 'src.analysis.backtest'`

- [ ] **Step 4: Create `src/analysis/backtest.py`**

```python
"""Pure backtest functions for GDELT A/B test."""

from dataclasses import dataclass

import numpy as np

from src.performance.ic import compute_composite_ic


@dataclass
class ABResult:
    """A/B comparison result between GDELT-driven and buy-and-hold strategies."""
    sharpe_baseline: float
    sharpe_gdelt: float
    delta_sharpe: float
    composite_ic: float
    coverage_pct: float
    n_signals: int
    n_trading_days: int
    gate_passed: bool


def compute_sharpe(returns: list[float], annualization: int = 252) -> float:
    """Annualized Sharpe ratio. Returns 0.0 for empty or zero-variance inputs."""
    arr = np.array(returns, dtype=float)
    if len(arr) < 2:
        return 0.0
    std = float(np.std(arr, ddof=1))
    if std == 0.0:
        return 0.0
    return float(np.mean(arr) / std * np.sqrt(annualization))


def compute_signal_returns(
    daily_scores: list[float],
    fwd_returns: list[float],
) -> list[float]:
    """Long if score>0, short if score<0, flat if score=0."""
    if len(daily_scores) != len(fwd_returns):
        raise ValueError("daily_scores and fwd_returns must have the same length")
    result = []
    for score, ret in zip(daily_scores, fwd_returns):
        if score > 0:
            result.append(ret)
        elif score < 0:
            result.append(-ret)
        else:
            result.append(0.0)
    return result


def run_ab_comparison(
    daily_scores: list[float],
    fwd_returns: list[float],
    n_articles: int,
    threshold: float = 0.10,
) -> ABResult:
    """Compare GDELT-driven strategy vs buy-and-hold. Gate: delta_Sharpe >= threshold."""
    gdelt_returns = compute_signal_returns(daily_scores, fwd_returns)
    sharpe_baseline = compute_sharpe(fwd_returns)
    sharpe_gdelt = compute_sharpe(gdelt_returns)
    delta_sharpe = sharpe_gdelt - sharpe_baseline

    active_idx = [i for i, s in enumerate(daily_scores) if s != 0.0]
    if active_idx:
        ic_result = compute_composite_ic(
            [daily_scores[i] for i in active_idx],
            [fwd_returns[i] for i in active_idx],
        )
        composite_ic = ic_result.composite_ic
    else:
        composite_ic = 0.0

    n_trading_days = len(daily_scores)
    covered = sum(1 for s in daily_scores if s != 0.0)
    coverage_pct = (covered / n_trading_days * 100.0) if n_trading_days > 0 else 0.0

    return ABResult(
        sharpe_baseline=sharpe_baseline,
        sharpe_gdelt=sharpe_gdelt,
        delta_sharpe=delta_sharpe,
        composite_ic=composite_ic,
        coverage_pct=coverage_pct,
        n_signals=n_articles,
        n_trading_days=n_trading_days,
        gate_passed=delta_sharpe >= threshold,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/analysis/test_backtest.py -v`

Expected: All 10 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/analysis/ tests/analysis/__init__.py tests/analysis/test_backtest.py requirements.txt
git commit -m "feat: add pure backtest module and dependencies for GDELT A/B test"
```

---

## Task 3: FinBERT Scoring Module (TDD)

**Files:**
- Create: `tests/analysis/test_finbert.py`
- Create: `src/analysis/finbert.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/analysis/test_finbert.py`:

```python
"""Tests for FinBERT scoring — all external calls mocked."""
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from src.models.news import NewsItem
from src.analysis.finbert import score_article, score_articles


def make_article(title: str, ts: datetime | None = None) -> NewsItem:
    ts = ts or datetime.now(timezone.utc)
    return NewsItem(id="test", source="gdelt", timestamp=ts, title=title, body=title)


class TestScoreArticle:
    def test_positive_article(self):
        mock_pipe = lambda text: [[
            {"label": "positive", "score": 0.80},
            {"label": "negative", "score": 0.05},
            {"label": "neutral",  "score": 0.15},
        ]]
        with patch("src.analysis.finbert._get_pipeline", return_value=mock_pipe):
            polarity, confidence = score_article("Earnings beat")
        assert abs(polarity - 0.75) < 1e-6    # 0.80 - 0.05
        assert abs(confidence - 0.85) < 1e-6  # 0.80 + 0.05

    def test_negative_article(self):
        mock_pipe = lambda text: [[
            {"label": "positive", "score": 0.05},
            {"label": "negative", "score": 0.85},
            {"label": "neutral",  "score": 0.10},
        ]]
        with patch("src.analysis.finbert._get_pipeline", return_value=mock_pipe):
            polarity, confidence = score_article("Bankruptcy filing")
        assert polarity < 0
        assert confidence > 0.8

    def test_neutral_article_low_confidence(self):
        mock_pipe = lambda text: [[
            {"label": "positive", "score": 0.05},
            {"label": "negative", "score": 0.05},
            {"label": "neutral",  "score": 0.90},
        ]]
        with patch("src.analysis.finbert._get_pipeline", return_value=mock_pipe):
            polarity, confidence = score_article("Annual meeting scheduled")
        assert abs(polarity) < 0.01
        assert confidence < 0.15


class TestScoreArticles:
    def test_score_formula_polarity_times_confidence(self):
        articles = [make_article("Test")]
        with patch("src.analysis.finbert.score_article", return_value=(0.6, 0.8)):
            results = score_articles(articles, min_confidence=0.0)
        assert len(results) == 1
        _, score = results[0]
        assert score == pytest.approx(0.6 * 0.8)

    def test_filters_below_min_confidence(self):
        articles = [make_article("High conf"), make_article("Low conf")]

        def mock_score(text):
            return (0.75, 0.85) if "High" in text else (0.0, 0.10)

        with patch("src.analysis.finbert.score_article", side_effect=mock_score):
            results = score_articles(articles, min_confidence=0.3)
        assert len(results) == 1
        assert results[0][1] == pytest.approx(0.75 * 0.85)

    def test_empty_list_returns_empty(self):
        assert score_articles([], min_confidence=0.3) == []

    def test_skips_article_with_no_text(self):
        article = NewsItem(id="x", source="gdelt", body="", title="")
        with patch("src.analysis.finbert.score_article") as mock_score:
            results = score_articles([article], min_confidence=0.0)
        mock_score.assert_not_called()
        assert results == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/analysis/test_finbert.py -v`

Expected: `ModuleNotFoundError: No module named 'src.analysis.finbert'`

- [ ] **Step 3: Create `src/analysis/finbert.py`**

```python
"""FinBERT scoring for news articles."""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.news import NewsItem

logger = logging.getLogger(__name__)

_pipeline = None


def _get_pipeline():
    """Lazy-load FinBERT pipeline once (singleton)."""
    global _pipeline
    if _pipeline is None:
        import torch
        from transformers import pipeline

        device = 0 if torch.cuda.is_available() else -1
        _pipeline = pipeline(
            "text-classification",
            model="ProsusAI/finbert",
            device=device,
            top_k=None,
        )
    return _pipeline


def score_article(text: str) -> tuple[float, float]:
    """Run FinBERT on text. Returns (polarity, confidence).

    polarity   = pos_prob - neg_prob   ∈ [-1, +1]
    confidence = pos_prob + neg_prob   ∈ [0, 1]   (= 1 - neutral_prob)
    """
    pipe = _get_pipeline()
    results = pipe(text[:512])
    probs = {r["label"]: r["score"] for r in results[0]}
    pos = probs.get("positive", 0.0)
    neg = probs.get("negative", 0.0)
    return pos - neg, pos + neg


def score_articles(
    articles: list[NewsItem],
    min_confidence: float = 0.3,
) -> list[tuple[date, float]]:
    """Score articles with FinBERT. Returns [(article_date, score)] for articles
    where FinBERT confidence >= min_confidence.

    score = polarity × confidence
    Articles with empty body and title are skipped.
    """
    results = []
    for article in articles:
        text = article.body or article.title
        if not text:
            continue
        try:
            polarity, confidence = score_article(text)
        except Exception as e:
            logger.warning("FinBERT failed for %s: %s", article.id, e)
            continue
        if confidence >= min_confidence:
            results.append((article.timestamp.date(), polarity * confidence))
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/analysis/test_finbert.py -v`

Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/analysis/finbert.py tests/analysis/test_finbert.py
git commit -m "feat: add FinBERT scoring module"
```

---

## Task 4: Extend GDELTConnector with `fetch_historical`

**Files:**
- Create: `tests/connectors/test_gdelt_historical.py`
- Modify: `src/connectors/gdelt.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/connectors/test_gdelt_historical.py`:

```python
"""Tests for GDELTConnector.fetch_historical."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.connectors.gdelt import GDELTConnector

SAMPLE_ARTICLE = {
    "url": "https://reuters.com/1",
    "title": "AAPL earnings beat",
    "seendate": "20240115T100000Z",
}


def make_mock_resp(articles: list[dict]) -> AsyncMock:
    resp = AsyncMock()
    resp.json = AsyncMock(return_value={"articles": articles})
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=None)
    return resp


@pytest.mark.asyncio
async def test_fetch_historical_yields_items():
    connector = GDELTConnector(query='"AAPL"', asset_tags=["AAPL"])
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 31, tzinfo=timezone.utc)

    with patch("aiohttp.ClientSession.get", return_value=make_mock_resp([SAMPLE_ARTICLE])):
        with patch("asyncio.sleep"):
            items = [item async for item in connector.fetch_historical(start, end)]

    assert len(items) == 1
    assert items[0].title == "AAPL earnings beat"
    assert items[0].source == "gdelt"


@pytest.mark.asyncio
async def test_fetch_historical_makes_one_call_per_month():
    """A 3-month range produces exactly 3 API calls."""
    connector = GDELTConnector(query='"AAPL"', asset_tags=["AAPL"])
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 3, 31, tzinfo=timezone.utc)

    call_count = 0

    def counting_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return make_mock_resp([])

    with patch("aiohttp.ClientSession.get", side_effect=counting_get):
        with patch("asyncio.sleep"):
            _ = [item async for item in connector.fetch_historical(start, end)]

    assert call_count == 3


@pytest.mark.asyncio
async def test_fetch_historical_continues_on_http_error():
    """Error on chunk 1 is skipped; chunk 2 articles are still yielded."""
    connector = GDELTConnector(query='"AAPL"', asset_tags=["AAPL"])
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 2, 28, tzinfo=timezone.utc)

    call_count = 0

    def failing_then_ok(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("HTTP 429")
        return make_mock_resp([SAMPLE_ARTICLE])

    with patch("aiohttp.ClientSession.get", side_effect=failing_then_ok):
        with patch("asyncio.sleep"):
            items = [item async for item in connector.fetch_historical(start, end)]

    assert len(items) == 1  # chunk 1 failed, chunk 2 succeeded


@pytest.mark.asyncio
async def test_fetch_historical_uses_gdelt_datetime_params():
    """STARTDATETIME and ENDDATETIME are sent in GDELT format."""
    connector = GDELTConnector(query='"MSFT"', asset_tags=["MSFT"])
    start = datetime(2024, 6, 1, tzinfo=timezone.utc)
    end = datetime(2024, 6, 30, tzinfo=timezone.utc)
    captured = {}

    def capture_get(url, params=None, **kwargs):
        captured.update(params or {})
        return make_mock_resp([])

    with patch("aiohttp.ClientSession.get", side_effect=capture_get):
        with patch("asyncio.sleep"):
            _ = [item async for item in connector.fetch_historical(start, end)]

    assert captured["STARTDATETIME"] == "20240601000000"
    assert "ENDDATETIME" in captured
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/connectors/test_gdelt_historical.py -v`

Expected: `AttributeError: 'GDELTConnector' object has no attribute 'fetch_historical'`

- [ ] **Step 3: Rewrite `src/connectors/gdelt.py`**

Replace the entire file:

```python
"""GDELT news connector."""

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import aiohttp

from src.connectors.base import NewsConnector
from src.models.news import NewsItem
from src.text.sanitizer import sanitize_text

logger = logging.getLogger(__name__)

_GDELT_DOC2_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


class GDELTConnector(NewsConnector):
    """GDELT API connector for news ingestion.

    Fetches news articles from GDELT 2.0 API, sanitizes content, and yields
    NewsItem objects. GDELT artlist mode returns titles only; title is used as
    body proxy.
    """

    def __init__(
        self,
        query: str,
        asset_tags: list[str],
        max_records: int = 50,
        timespan: str = "15min",
    ):
        self.query = query
        self.asset_tags = asset_tags
        self.max_records = max_records
        self.timespan = timespan

    async def fetch(self) -> AsyncIterator[NewsItem]:
        """Fetch recent articles using relative timespan (e.g. '15min')."""
        params = {
            "query": self.query,
            "mode": "artlist",
            "maxrecords": self.max_records,
            "format": "json",
            "timespan": self.timespan,
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(_GDELT_DOC2_URL, params=params) as resp:
                data = await resp.json(content_type=None)

        async for item in self._parse_articles(data.get("articles", [])):
            yield item

    async def fetch_historical(
        self,
        start_date: datetime,
        end_date: datetime,
        max_records_per_chunk: int = 250,
    ) -> AsyncIterator[NewsItem]:
        """Fetch articles in [start_date, end_date] chunked by calendar month.

        Makes one API call per month. Sleeps 1 s between chunks (GDELT rate limit).
        HTTP errors on a single chunk are logged and skipped.
        """
        current = start_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        while current <= end_date:
            if current.month == 12:
                next_month = current.replace(year=current.year + 1, month=1, day=1)
            else:
                next_month = current.replace(month=current.month + 1, day=1)

            chunk_end = min(next_month - timedelta(seconds=1), end_date)

            params = {
                "query": self.query,
                "mode": "artlist",
                "maxrecords": max_records_per_chunk,
                "format": "json",
                "STARTDATETIME": current.strftime("%Y%m%d%H%M%S"),
                "ENDDATETIME": chunk_end.strftime("%Y%m%d%H%M%S"),
            }

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(_GDELT_DOC2_URL, params=params) as resp:
                        data = await resp.json(content_type=None)

                async for item in self._parse_articles(data.get("articles", [])):
                    yield item

            except Exception as e:
                logger.warning("GDELT historical chunk %s failed: %s", current.date(), e)

            current = next_month
            await asyncio.sleep(1.0)

    async def _parse_articles(self, articles: list[dict]) -> AsyncIterator[NewsItem]:
        """Parse raw GDELT article dicts into sanitized NewsItem objects."""
        for article in articles:
            title = article.get("title", "")
            if not title:
                continue
            try:
                clean_title = sanitize_text(title)
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
                body=clean_title,
                url=article.get("url", ""),
                language="en",
                asset_tags=self.asset_tags,
            )
```

- [ ] **Step 4: Run new tests**

Run: `pytest tests/connectors/test_gdelt_historical.py -v`

Expected: All 4 tests PASS

- [ ] **Step 5: Verify existing GDELT tests still pass**

Run: `pytest tests/connectors/test_gdelt.py -v`

Expected: All 5 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/connectors/gdelt.py tests/connectors/test_gdelt_historical.py
git commit -m "feat: add GDELTConnector.fetch_historical for date-range queries"
```

---

## Task 5: CLI Script

**Files:**
- Create: `scripts/__init__.py` (empty — makes `scripts` importable in tests)
- Create: `tests/analysis/test_gdelt_ab_cli.py`
- Create: `scripts/gdelt_ab_test.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/analysis/test_gdelt_ab_cli.py`:

```python
"""Integration tests for gdelt_ab_test CLI — all external deps mocked."""
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from scripts.gdelt_ab_test import run_ab_test


def make_price_df(n_days: int = 260, start: str = "2024-01-02") -> pd.DataFrame:
    rng = np.random.default_rng(42)
    dates = pd.bdate_range(start=start, periods=n_days)
    prices = 100 * np.cumprod(1 + rng.normal(0.0005, 0.01, n_days))
    return pd.DataFrame({"Close": prices}, index=dates)


async def empty_async_gen(*args, **kwargs):
    """Async generator that yields nothing."""
    return
    yield  # noqa: unreachable — makes this an async generator


class TestRunABTest:
    @pytest.mark.asyncio
    async def test_result_contains_all_symbols(self):
        price_df = make_price_df()

        def mock_score_articles(articles, min_confidence=0.3):
            rng = np.random.default_rng(0)
            return [
                (date(2024, 1, 2) + timedelta(days=int(rng.integers(0, 250))),
                 float(rng.uniform(-0.5, 0.5)))
                for _ in range(50)
            ]

        with patch("scripts.gdelt_ab_test.score_articles", side_effect=mock_score_articles), \
             patch("scripts.gdelt_ab_test.GDELTConnector") as mock_gdelt_cls, \
             patch("scripts.gdelt_ab_test.yf.Ticker") as mock_ticker_cls:

            mock_connector = MagicMock()
            mock_connector.fetch_historical = empty_async_gen
            mock_gdelt_cls.return_value = mock_connector

            mock_ticker = MagicMock()
            mock_ticker.history.return_value = price_df
            mock_ticker_cls.return_value = mock_ticker

            result = await run_ab_test(
                symbols=["AAPL", "MSFT"],
                start=datetime(2024, 1, 1, tzinfo=timezone.utc),
                end=datetime(2024, 12, 31, tzinfo=timezone.utc),
                horizon=1,
                threshold=0.1,
                min_confidence=0.3,
            )

        assert "AAPL" in result["symbols"]
        assert "MSFT" in result["symbols"]
        assert "gate_passed_overall" in result
        assert "overall_delta_sharpe" in result

    @pytest.mark.asyncio
    async def test_gate_fails_with_no_articles(self):
        """Zero GDELT articles → no edge → gate should fail (delta_Sharpe < 0.1)."""
        price_df = make_price_df()

        with patch("scripts.gdelt_ab_test.score_articles", return_value=[]), \
             patch("scripts.gdelt_ab_test.GDELTConnector") as mock_gdelt_cls, \
             patch("scripts.gdelt_ab_test.yf.Ticker") as mock_ticker_cls:

            mock_connector = MagicMock()
            mock_connector.fetch_historical = empty_async_gen
            mock_gdelt_cls.return_value = mock_connector

            mock_ticker = MagicMock()
            mock_ticker.history.return_value = price_df
            mock_ticker_cls.return_value = mock_ticker

            result = await run_ab_test(
                symbols=["AAPL"],
                start=datetime(2024, 1, 1, tzinfo=timezone.utc),
                end=datetime(2024, 12, 31, tzinfo=timezone.utc),
                horizon=1,
                threshold=0.1,
                min_confidence=0.3,
            )

        assert result["gate_passed_overall"] is False
        assert result["symbols"]["AAPL"]["n_signals"] == 0

    @pytest.mark.asyncio
    async def test_result_schema(self):
        """Output dict matches the JSON schema from the spec."""
        price_df = make_price_df()

        with patch("scripts.gdelt_ab_test.score_articles", return_value=[]), \
             patch("scripts.gdelt_ab_test.GDELTConnector") as mock_gdelt_cls, \
             patch("scripts.gdelt_ab_test.yf.Ticker") as mock_ticker_cls:

            mock_connector = MagicMock()
            mock_connector.fetch_historical = empty_async_gen
            mock_gdelt_cls.return_value = mock_connector

            mock_ticker = MagicMock()
            mock_ticker.history.return_value = price_df
            mock_ticker_cls.return_value = mock_ticker

            result = await run_ab_test(
                symbols=["SPY"],
                start=datetime(2024, 1, 1, tzinfo=timezone.utc),
                end=datetime(2024, 3, 31, tzinfo=timezone.utc),
                horizon=1,
                threshold=0.1,
                min_confidence=0.3,
            )

        top = result["symbols"]["SPY"]
        for key in ("sharpe_baseline", "sharpe_gdelt", "delta_sharpe", "composite_ic",
                    "coverage_pct", "n_signals", "n_trading_days", "gate_passed"):
            assert key in top, f"Missing key: {key}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/analysis/test_gdelt_ab_cli.py -v`

Expected: `ModuleNotFoundError: No module named 'scripts.gdelt_ab_test'`

- [ ] **Step 3: Create `scripts/__init__.py`**

Create an empty file at `scripts/__init__.py`.

- [ ] **Step 4: Create `scripts/gdelt_ab_test.py`**

```python
"""GDELT A/B test: GDELT+FinBERT strategy vs buy-and-hold baseline."""

import argparse
import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import numpy as np
import yfinance as yf

from src.analysis.backtest import run_ab_comparison
from src.analysis.finbert import score_articles
from src.connectors.gdelt import GDELTConnector

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def run_ab_test(
    symbols: list[str],
    start: datetime,
    end: datetime,
    horizon: int = 1,
    threshold: float = 0.10,
    min_confidence: float = 0.3,
) -> dict[str, Any]:
    """Run the full GDELT A/B test for all symbols. Returns JSON-serializable dict."""
    symbol_results: dict[str, Any] = {}

    for symbol in symbols:
        logger.info("Processing %s ...", symbol)
        try:
            symbol_results[symbol] = await _process_symbol(
                symbol, start, end, horizon, min_confidence, threshold
            )
        except Exception as e:
            logger.error("Failed to process %s: %s", symbol, e)

    if not symbol_results:
        return {
            "run_date": datetime.now(timezone.utc).date().isoformat(),
            "period": {"start": start.date().isoformat(), "end": end.date().isoformat()},
            "config": {"horizon": horizon, "threshold": threshold, "min_confidence": min_confidence},
            "gate_passed_overall": False,
            "overall_delta_sharpe": 0.0,
            "symbols": {},
        }

    overall_delta = float(np.mean([r["delta_sharpe"] for r in symbol_results.values()]))
    return {
        "run_date": datetime.now(timezone.utc).date().isoformat(),
        "period": {"start": start.date().isoformat(), "end": end.date().isoformat()},
        "config": {"horizon": horizon, "threshold": threshold, "min_confidence": min_confidence},
        "gate_passed_overall": overall_delta >= threshold,
        "overall_delta_sharpe": round(overall_delta, 4),
        "symbols": symbol_results,
    }


async def _process_symbol(
    symbol: str,
    start: datetime,
    end: datetime,
    horizon: int,
    min_confidence: float,
    threshold: float,
) -> dict[str, Any]:
    # 1. Fetch GDELT articles
    connector = GDELTConnector(query=f'"{symbol}"', asset_tags=[symbol])
    articles = []
    async for item in connector.fetch_historical(start, end):
        articles.append(item)
    logger.info("  %s: %d articles fetched", symbol, len(articles))

    # 2. Score with FinBERT → list of (date, score)
    dated_scores = score_articles(articles, min_confidence=min_confidence)

    # 3. Aggregate to daily mean scores
    daily: dict = defaultdict(list)
    for article_date, score in dated_scores:
        daily[article_date].append(score)
    daily_mean = {d: float(np.mean(scores)) for d, scores in daily.items()}

    # 4. Fetch prices (yfinance Ticker.history returns flat-column DataFrame)
    ticker = yf.Ticker(symbol)
    hist = ticker.history(
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        auto_adjust=True,
    )
    if hist.empty:
        raise ValueError(f"No price data for {symbol}")

    closes = hist["Close"].values.astype(float)
    trading_dates = [d.date() for d in hist.index]

    # 5. Compute forward returns and align daily GDELT scores
    fwd_returns = []
    aligned_scores = []
    for i in range(len(closes) - horizon):
        fwd_returns.append(float((closes[i + horizon] - closes[i]) / closes[i]))
        aligned_scores.append(daily_mean.get(trading_dates[i], 0.0))

    # 6. A/B comparison
    ab = run_ab_comparison(
        daily_scores=aligned_scores,
        fwd_returns=fwd_returns,
        n_articles=len(articles),
        threshold=threshold,
    )

    return {
        "sharpe_baseline": round(ab.sharpe_baseline, 4),
        "sharpe_gdelt":    round(ab.sharpe_gdelt, 4),
        "delta_sharpe":    round(ab.delta_sharpe, 4),
        "composite_ic":    round(ab.composite_ic, 4),
        "coverage_pct":    round(ab.coverage_pct, 1),
        "n_signals":       ab.n_signals,
        "n_trading_days":  ab.n_trading_days,
        "gate_passed":     ab.gate_passed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="GDELT A/B test: GDELT+FinBERT vs buy-and-hold"
    )
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument("--horizon", type=int, default=1,
                        help="Forward return horizon in trading days (default: 1)")
    parser.add_argument("--threshold", type=float, default=0.1,
                        help="Min delta_Sharpe for PASS (default: 0.1)")
    parser.add_argument("--min-confidence", type=float, default=0.3, dest="min_confidence",
                        help="Min FinBERT confidence to include article (default: 0.3)")
    parser.add_argument("--output", default=None, help="JSON output file (default: stdout)")
    args = parser.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    result = asyncio.run(run_ab_test(
        symbols=args.symbols,
        start=start,
        end=end,
        horizon=args.horizon,
        threshold=args.threshold,
        min_confidence=args.min_confidence,
    ))

    output_str = json.dumps(result, indent=2)
    if args.output:
        with open(args.output, "w") as f:
            f.write(output_str)
        logger.info("Results written to %s", args.output)
    else:
        print(output_str)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/analysis/test_gdelt_ab_cli.py -v`

Expected: All 3 tests PASS

- [ ] **Step 6: Run full test suite to check for regressions**

Run: `pytest tests/ -v --tb=short 2>&1 | tail -20`

Expected: All 284+ existing tests still pass, plus 14 new tests (10 backtest + 7 finbert + 4 historical + 3 CLI).

- [ ] **Step 7: Commit**

```bash
git add scripts/ tests/analysis/test_gdelt_ab_cli.py
git commit -m "feat: add GDELT A/B test CLI script"
```

---

## Task 6: Smoke Test

- [ ] **Step 1: Verify CLI loads without errors**

Run: `python scripts/gdelt_ab_test.py --help`

Expected:
```
usage: gdelt_ab_test.py [-h] --symbols SYMBOLS [SYMBOLS ...] --start START
                        --end END [--horizon HORIZON] [--threshold THRESHOLD]
                        [--min-confidence MIN_CONFIDENCE] [--output OUTPUT]

GDELT A/B test: GDELT+FinBERT vs buy-and-hold
```

- [ ] **Step 2: Live run (requires internet + ~440 MB FinBERT download on first run)**

Run:
```bash
python scripts/gdelt_ab_test.py \
  --symbols AAPL \
  --start 2024-01-01 --end 2024-01-31 \
  --horizon 1 --threshold 0.1
```

Expected: JSON printed to stdout with keys `gate_passed_overall`, `overall_delta_sharpe`, `symbols.AAPL`. FinBERT is downloaded from HuggingFace on first run (one-time only, cached in `~/.cache/huggingface/`).
