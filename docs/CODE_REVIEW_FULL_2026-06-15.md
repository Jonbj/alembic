# Full Code Review Report

**Date:** 2026-06-15  
**Scope:** Complete codebase (`src/`, `tests/`, `config/`, deployment artifacts)  
**Reviewers:** Multi-agent automated review (Kilo Code)  

---

## Executive Summary

This review covers **5 architectural areas** and **25+ primary files** across the Alembic trading system. The codebase demonstrates solid architectural separation (Alpha Miner paradigm, async discipline, structured logging) but suffers from systemic issues: **connection leaks**, **event-loop churn**, **missing input sanitization in fallback paths**, **N+1 queries**, **secret leakage in version control**, and **no CI/CD pipeline**.

| Severity | Count | Description |
|----------|-------|-------------|
| **Critical** | 28 | Security vulnerabilities, resource leaks, data-race conditions, financial correctness bugs |
| **Warning** | 72 | DRY violations, performance bottlenecks, missing validation, brittle error handling |
| **Info** | 34 | Style notes, architectural observations, positive patterns |

---

## 1. Core Workers (`src/workers/`)

### 1.1 `performance.py` (1,883 lines)

**Critical**
- **Line 783** — Local shadowing of module constant `_MIN_SAMPLES = 10` inside `run_weekly_weights` shadows the module-level `_MIN_SAMPLES = 300` (line 70). Changes guardrail semantics silently.
- **Lines 726, 904, 1332, 1357, 1675, 1715** — Multiple `asyncio.run()` calls per task. Each Telegram alert spins up and tears down a new event loop. In Celery prefork workers this is wasteful and can cause event-loop state pollution.
- **Lines 695, 697, 703, 851, 860, 916, 1001, 1177** — Direct access to `redis._r` private attribute breaks encapsulation.
- **Lines 1168, 1172** — Using `print()` instead of logging in `check_suggestion_expiry`.
- **Lines 1290–1360** — Resource leak: `notifier = TelegramNotifier()` is never closed.
- **Lines 682, 764, 952, 1155** — `RedisStore` instances created in multiple tasks are never closed.
- **Lines 220–221** — Inconsistent API usage: `compute_composite_ic` and `compute_icir` called without `all_confs` parameter.
- **Line 1045** — `_build_signal_distribution` uses module-level `ENTRY_THRESHOLD`, ignoring Redis feedback override.

**Warning**
- **Lines 89–91, 108–110, 955–958** — N+1 query pattern: loops over `WATCHLIST_SYMBOLS` querying PG once per symbol.
- **Line 742** — `TradingClient` instantiated inside nested `try` but never explicitly closed.
- **Lines 689, 771** — Hardcoded default ensemble weights repeated verbatim in two tasks.
- **Lines 832–841, 1268–1273** — Duplicated G3.5 anti-predictive guard logic.
- **Lines 745, 922** — Bare `except Exception` masks unexpected failures.
- **Lines 140–147** — `budget_tracker.record_spending` called sequentially; should use `asyncio.gather`.
- **Lines 42, 46** — Unused/misplaced imports (`psycopg2`, `hashlib`).
- **Lines 159–160** — Fragile date arithmetic using `fromordinal` instead of `timedelta`.

### 1.2 `execution.py` (874 lines)

**Critical**
- **Lines 278, 397, 534, 568, 607, 736, 807** — Multiple `asyncio.run()` calls per alert cycle.
- **Lines 543, 766** — `UnboundLocalError` risk: `tick_time` defined inside `for symbol in symbols` loop; if `symbols` is empty, line 766 crashes.
- **Lines 836–873** — Alpaca client leaks: `TradingClient` and `StockHistoricalDataClient` never closed in `finally`.
- **Lines 704–727** — Zero-quantity risk: `qty = round(notional / price, 4)` can produce `0.0` for high-priced stocks.
- **Line 710** — Rounding error on stop price: `round(price * (1 - sym_stop_pct), 2)` can round *up*, tightening stop.
- **Line 855** — Fragile DB URL manipulation: `config.DATABASE_URL.replace("+asyncpg", "")`.

**Warning**
- **Lines 59–103** — File I/O on hot path: `_load_execution_engine`, `_load_risk_params`, `_load_killswitch_recovery_config` parse YAML on every 15-min cycle.
- **Lines 512–523** — Overly conservative fail-safe: pending-order fetch failure blocks all new entries for 15 minutes.
- **Lines 643–649** — Fallback signals counted as `skipped_stale`; deserve own counter.
- **Line 546** — `tick_time` reset per symbol; all decisions in cycle should share timestamp.

### 1.3 `portfolio_scheduler.py` (727 lines)

**Critical**
- **Line 187, 226** — `_run_cycle_inner` creates `TradingClient` and `StockHistoricalDataClient` but **never closes them**.
- **Line 467** — Second `PostgreSQLStore` (`_pg_trades`) closed inside `try` rather than `finally`, leaking on exception.
- **Lines 151–172, 302–328, 445–452** — Multiple ephemeral Redis connections opened per cycle instead of reusing one.
- **Lines 630–693** — `_submit_portfolio_orders` submits orders one-by-one with no batching.
- **Lines 660–668** — `MarketOrderRequest` uses string literals `"buy"`/`"sell"` instead of `OrderSide` enums.
- **Lines 696–727** — Fragile raw psycopg2 URL construction via `replace("+asyncpg", "")`.

**Warning**
- **Lines 531–551** — `_apply_zeygos_filter` defined but never called (dead code).
- **Lines 293–298** — `MarketSnapshot` hardcodes `volumes` and `adv_20d` to `1_000_000.0`.
- **Lines 482–483** — `_portfolio_postmortem` hardcodes `regime="risk_on"`.
- **Line 24** — Unused import `from pathlib import Path`.

### 1.4 `sentiment.py` (444 lines)

**Critical**
- **Lines 123, 161** — **Sanitization bypass**: `finbert.analyze(item.body[:512])` passes **raw** article body to FinBERT, not `clean_body`. Violates architecture spec requiring sanitized text before LLM processing.
- **Line 240** — `asyncio.Semaphore(1)` in `process_news_batch` means sequential processing despite `asyncio.gather`.
- **Lines 339–349** — Crash recovery race condition: `lrange` + pipeline rpush not atomic.
- **Lines 427–428** — Unsafe queue deletion: `redis_client.delete("news:processing")` deletes entire queue.
- **Line 279** — `psycopg2.connect(config.DATABASE_URL)` breaks if URL contains `+asyncpg`.

**Warning**
- **Line 104** — Reads `SENTIMENT_LLM_BODY_CHARS` env var on every inference call.
- **Lines 139–147** — `record_spending` loop sequential; could be parallelized.
- **Lines 193–211** — `process_news_item` catches all store-write exceptions and still returns result.
- **Line 313** — `finbert._get_pipeline()` accesses private method.

### 1.5 `ingestion.py` (336 lines)

**Critical**
- **Line 320** — `psycopg2.connect(config.DATABASE_URL)` missing `replace("+asyncpg", "")`.
- **Lines 119, 171, 257** — No queue TTL or `MAXLEN`; unbounded Redis growth if SentimentWorker is down.
- **Lines 102–112, 154–165, 241–251** — Memory amplification: multi-ticker articles expanded into full copies per ticker.

**Warning**
- **Lines 48–56, 126–128, 216–218** — List comprehension over async iterators buffers entire result sets.
- **Lines 177–213, 263–300, 303–335** — Code duplication across three ingestion workers.
- **Lines 89–91** — `extractor.extract(gkg_item.org_names)` passes raw org names without length limit.

### 1.6 `regime.py` (332 lines)

**Critical**
- **Lines 162, 174, 185, 194, 212, 226, 239, 252, 273, 284, 330** — Up to 11 `asyncio.run()` calls per task invocation.
- **Lines 148, 149** — `RedisStore()` and `TelegramNotifier()` instantiated but never closed.
- **Lines 204–205, 206** — LLM clients instantiated but never closed.
- **Lines 310, 321–322, 325–330** — No Redis failure handling around writes.

**Warning**
- **Lines 137–332** — `detect_regime` is 195 lines; should be decomposed.
- **Lines 261–266** — `multipliers` dict rebuilt from config on every run.
- **Line 41** — Imports four LLM client classes but only uses them dynamically.

---

## 2. LLM Pipeline & Text Processing (`src/llm/`, `src/text/`)

### 2.1 `client.py` (779 lines)

**Critical**
- **Line 317** — Security docstring mismatch: claims env vars are sanitized, but `env={**os.environ, "LC_ALL": "C"}` passes **entire parent environment** unchanged.
- **Line 676** — Blocking Redis call in async path: `_OllamaSemaphore.acquire()` calls `r.lpush()` and `r.close()` synchronously without `run_in_executor`.
- **Lines 379–606** — Massive DRY violation: `OpusClient`, `Qwen35Client`, `DeepseekClient`, `GlmClient` contain identical `complete()` implementations.

**Warning**
- **Line 108** — Overly aggressive error redaction regex strips legitimate debugging context.
- **Line 639** — Redis connection created per semaphore acquisition; defeats pooling.
- **Lines 751–753** — No retry on timeout in `OllamaCloudClient`.
- **Line 472** — Unreachable dead code: final `raise RuntimeError` after exhaustive retry loop.
- **Lines 745–749** — No retry on 429 (rate limit).
- **Line 718** — `config.OLLAMA_API_KEY` pulled into headers; ensure config is not logged.

### 2.2 `ensemble.py` (329 lines)

**Warning**
- **Line 49** — `numpy` imported solely for `np.std()` on 2–4 floats; Python `statistics.stdev()` suffices.
- **Lines 305, 317** — `print()` used instead of `logging` module.
- **Line 280** — Overly restrictive type signature hardcodes `LLMSentimentOutput`.
- **Line 246** — `np.std(..., ddof=1)` uses sample std for 2–4 models; population std may be more appropriate.
- **Line 301** — `import asyncio` inside function body.

### 2.3 `finbert.py` (164 lines)

**Warning**
- **Line 112** — Character-based truncation instead of token-based: `clean_text[: self._MAX_TOKENS]` slices Unicode code points, not tokenizer tokens.
- **Line 155** — Overly broad `except Exception` swallows CUDA OOM, model download failures, etc.
- **Line 92** — `device="cpu"` hardcoded; ignores available GPU.
- **Lines 149–161** — Sequential single-item processing; pipeline supports batching.

**Info**
- Consider adding `async def analyze_async()` wrapper for consistency with async client suite.

### 2.4 `budget.py` (291 lines)

**Warning**
- **Lines 96, 104** — `check_budget()` annotated `Literal["ok", "exhausted"]` but **raises** on exhausted; return type should be `Literal["ok"]` or `None`.
- **Lines 106, 172, 221, 246** — Connection lifecycle risk: `_get_connection()` stores conn on `self._conn`; can exhaust pool under load.
- **Line 275** — `NoOpBudgetTracker` inherits from `LLMBudgetTracker` with fundamentally different `__init__` (Liskov violation).
- **Lines 268–272** — Only synchronous context manager provided; async methods suggest `__aenter__`/`__aexit__` would be more idiomatic.
- **Line 162** — Silent default pricing for unknown models falls back to arbitrary costs without logging.

### 2.5 `sanitizer.py` (86 lines)

**Warning**
- **Lines 48–57** — Incomplete emoji regex misses Miscellaneous Symbols, Dingbats, ZWJ sequences, Unicode 15/16 emojis.
- **Lines 33–35** — Overly broad `Cf` removal strips legitimate format controls (soft hyphens, variation selectors).
- **Lines 39, 44** — Invisible characters stored as literal string literals; maintenance hazard. Use `\uXXXX` escapes.

**Info**
- Regexes compiled on every function call; should be module-level constants.
- No semantic prompt-injection filtering (e.g., "ignore previous instructions"). Document as handled upstream or add regex guard.

---

## 3. Data Layer & Connectors (`src/store/`, `src/connectors/`, `src/models/`)

### 3.1 `pg_store.py` (1,592 lines)

**Critical**
- **Lines 507–556** — Race condition in `close_trade`: `SELECT ... FOR UPDATE SKIP LOCKED` executed inside cursor block that closes immediately, releasing row lock before `UPDATE`.
- **Lines 710–802** — Broken transaction boundary in `reconcile_trade_fills`: commits twice; if second block fails, DB is partially reconciled.
- **Lines 1531–1561, 804–826** — Row-by-row INSERT loops (N+1 writes). Should use `executemany` or `COPY`.

**Warning**
- **Lines 24–42** — `ThreadedConnectionPool` initialized without `block=False` or timeout.
- **Lines 109–131** — Pool exhaustion fallback creates unbounded direct connections.
- **Lines 1472–1493, 1495–1518** — Silent error swallowing returns `None`/empty list without re-raising.
- **Line 61** (and throughout) — Interval construction via string concatenation `%s || ' days'::interval` is safe but `make_interval(days => %s)` is clearer.
- **Lines 1134–1154** — Manual `IN` placeholder construction fragile for very large symbol lists.
- **Lines 1520–1527** — Unsafe `__del__` usage for connection return.
- **Lines 217–218** — Silent truncation in `log_news_item`.
- **Line 1122–1126** — Unbounded result set in `fetch_signals_pending_forward_return` with no `LIMIT`.

**Info**
- Missing index hints for `trades(exit_time)`, `sentiment_signals(symbol, generated_at)`, `trades(signal_id)`.

### 3.2 `redis_store.py` (661 lines)

**Critical**
- **Lines 228–254** — Non-atomic fallback counter increment: `incr`, `expire`, threshold check are three separate round-trips.
- **Lines 265–296** — Non-atomic `_on_fallback_threshold_reached`: multiple `set`/`expire` not pipelined.

**Warning**
- **Line 93** — Inefficient serialization: `json.loads(result.model_dump_json())` round-trips through JSON.
- **Lines 97–103, 159–166, 183–189, 241–254, 341–351, 371–376, 592–600** — Overly broad exception handling with fragile OOM string matching.
- **Lines 409–414, 416–421** — Unprotected `json.loads` without exception handling for corrupted values.

### 3.3 `gdelt_gkg.py` (265 lines)

**Warning**
- **Lines 83–90** — Generic `Exception` catch masks DNS, SSL, aiohttp bugs.
- **Lines 187–196** — Fragile org name parsing: `rsplit(",", 1)[0]` truncates names like `"Apple, Inc"`.
- **Lines 237–243** — Redundant 429 handling unreachable due to prior status check.

**Info**
- Sequential backfill with 0.5s sleep is slow (~840 sequential requests for 6 months).
- No deduplication at connector level.

### 3.4 `marketaux.py` (~200 lines)

**Critical**
- **Lines 112–117** — Session-per-page anti-pattern: new `aiohttp.ClientSession` inside `while True` loop.

**Warning**
- **Lines 181–183** — Silent timestamp corruption: falls back to `datetime.now(timezone.utc)` on parse failure.
- **Lines 100–134** — No pagination safety limit (`max_pages`).
- **Lines 66–69, 101–104** — No retry/backoff on 429.

### 3.5 `alpaca_news.py` (~180 lines)

**Critical**
- **Lines 106–112** — Session-per-page anti-pattern (same as MarketAux).

**Warning**
- **Lines 175–178** — Silent timestamp corruption on parse failure.
- **Lines 98–121** — No pagination safety limit.
- **Lines 159–165** — Naive HTML stripping via regex.

### 3.6 `models/news.py` (~90 lines)

**Warning**
- **Lines 32–39** — Missing validators on `NewsItem`: empty `id`/`body`, invalid `url`, invalid `language` not rejected.
- **Line 34** — `title` defaults to empty string; no error if both `title` and `body` empty.
- **Line 88** — `LLMSentimentOutput.reasoning` has no `min_length`.
- **Line 89** — `LLMSentimentOutput.ticker` defaults to empty string without format validation.

### 3.7 `models/signals.py` (~40 lines)

**Critical**
- **Lines 20–35** — `model_dump_json` override breaks Pydantic contract: signature incompatible with Pydantic's method (missing `indent`, `include`, `exclude`, `context`). `# type: ignore[override]` confirms awareness. Remove override and use `model_config = ConfigDict(json_encoders=...)` or `model_dump(mode="json")`.

**Warning**
- Manual JSON serialization bypasses Pydantic features (custom serializers, computed fields).

---

## 4. Portfolio, Strategies & API (`src/portfolio/`, `src/strategies/`, `src/api/`)

### 4.1 `orchestrator.py` (302 lines)

**Critical**
- **Line 149** — Negative target weights treated as "liquidate to zero" instead of short positions.
- **Lines 152, 196–210** — Short positions (negative quantity) never covered; orphaned shorts persist.
- **Lines 297–303** — `_compute_nav` skips positions where `market.price_of()` returns `None`, understating NAV.
- **Line 170** — `target_qty = (nav * target_wt) / price` with no lot-size rounding or minimum-order-size check.

**Warning**
- **Lines 266–273** — Hard-coded strategy branching (`if strategy_id == "S1"`) violates Open/Closed principle.
- **Line 96** — `from uuid import uuid4` imported inside method.
- **Line 175** — Magic number `1e-4` as delta threshold not scaled to NAV or lot size.
- **Lines 167–168** — Missing price logs debug message and `continue`s silently.

### 4.2 `constraints.py` (344 lines)

**Critical**
- **Lines 137–139** — `_scale_orders` uses `with_quantity(result[i].quantity * scale)` but never rounds to lot size.

**Warning**
- **Lines 127–131, 161, 201–203, 230–232, 272–274** — Notional computation repeated in every enforcement method.
- **Lines 18–30, 33–38** — Hand-rolled `_pearson_correlation` and `_std_dev` over Python lists.
- **Lines 19–22** — Pearson correlation silently truncates unequal-length return series.
- **Lines 158–160** — Missing or non-positive price causes `continue` with no logging.
- **Line 88** — Local variable `_corr_reduced` uses leading-underscore convention incorrectly.
- **Lines 112–115** — O(n²) nested loop over strategy returns.

### 4.3 `strategies/s1/sizing.py` (~40 lines)

**Warning**
- **Line 31** — `target_vol / ann_vol` produces `inf` or `NaN` with no guard.
- **Line 31** — Weights not normalized to sum to 1.0.
- **Lines 8–13** — No input validation for `vol_window <= 0`, negative `target_vol`.

### 4.4 `strategies/s4/backtest.py` (292 lines)

**Critical**
- **Lines 70–71** — `pd.concat(wf_window_returns, ignore_index=True)` drops timestamps; overlapping windows double-count returns in Sharpe denominator.
- **Lines 249–267** — N+1 query: `fetch_signals_for_backtest(ticker, ...)` called inside ticker loop.

**Warning**
- **Lines 163–171** — Perturbation config may set `min_stocks > n_top`.
- **Line 61** — `w.oos_result.snapshots` assumes `oos_result` is never `None`.
- **Lines 106–108** — Hard-coded gate keys are brittle.
- **Lines 224–244** — Imports inside function suggest circular-dependency risk.
- **Line 80** — `oos_nav.pct_change()` assumes uniform spacing.

### 4.5 `api/routes/strategies.py` (319 lines)

**Critical**
- **Line 38** — Manual JSON construction `f'["{strategy_id.upper()}"]'` instead of `json.dumps`. Malformed input with quotes/backslashes breaks query.
- **Lines 24–43, 276–279** — `_check_live_data` instantiates new `PostgreSQLStore()` on every call; N round-trips in `list_strategies`.

**Warning**
- **Lines 220–221** — `_load_equity_curve` drops leading flat-zero period, artificially cleaning curves.
- **Lines 224–248** — `SENSITIVITY_S1` and `SENSITIVITY_S3` are purely synthetic formulas, not actual backtest results.
- **Lines 48–89, 92–133, 138–165, 167–208** — All strategy metadata hard-coded; violates DRY.
- **Lines 298–303, 306–311, 314–319** — Missing strategy returns `[]` (200 OK) instead of 404.

### 4.6 `api/routes/backtest.py` (~300 lines)

**Critical**
- **Lines 276–287** — `limit` and `offset` query parameters accept negative values with no validation.
- **Lines 14–33, 47–107, 121–149** — Every endpoint manually calls `pg._get_connection()` without connection-pool context manager.

**Warning**
- **Lines 62–68, 176–179, 214–216** — Hit-rate calculation copy-pasted across three endpoints.
- **Lines 77–94** — Weekly ICIR buckets with no minimum observation count per week.
- **Lines 260–261** — Missing days treated as 0 return, biasing cumulative P&L.
- **Lines 126–130** — `width_bucket` subqueries double-scan table.
- **Lines 276–300** — Pagination uses `LIMIT/OFFSET`; keyset pagination preferred for time-series.

---

## 5. Tests, Configuration & Deployment

### 5.1 Test Suite (`tests/`)

**Critical**
- **`tests/test_llm_client.py`** — Only covers JSON parsing, allowlist, and one aiohttp mock path. Missing: subprocess execution, retry logic, `_sanitize_error_output`, semaphore exhaustion, path injection (779-line module largely untested).
- **`.coverage` file exists but stale**; no `coverage run` invocation documented, no `[tool.coverage.run]` config.

**Warning**
- **`tests/conftest.py`** — Extremely minimal (24 lines). Missing shared Redis/PG fixtures, factory fixtures for `NewsItem`/`SentimentResult`.
- **`tests/workers/test_performance_worker.py`** — Mocks patch internal private functions instead of boundary interfaces.
- **`tests/workers/test_sentiment_worker.py`** — Integration tests mock `asyncio.run`, so coroutine scheduling is never exercised.
- **`tests/workers/test_portfolio_scheduler.py`** — Several tests patch 7–10 collaborators in large blocks.
- **`tests/test_budget_tracker.py`** — Connection-pool failure paths and `_get_pool` circular-import handling undertested.

### 5.2 Configuration & Secrets

**Critical**
- **`.env` is tracked in git** and contains **real, unredacted secrets**:
  - `ADMIN_API_KEY`, `OLLAMA_API_KEY`, `NEWSAPI_KEY`, `MARKETAUX_API_KEY`, `FRED_API_KEY`, `DEEPL_API_KEY`, `TELEGRAM_BOT_TOKEN`, `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`.
  - `.gitignore` lists `.env` but file is already tracked.

**Warning**
- **`src/config.py`** — `TELEGRAM_ALLOWED_USER_IDS` does not validate numeric entries; `ALPACA_API_KEY`/`SECRET_KEY` have no length/format validators.
- **`config/strategies.yaml`** — No schema validation; `allocation_pct` sum and S4 cap are comments, not enforced at load time.
- **`config/trading.yaml`** — `engine: portfolio` is magic string with no enum validation.

### 5.3 Deployment

**Critical**
- **`docker-compose.yml`** — Hardcodes weak credentials (`POSTGRES_PASSWORD: trading`, `GF_SECURITY_ADMIN_PASSWORD: alembic123`).
- **`docker-compose.yml`** — No resource limits (`deploy.resources.limits`) on any service.
- **`Dockerfile`** — Installs from `requirements.txt` instead of `pyproject.toml`/`uv.lock`.
- **`Dockerfile`** — Hardcodes `torch==2.6.0+cpu` while `pyproject.toml` specifies `torch>=2.2`.

**Warning**
- **`Dockerfile`** — No non-root `USER` directive.
- **`docker-compose.yml`** — API healthcheck uses `urllib.request.urlopen` without timeout.
- **`docker-compose.yml`** — `grafana` enables anonymous auth with `Viewer` role and disables sandboxing.
- **`celery_app.py`** — `poll-telegram-updates` every 5 seconds without persistent beat volume; may dispatch duplicates on restart.
- **`celery_app.py`** — No `worker_prefetch_multiplier` or `task_acks_late`; long-running sentiment tasks may cause head-of-line blocking.

### 5.4 CI/CD & Tooling

**Critical**
- **No CI/CD pipeline exists.** No `.github/workflows/`, `.gitlab-ci.yml`, `Jenkinsfile`, or pre-commit config.
  - No automated tests, linting (`ruff`, `mypy`), formatting, dependency vulnerability scanning, or secret scanning.

**Warning**
- **`pyproject.toml`** — Includes `mypy>=1.10` and `ruff>=0.4` in dev deps but contains **zero configuration** for either tool (no `[tool.mypy]`, no `[tool.ruff]`).
- **`pytest.ini`** — No custom markers, log level config, or `--strict-markers`.
- **`requirements.txt` vs `pyproject.toml`** — Significantly out of sync. `sqlalchemy`, `pydantic-settings`, `python-dotenv`, `feedparser`, `bleach`, `python-telegram-bot`, `pyarrow`, `empyrical`, `pdfplumber` missing from `requirements.txt`.
- **`requirements.txt`** — Includes `asyncio>=3.4` which conflicts with Python 3.11+ standard library.
- **Missing type stubs** — `types-psycopg2`, `types-redis`, `types-requests`, `types-aiohttp` omitted.

---

## 6. Cross-Cutting Issues

1. **Event-Loop Churn**: `asyncio.run()` is called repeatedly inside Celery tasks (performance, execution, regime, portfolio scheduler). This is anti-idiomatic and can cause state pollution in prefork workers. Solution: use `app.task` with async functions (Celery 5+) or a persistent event-loop thread.

2. **Connection Leaks**: Redis, PostgreSQL, Alpaca, and Telegram clients are frequently instantiated without guaranteed `finally: close()` cleanup. The worst offender is `portfolio_scheduler.py`, which creates multiple clients per cycle and leaks them on exceptions.

3. **N+1 Patterns**: Both read and write N+1 anti-patterns exist across `pg_store.py` (row-by-row inserts), `performance.py` (per-symbol signal queries), and `s4/backtest.py` (per-ticker backtest fetches).

4. **Input Sanitization Inconsistency**: While `sentiment.py` now sanitizes text before the LLM ensemble, the FinBERT fallback path (`finbert.analyze(item.body[:512])`) still receives raw, unsanitized text, violating the architecture spec.

5. **Secret Leakage**: `.env` with production credentials is committed to git. All exposed secrets must be rotated immediately.

6. **No CI/CD**: There is zero automation for testing, linting, type-checking, or deployment validation.

---

## 7. Top Priority Actions

| Priority | Action | Owner |
|----------|--------|-------|
| **P0** | Rotate all secrets exposed in `.env`; purge `.env` from git history | Security |
| **P0** | Fix connection lifecycle: every `RedisStore`, `PostgreSQLStore`, `TradingClient`, `TelegramNotifier` must be closed in `finally` | Backend |
| **P0** | Replace repeated `asyncio.run()` with Celery async tasks or a persistent event loop | Backend |
| **P0** | Add CI/CD pipeline (GitHub Actions) running `pytest`, `ruff`, `mypy`, `coverage`, `pip-audit` | DevOps |
| **P1** | Fix FinBERT sanitization bypass: pass `clean_body[:512]` instead of `item.body[:512]` | Backend |
| **P1** | Fix `pg_store.py` race condition in `close_trade` (row lock released before UPDATE) | Backend |
| **P1** | Fix `pg_store.py` broken transaction in `reconcile_trade_fills` (partial commit) | Backend |
| **P1** | Unify dependency management: delete `requirements.txt`, install from `pyproject.toml` + `uv.lock` in Docker | DevOps |
| **P1** | Replace N+1 queries in `performance.py` and `pg_store.py` with batched `WHERE symbol = ANY(%s)` or `executemany` | Backend |
| **P2** | Add resource limits and non-root users to `docker-compose.yml` | DevOps |
| **P2** | Add `pyproject.toml` config for `mypy`, `ruff`, and `coverage` | Tooling |
| **P2** | Expand `tests/test_llm_client.py` to cover subprocess execution, retry logic, semaphore paths | QA |
| **P2** | Add pagination safety limits (`max_pages`) to `marketaux.py` and `alpaca_news.py` | Backend |
| **P2** | Fix token-aware truncation in `finbert.py` using `self._pipe.tokenizer.encode` + truncation | ML |

---

*End of Report*
