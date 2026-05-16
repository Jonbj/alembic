# NewsAPI Enrichment Backtest — Implementation Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a second backtest run `gkg-nov25-newsapi-v1` using NewsAPI as article source (description+content ~300-400 chars) for the same tickers as the existing GDELT run, to compare IC/ICIR between title-only and enriched-text signals.

**Architecture:** NewsAPIConnector fetches articles by ticker+date range from `/v2/everything`. A new script `run_backtest_newsapi.py` runs Phase 0 (NewsAPI fetch → DB insert) then reuses the existing `phase2_infer`, `phase3_forward_returns`, `phase4_report` unchanged. No modifications to existing backtest phases.

**Tech Stack:** aiohttp (async HTTP), NewsAPI v2 REST, psycopg2, existing `NewsConnector` ABC, existing `ticker_lookup` PostgreSQL table.

---

## Scope

- **In scope:** Phase 0 (NewsAPI fetch), new run `gkg-nov25-newsapi-v1`, IC/ICIR comparison
- **Out of scope:** Live ingestion, URL-matching GDELT↔NewsAPI articles, NewsAPI paid plan features, other date ranges (can reuse same connector later)

---

## Components

### `src/connectors/newsapi.py`

Implements `NewsConnector` ABC. Single responsibility: given a ticker + company name + date range, fetch articles from NewsAPI and yield `NewsItem` objects.

```python
class NewsAPIConnector(NewsConnector):
    def __init__(self, api_key: str, max_requests_per_day: int = 95)
    async def fetch(self) -> AsyncIterator[NewsItem]  # live (not used yet)
    async def fetch_historical(
        self, ticker: str, company_name: str,
        start: datetime, end: datetime
    ) -> AsyncIterator[NewsItem]
```

**Article body:** `f"{description} {content}"` — concatenation of NewsAPI `description` (100-200 chars) and `content` (truncated at 260 chars by NewsAPI). Articles with both fields empty are skipped.

**Rate limiting:** instance-level counter `_requests_made`. Raises `NewsAPIRateLimitError` when `_requests_made >= max_requests_per_day`. Caller catches and logs warning, stops Phase 0 gracefully.

**Ticker → query:** uses `company_name` as primary search query (e.g., `"Goldman Sachs"`). Fallback: ticker symbol alone (e.g., `"GS"`) if `company_name` is empty.

**API call:**
```
GET https://newsapi.org/v2/everything
  ?q={company_name}
  &from={start.date()}
  &to={end.date()}
  &language=en
  &pageSize=100
  &sortBy=publishedAt
  &apiKey={api_key}
```

**Error handling:**
- HTTP 401 → `NewsAPIAuthError` (fatal — bad key)
- HTTP 429 → `NewsAPIRateLimitError` (stop gracefully)
- HTTP 5xx → log warning, skip ticker
- Article missing `description` AND `content` → skip silently

### `src/config.py`

Add field:
```python
NEWSAPI_KEY: str = Field(default_factory=lambda: os.environ.get("NEWSAPI_KEY", ""))
```

### `scripts/run_backtest_newsapi.py`

Thin script: Phase 0 + delegates to existing phases 2-4.

```
Phase 0: for each unique ticker in source_run_id
    → lookup company_name from ticker_lookup table
    → NewsAPIConnector.fetch_historical(ticker, company_name, start, end)
    → INSERT INTO backtest_signals (run_id=target_run_id, symbol, article_title=body,
                                    article_url=url, generated_at=publishedAt)
       ON CONFLICT DO NOTHING
    → if NewsAPIRateLimitError: log WARNING, break loop, continue to Phase 2

Phase 2: phase2_infer(pg_conn, target_run_id, dry_run)   # unchanged
Phase 3: phase3_forward_returns(pg_conn, target_run_id, start, end)  # unchanged
Phase 4: phase4_report(pg_conn, target_run_id)            # unchanged
```

CLI:
```
python scripts/run_backtest_newsapi.py \
  --source-run-id gkg-nov25-v1 \
  --target-run-id gkg-nov25-newsapi-v1 \
  --start 2025-11-01 \
  --end   2025-11-30
```

Auto-skip Phase 0 if `target_run_id` already has rows in DB (same resume logic as `run_backtest.py`).

### `tests/connectors/test_newsapi.py`

- `test_fetch_historical_yields_news_items` — mocked aiohttp, verifies body = description+content
- `test_skips_articles_with_no_text` — description=None, content=None → not yielded
- `test_raises_rate_limit_error_at_95_requests` — counter hits limit → raises
- `test_raises_auth_error_on_401` — HTTP 401 → NewsAPIAuthError
- `test_uses_ticker_symbol_when_no_company_name` — empty company_name → q=ticker

---

## Data Flow

```
ticker_lookup (PostgreSQL)
    ↓ company_name
NewsAPIConnector.fetch_historical()
    ↓ NewsItem(body=description+content, url, timestamp)
backtest_signals INSERT (run_id='gkg-nov25-newsapi-v1')
    ↓
phase2_infer() → LLM scores (unchanged)
    ↓
phase3_forward_returns() → 1h/4h/24h returns (unchanged)
    ↓
phase4_report() → IC/ICIR → reports/backtest_gkg-nov25-newsapi-v1.json
```

---

## Rate Limit Budget (free plan)

| Ticker count | Requests used | Daily budget remaining |
|-------------|--------------|----------------------|
| ~30 unique  | ~30 requests | ~70 remaining        |

Phase 0 completes in a single day well within free tier limits.

---

## Comparison

After both runs complete:
```sql
-- Compare IC/ICIR between runs
SELECT run_id, COUNT(*) as signals, AVG(score) as avg_score
FROM backtest_signals
WHERE run_id IN ('gkg-nov25-v1', 'gkg-nov25-newsapi-v1')
  AND score IS NOT NULL
GROUP BY run_id;
```

Phase 4 report JSON for each run contains full IC/ICIR breakdown for direct comparison.
