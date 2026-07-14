# Alembic — Context Map (audit-context-building)

**Date:** 2026-07-10
**Method:** audit-context-building (read-only, no problem-hunting, no proposed changes). Built by fanning out five parallel read-only explorers across the codebase and synthesizing their findings. Each conclusion cites supporting files.
**Source of truth:** the **code**. `docs/ARCHITECTURE.md` lags the code in several places — see §9.

---

**System shape:** an LLM-based algorithmic trading system ("Alpha Miner" paradigm). LLMs run offline in background workers; the execution engine reads pre-computed signals from Redis/PostgreSQL and never calls an LLM in the hot path. Two execution paths exist behind one `execution.engine` flag: a legacy per-symbol worker and the active weight-then-order portfolio orchestrator. Stack: FastAPI + Celery + Redis + PostgreSQL; Alpaca SDK for broker; Ollama-cloud LLMs + local FinBERT.

## 1. Components & responsibilities

Organized by `src/` subpackage (responsibilities + load-bearing symbols):

| Subpackage | Responsibility | Load-bearing symbols | Files |
|---|---|---|---|
| `config.py` | Central Pydantic `Config` (frozen) singleton from env + `config/*.yaml`; `ADMIN_API_KEY` length≥32 validator | `config` | `src/config.py` |
| `store/` | Data access. `PostgreSQLStore` (threaded pool, ~60 methods); `RedisStore` (hot-path cache + state) | `PostgreSQLStore`, `RedisStore` | `src/store/pg_store.py`, `redis_store.py` |
| `workers/` | Celery task layer (the runtime beat). Largest module is `portfolio_scheduler.py` (~2400 lines) | `run_portfolio_cycle`, `run_execution_worker`, `run_sentiment_worker`, `run_daily_report`, `detect_regime` | `src/workers/{portfolio_scheduler,execution,sentiment,performance,regime,ingestion,celery_app,...}.py` |
| `portfolio/` | Multi-strategy orchestration. Weight-then-order cycle, 5-pass constraint enforcement, EWMA vol targeting | `PortfolioOrchestrator`, `ConstraintEnforcer`, `PortfolioVolTargeter` | `src/portfolio/{orchestrator,constraints,vol_targeting,risk_monitor,decay_monitor,...}.py` |
| `strategies/` | Strategy implementations + lifecycle. Registry loads only S1/S2/S4 (lazy imports); S7 not registered | `StrategyRegistry`, `request_promotion/approve_promotion/demote_strategy`, `TimeSeriesMomentum`, `NewsDrivenTactical`, `PEADStrategy` | `src/strategies/{registry,promotion,s1,s2,s3,s4,s7}/` |
| `llm/` | LLM clients + ensemble + budget. Ollama-cloud clients (kimi/glm/qwen/deepseek) + FinBERT fallback + spend cap | `LLMClient`, `EnsembleAggregator`, `FinBERTClient`, `LLMBudgetTracker`, `build_sentiment_clients` | `src/llm/{client,ensemble,finbert,budget,model_registry}.py` |
| `connectors/` | News sources + deterministic ticker resolution. NewsConnector ABC; pure decision core + fail-open providers | `GDELTGKGConnector`, `AlpacaNewsConnector`, `resolve`, `gather_evidence`, `TickerExtractor`, `Deduplicator` | `src/connectors/{gdelt_gkg,alpaca_news,ticker_resolver,ticker_resolver_providers,...}.py` |
| `api/` | FastAPI control plane. 16 routers; API-key + JWT auth | `app`, `require_api_key`, `create_access_token` | `src/api/main.py`, `deps.py`, `auth.py`, `jwt_utils.py`, `routes/*.py` |
| `backtest/` | Backtest engine + gates (reused by live portfolio engine). Walk-forward, robustness, regime, stress gates | `BacktestOrchestrator`, `VirtualPortfolio`, `run_all_gates`, `WalkForwardRunner` | `src/backtest/{engine,gates,walkforward,costs,metrics}/` |
| `models/` | Pydantic data models (true leaf — imports nothing cross-package) | `NewsItem`, `SentimentResult`, `RegimeState`, `SurpriseSignal`, `LLMSentimentOutput` | `src/models/{news,signals,regime,pead,performance}.py` |
| `performance/` | Metrics + weight optimization. Composite IC (B4 + Newey-West HAC), LOO ICIR, drift, postmortem | `compute_composite_ic`, `compute_purified_icir`, `detect_drift`, `diagnose_loss` | `src/performance/{ic,weights,drift,postmortem,threshold}.py` |
| `notifications/` | `Notifier` Protocol + Telegram (raw Bot API, no PTB) | `TelegramNotifier`, `AlertLevel` | `src/notifications/{base,telegram}.py` |
| `text/` | Input sanitization (BiDi, homoglyphs, NFKC) | `sanitize_text`, `sanitize_ticker` | `src/text/sanitizer.py` |
| `costs/`, `monitoring/`, `analytics/`, `analysis/`, `options/`, `brokers/`, `data/` | Trade cost calc, cockpit/divergence alerts, paper-validation metrics, A/B comparison, Black-Scholes, broker ABC (IBKRAdapter only), options ingestion | `TradeCostCalculator`, `get_cockpit_alerts`, `compute_validation_metrics`, `IBKRAdapter` | respective files |

## 2. Entry points

| Entry point | Launcher | Cited |
|---|---|---|
| FastAPI app (16 routers, `/api/health`, SPA fallback) | `uvicorn src.api.main:app` (docker `api`, host 8001); refuses start if `JWT_SECRET_KEY` unset | `src/api/main.py:28,43-58`; `docker-compose.yml:30` |
| Celery app (13 task modules, two queues) | `celery -A src.workers.celery_app`; broker+backend=Redis; time limit 840s/soft 780s | `src/workers/celery_app.py:25` |
| Celery `beat` (emits ~22 scheduled tasks) | docker `beat` service | `src/workers/celery_app.py:65-231` |
| `worker` (concurrency 4, `-Q celery`) | docker `worker` | `docker-compose.yml` |
| `worker-inference` (concurrency 1, `-Q inference`) — single FinBERT/Ollama copy | docker `worker-inference` | `docker-compose.yml` |
| Frontend SPA | docker `frontend` (port 3000→80), built from `frontend/` | `docker-compose.yml` |
| Backtest runner | docker `backtest` (`profiles:[backtest]`, manual/interactive only) | `docker-compose.yml` |
| CLI scripts | `python scripts/<name>.py` — ops-critical: `sample_news_labels`, `compute_label_forward_returns`, `validate_ticker_sentiment`, `run_s4_gate_report`, `compare_models_retro`, `backtest_s7_pead` | `scripts/` |
| `__main__` runners | `src/workers/news_stream.py:105` (manual Alpaca stream), `src/strategies/s4/gate_cli.py:84` (S4 gate CLI, exits 0/1) | — |

**Worker split** is structural, not via `task_routes`: only `options.queue="inference"` in the beat schedule routes tasks; everything else falls to default `celery`. inference tasks = `sentiment`, `regime` (×2), `telegram-poller`, `pead-ingestion`.

### Beat schedule (full)

| Beat name | Task | Cron (UTC) | Queue |
|---|---|---|---|
| sentiment-worker | `sentiment.run_sentiment_worker` | `*/15` 14-21 Mon-Fri | inference |
| regime-detector | `regime.detect_regime` | 07:00 Mon-Fri | inference |
| regime-detector-premarket | `regime.detect_regime` | 13:30 Mon-Fri (safety net) | inference |
| poll-telegram-updates | `telegram_poller.poll_telegram_updates` | every 5s (always) | inference |
| pead-ingestion | `pead_worker.run_pead_ingestion_worker` | `5,35` 14-21 Mon-Fri | inference |
| run-news-ingestion | `ingestion.run_news_ingestion_worker` (GDELT) | `*/15` 14-21 Mon-Fri | celery |
| run-alpaca-ingestion | `ingestion.run_alpaca_ingestion_worker` | `*/15` 14-21 Mon-Fri | celery |
| run-execution | `execution.run_execution_worker` | `*/15` 14-21 Mon-Fri (inert in default `portfolio` engine) | celery |
| portfolio-cycle | `portfolio_scheduler.run_portfolio_cycle` | `7,22,37,52` 14-21 Mon-Fri | celery |
| reconcile-fills-intraday | `performance.run_reconcile_fills_intraday` | `12,27,42,57` 14-21 Mon-Fri | celery |
| reconcile-fills-evening | `performance.run_reconcile_fills_intraday` | 21:30 Mon-Fri | celery |
| forward-return-worker | `performance.run_forward_return_worker` | 22:00 daily | celery |
| loss-feedback-check | `performance.run_loss_feedback_check` | `*/30` 14-21 Mon-Fri | celery |
| counterfactual-worker | `performance.run_counterfactual_worker` | 22:45 daily | celery |
| performance-daily | `performance.run_daily_report` | 03:00 daily | celery |
| performance-weekly | `performance.run_weekly_weights` | 04:00 Monday | celery |
| drift-detection | `performance.run_drift_detection` | 04:30 Sunday | celery |
| check-suggestion-expiry | `performance.check_suggestion_expiry` | 05:00 daily | celery |
| run-retention-sweep | `retention.run_retention_sweep` | 03:30 daily | celery |
| decay-monitor | `decay_monitor_task.run_decay_check` | 21:00 daily | celery |
| risk-monitor | `risk_monitor_task.compute_risk_report` | 22:30 daily | celery |
| earnings-pead | `earnings_pead_worker.run_earnings_pead_worker` | :10 hourly 11-23 Mon-Fri | celery |

**Registered tasks NOT in beat (env-gated / ad-hoc):** `run_marketaux_ingestion_worker`, `run_finnhub_ingestion_worker`, `run_sec_edgar_ingestion_worker`, `run_rss_ingestion_worker` (all disabled), `run_gdelt_doc_ingestion_worker`, `run_news_stream` (ad-hoc + `__main__`), `check_and_apply_weights` (manual/API), `run_daily_trading_analysis` (removed from beat — replaced by external scheduled session).

## 3. Application flows

### Flow A — News → Sentiment (`src/workers/ingestion.py`, `sentiment.py`, `connectors/*`)
Connectors fetch (GDELT GKG + Alpaca news; MarketAux/RSS/SEC-news disabled, env-gated) → `TickerExtractor` (PG `ticker_lookup`; Alpaca path skips, metadata already carries tickers) → `Deduplicator` (Redis `dedup:id:*` + `dedup:content:*:*`, SET NX 4h) → `RPUSH news:queue` → `run_sentiment_worker` (`sentiment.py:417`): crash-recovery `lmove` queue→processing → stale-skip (>2h `MAX_NEWS_AGE_HOURS`) → **ticker resolver (shadow + conservative enforce: drops `NO_TRADE_NOT_TRADABLE` before inference)** → `sanitize_text` → DK-CoT prompt → `run_ensemble_query` (asyncio.gather over Ollama clients, Redis semaphore slots=2) → `EnsembleAggregator.aggregate` (eligible conf≥0.4; divergence std≥**0.40** → fallback) → **3 FinBERT fallback paths** (timeout / divergence / budget-exhausted) → `score = polarity × confidence` → write PG `sentiment_signals` + `news_log` + `llm_responses`; Redis `signal:{sym}:sentiment` (4h TTL) + `signal:{sym}:history`. Cited: `sentiment.py:136-255`, `ensemble.py:222-278`, `finbert.py:117`.

### Flow B — Portfolio cycle (active order path) (`portfolio_scheduler.py:766`, beat `:07/:22/:37/:52` 14-21 UTC)
engine guard (`portfolio` only) → Redis cycle lock `portfolio:cycle:lock` NX EX **1200s** → kill-switch (fail-closed if Redis down) → `StrategyRegistry` (YAML + PG `strategy_lifecycle` override + approval gate; active = S1 50% + S4 10%) → Alpaca market-clock + account preflight → price bars (Alpaca IEX daily + snapshot refresh; no yfinance) → drawdown cap (Redis `portfolio:peak_equity`; ≥5% → killswitch) → load positions into `VirtualPortfolio` → sentiment-reversal sells + stop-loss precompute → build S1 (`TimeSeriesMomentum`, monthly rebalance) + S4 (`NewsDrivenTactical`: `fetch_signals_for_cycle` with **event-time gate on `published_at` ≤ 2h**, `DISTINCT ON (symbol)` preferring ensemble over fallback, freshness ≤4h, feedback `entry_threshold` filter → SKIP_THRESHOLD rows, signal velocity from `signal:{sym}:history`) → `PortfolioOrchestrator.run_cycle` (merge `sleeve_weight × allocation_pct`, delta orders, **VolTargeter before Enforcer**, 5-pass `ConstraintEnforcer` ≤10 iterations) → post-filters (stop-loss drop, **hold-minimum 90min** SELL filter, exit hysteresis via `portfolio:exit_count:*`, pyramiding guard fail-closed) → regime multiplier from `regime:current` (fallback `macro:vix:latest` → VIX mapping → 0.2) → idempotency (`s4:fired_signals:{date}`, fail-closed) → submit Alpaca market orders → write PG `execution_decisions` + `trades` (BUY immediately, B28) + `portfolio_cycles` → divergence alert (Jaccard<0.8 / fill-ratio delta>0.20). Cited: `portfolio_scheduler.py:766-2388`, `orchestrator.py:75-229`, `constraints.py:74-294`.

### Flow C — Legacy execution (`execution.py:815`, beat `*/15`; active only when `engine=legacy_sentiment`)
engine guard → account fetch → regime × `feedback:regime_scale` → kill-switch → `feedback:entry_threshold` (default 0.30) → EMA20 cache (Alpaca IEX hourly) → open positions + pending orders → drawdown cap (code fallback **10%** if config read fails) → per-symbol: read `signal:{sym}:sentiment` → stop-loss `close_position`+`close_trade`+postmortem → freshness (30min) → **BUY gate: score > threshold AND price > EMA20** (only path with an EMA gate) → sizing `portfolio_value × max_position_pct × regime_mult` → cycle cap 20% → submit OTO bracket → write `execution_decisions` + `trades` → `_maybe_postmortem` (loss≥3% or ≥2% with low conf/high std → `diagnose_loss` → `trades.postmortem_diagnosis`). Cited: `execution.py:316-767`.

### Flow D — Performance loop (`performance.py`)
daily 03:00 IC (B4 = 0.5·Spearman+0.3·hit-rate+0.2·(1−Brier)) + Newey-West ICIR + drift → Telegram, Redis `performance:latest_report`; weekly Mon 04:00 LOO ICIR → weight suggestion → guardrail cascade `check_and_apply_weights` (G1-G4) → `ensemble:weights:current` + PG `weight_update_log`; 22:00 forward-return from Alpaca daily bars → `sentiment_signals.forward_return`; **Phase B** `*/30` loss-feedback → Redis `feedback:entry_threshold/regime_scale/state` (48h TTL); **Phase C** 22:45 counterfactual 1h return for SKIP_THRESHOLD/SKIP_EMA/SKIP_CAP → `execution_decisions.counterfactual_return_1h`; Sun 04:30 drift (PSI+CUSUM). Cited: `performance.py:689-1886`, `ic.py`, `weights.py`, `drift.py`.

### Flow E — Regime (`regime.py:139`, beat 07:00 + 13:30 premarket)
FRED VIX + T10Y2Y (+ CSV fallback) + yfinance SPY-20d → cache `macro:vix:latest` (72h) → own LLM pair (kimi+qwen, NOT `ensemble.py`) → consensus or conservative-pick → multipliers `bull 1.0 / sideways 0.7 / bear 0.4 / high_vol 0.2` → Redis `regime:current` (JSON `RegimeState`, 72h) + `qc:sizing_multiplier`. Consumers: portfolio scheduler + execution worker (× `feedback:regime_scale`). Cited: `regime.py:139-332`, `macro.py`.

### `execution.engine` effect (`config/trading.yaml`)
`portfolio` → only portfolio-cycle submits; `legacy_sentiment` → only run-execution; `disabled` → neither. Default config value is `portfolio`. Both `_load_execution_engine` helpers diverge on fallback defaults (portfolio-side→`portfolio`, execution-side→`legacy_sentiment`), so a missing YAML would make both paths active.

## 4. Persistence & state

### Redis (code is source of truth — §4 of ARCHITECTURE.md is materially stale)
`signal:{sym}:sentiment` (4h), `signal:{sym}:history` (last 5), `signal:{sym}:pead_event` (30d), `killswitch_active` + `killswitch_reason`, `system:halted_by_operator` (+reason, permanent), `regime:current` (72h), `qc:sizing_multiplier` (72h), `macro:vix:latest`, `ensemble:weights:current` (30d) / `:suggestion` (7d) / `:suggestion:snapshot`, `feedback:entry_threshold|regime_scale|state` (48h), `portfolio:cycle:lock` (1200s), `portfolio:peak_equity`/`portfolio:value`/`portfolio:exit_count:*`, `s4:fired_signals:{date}`/`s4:logged_stale_signals`, `stop_loss_today:*`, `fallback:consecutive:count`/`fallback:alert_sent`, `ensemble:divergence:log`, `budget:exhausted`, `news:queue`/`news:processing`, `dedup:id:*`/`dedup:content:*:*` (4h), `pead:processed:*`, `telegram:poller:offset`, `system:mode`, `config:sentiment_llm_models`, `performance:latest_report`/`performance:weekly_report`, `counterfactual:worker:last_run`, `overnight_alert:*`. Cited: `src/store/redis_store.py`, `deduplicator.py`, `portfolio_scheduler.py`.

### PostgreSQL (22 tables, migrations 001–033)
`sentiment_signals` (+`forward_return`,`published_at`,`news_log_id`), `news_log` (+`content_hash`,`extraction_method`,`raw_ingested_at`,`discarded_reason`), `llm_responses`, `llm_budget`, `execution_decisions` (+`reason`,`counterfactual_return_1h`), `trades` (+`postmortem_diagnosis`, full cost breakdown), `portfolio_cycles`, `risk_reports`, `decay_reports`, `pead_signals`, `strategy_lifecycle`, `strategy_lifecycle_audit`, `news_labels`, `news_resolved_entities`, `ingestion_stats_daily`, `weight_update_log`, `backtest_signals`, `ticker_lookup`, `audit_log`, `fallback_counters`, `performance_metrics`, `option_chains`, `zeygos_scores`. Cited: `migrations/`, `src/store/pg_store.py`.

### State machines / invariants
- **strategy_lifecycle** (`promotion.py`): ordered `disabled < research < paper < supervised_paper < live`; two-phase request→approve; sequential-only; `live` needs `GLOBAL_LIVE_PROMOTION_ENABLED` (currently **False**); `gate_report_id` required; demotion always allowed; every transition → immutable `strategy_lifecycle_audit`; `is_strategy_operationally_approved` fail-closed on DB error.
- **Kill-switch**: two OR-ed keys — `killswitch_active` (TTL-based, drawdown auto-trigger 18h TTL) vs `system:halted_by_operator` (permanent, explicit clear).
- **Loss feedback (Phase B)**: 3 Redis keys 48h TTL → auto-expire across restarts (no persistent ratchet); trigger = N consecutive losses OR rolling-PnL drawdown; cooldown via `feedback:state.last_adjustment_ts`; recovery/decay steps.
- **Cycle lock**: `SET NX EX 1200` with UUID token + Lua compare-and-delete; fail-open on Redis lock error (logs + proceeds), but kill-switch check below it fails **closed**.

## 5. External integrations

| System | Module | Lib | Data in→out | Gated |
|---|---|---|---|---|
| Alpaca (broker) | `portfolio_scheduler.py:837,918`; `execution.py:829` | `alpaca-py` `TradingClient` | orders→, account/positions/snapshots← | enabled; `ALPACA_PAPER_MODE=true` default |
| Alpaca (bars) | `portfolio_scheduler.py:982`; `execution.py:245` | `alpaca-py` `StockBarsRequest` (IEX) | EMA/bars← | with broker |
| Alpaca (news) | `connectors/alpaca_news.py` | aiohttp | Benzinga news→`NewsItem` (tickers pre-tagged) | with creds |
| Ollama cloud LLM | `llm/client.py:686` | aiohttp, Bearer | sanitized text→LLM JSON | `OLLAMA_API_KEY` req; active pair via `get_llm_models`→LOO ICIR |
| FinBERT (fallback) | `llm/finbert.py:96` | transformers + torch int8 | text→`FinBERTResult` | always available, no gate |
| GDELT GKG | `connectors/gdelt_gkg.py` | aiohttp (CSV) | 27-col TSV→`GKGNewsItem` | enabled, beat `*/15` 14-21 |
| SEC EDGAR (news) | `connectors/sec_edgar.py` | aiohttp | 8-K/10-Q→`NewsItem` | disabled (`SEC_EDGAR_INGESTION_ENABLED`); but 8-K path **live** via `pead_worker.py` |
| SEC `company_tickers` / OpenFIGI | `ticker_resolver_providers.py` | httpx | name↔ticker, FIGI mapping→resolver evidence | `SEC_USER_AGENT` req; OpenFIGI key optional; fail-open |
| FRED + yfinance (regime) | `connectors/macro.py` | httpx / yfinance | VIX, T10Y2Y, SPY-20d→ | FRED key optional (CSV fallback); enabled |
| Finnhub (earnings) | `connectors/earnings_calendar.py` | aiohttp | calendar→`EarningsEvent` w/ surprise | `FINNHUB_API_KEY` req; enabled `:10` hourly |
| Telegram | `notifications/telegram.py`; `telegram_poller.py` | httpx Bot API | alerts→, approve/reject callbacks← | token/chat optional (no-op if absent); `TELEGRAM_ALLOWED_USER_IDS` |
| MarketAux / RSS / Finnhub-news | `connectors/{marketaux,rss,finnhub_news}.py` | aiohttp | news→ | **disabled** (env flags) |

**LOO ICIR active-pair selection**: `get_llm_models()` (Redis `config:sentiment_llm_models` → env → `"all"`) → `compute_purified_icir` (baseline − leave-one-out) → `compute_new_weights` (softmax, 0.10 floor, guardrails) → `ensemble:weights:current` (only on full guardrail pass; fresh deploy falls back to `:suggestion` so weights apply before formal Telegram approval). Cited: `weights.py:13-96`, `sentiment.py:473-508`.

## 6. Trust boundaries & input sanitization

**Untrusted entry → validation:**
- News text (all sources) → `sanitize_text` at fetch + re-sanitize before prompt.
- Free-text tickers (RSS bare words, GDELT orgs) → **cashtag/ambiguity guard** (bare ambiguous tickers only via `$cashtag`; bare-word match needs len≥3 and not in `_AMBIGUOUS_WORD_TICKERS`; reliable paths bypass) → **deterministic resolver**.
- LLM JSON output → `parse_json_response` → Pydantic `LLMSentimentOutput` (bounded polarity/confidence/materiality/novelty; **schema has NO trading-action field**, only signal features).
- `model_id` → `ALLOWED_MODEL_IDS` frozenset allowlist; `_validate_model_id` raises before subprocess/HTTP (command-injection guard); errors sanitized via `_sanitize_error_output`.

**The sanitize → resolve → enforce chain:**
1. **Sanitize** (`text/sanitizer.py`): NFKC → strip invisible/Cf/Cc/Cs/Co (ZWSP/ZWJ/ZWNJ/BOM) → strip BiDi overrides (U+202E/D/C, U+2067-9) → strip emoji → whitespace normalize. `sanitize_ticker`: NFKD + ASCII-ignore + strip non-`[A-Z0-9]` (defeats Cyrillic homoglyphs).
2. **Resolve** (`ticker_resolver.py` pure core + `ticker_resolver_providers.py` I/O): design boundary — "LLMs/extractors PROPOSE, this module DECIDES, pure & deterministic, no I/O." Weighted evidence: source_ticker 0.30 + alias 0.25 + sec/openfigi 0.20 + llm_agreement 0.15 (boost only) + tradable 0.10. Gates: confidence≥0.80, ambiguity_margin≥0.15, tradable, directness≠unclear → `RESOLVED` or `NO_TRADE_*`. Providers are **fail-open** (outage lowers confidence, never fabricates).
3. **Enforce** (`resolver_shadow.py` + `sentiment.py:84-95`): currently **shadow + conservative-enforce** (QX-01 "measurement before enforcement"). Shadow verdicts → `news_resolved_entities` without gating. Only `NO_TRADE_NOT_TRADABLE` enforced (env `RESOLVER_ENFORCE_NOT_TRADABLE=1`); finer gates (`LOW_CONF`, `AMBIGUOUS`) remain observational pending golden-label calibration.

**Boundary principle**: the LLM never decides a ticker; it only proposes. A wrong ticker (order on an unrelated stock) is treated as the worst-case error, so resolution is deterministic and separate from sentiment.

## 7. Invariants

| # | Invariant | Status | File |
|---|---|---|---|
| 1 | LLM never in hot path | **Enforced** — no `import src.llm.*` in execution/portfolio; signals read from PG | `portfolio_scheduler.py:1358,2003` |
| 2 | `allocation_pct` is sole capital lever | **Partially false** — regime multiplier (×0.2–×1.0), vol-targeter (≤2.0×), constraint caps also scale; regime ×0.2 is currently the dominant throttle (~10% deployment vs ~50% design) | `orchestrator.py:138,173,221`; `constraints.py:63` |
| 3 | Sleeve-local weights (fraction-of-sleeve) summed after ×`allocation_pct`; startup guard sum(enabled)≤1.0, S4≤10% | **Enforced** | `orchestrator.py:53,131`; `registry.py:219-232` |
| 4 | One signal per symbol per cycle, ensemble preferred | **Enforced** in SQL `DISTINCT ON (symbol) ... ORDER BY symbol, fallback_used ASC, generated_at DESC` | `pg_store.py:1711` |
| 5 | SELL filtered for recent buys | **Enforced, threshold = 90 min** (not 30); stop-loss/reversal SELLs bypass | `portfolio_scheduler.py:664,1190` |
| 6 | Cycle lock prevents concurrent runs | **Enforced** (NX EX 1200s, UUID + Lua C-A-D); fail-open on lock error, fail-closed on kill-switch | `portfolio_scheduler.py:658,801` |
| 7 | Live trading not authorized | **Enforced, multi-layer** — `GLOBAL_LIVE_PROMOTION_ENABLED=False`, `ALPACA_PAPER_MODE=true`, registry rejects `S4.mode=="live"`, all `promotion_blocked`; approval gate fail-closed **but fail-open for strategies with no lifecycle row** | `promotion.py:27`; `config.py:138`; `registry.py:238`; `portfolio_scheduler.py:108-122` |
| 8 | `execution.engine` gates which path orders | **Enforced** | `trading.yaml:125`; `portfolio_scheduler.py:770`; `execution.py:832` |
| 9 | Ensemble failure never blocks orders → FinBERT fallback | **Enforced** (timeout/divergence std≥0.40/budget) | `ensemble.py:190,278`; `sentiment.py:188-255` |

## 8. Module dependencies

```
workers → config, store, connectors, llm, models, portfolio, strategies,
          performance, notifications, monitoring, backtest.engine, costs, text
api → config, store, strategies(registry+promotion), llm(model_registry), analytics
api.routes → store, api.deps, api.auth, api.jwt_utils, config, strategies, llm, analytics
portfolio → backtest.engine, portfolio(self), strategies(registry, TYPE_CHECKING)
strategies → models, data.options, options, connectors(cashtag), strategies(self)
strategies.registry → strategies.s1/s2/s4 (lazy imports — avoid cycles)
connectors → connectors(self), models, text, config
llm → config, models, text
store → config, models, costs (pg_store)
backtest.engine → backtest.engine(self), portfolio(types, TYPE_CHECKING)
workers.performance → performance, store, models, notifications, workers.execution (ENTRY_THRESHOLD symbol import)
```
- `models` is a true leaf (imported by many, imports nothing cross-package).
- No import cycles. Notable edge: `workers.performance` imports `workers.execution.ENTRY_THRESHOLD` (symbol-level, not a task call). Live portfolio engine **reuses backtest engine primitives** (`VirtualPortfolio`, `MarketSnapshot`, `OrderSide`).

## 9. Doc/code drift (observations, not prescriptions)

The code is the source of truth; `docs/ARCHITECTURE.md` lags the code in several places:

1. **`AlpacaBroker` does not exist** — CLAUDE.md/ARCHITECTURE.md say "Use `AlpacaBroker` in `src/brokers/ibkr_adapter.py`"; the file has only `IBKRAdapter`. Alpaca orders go through direct `alpaca-py` calls in `execution.py`/`portfolio_scheduler.py`. (`src/brokers/ibkr_adapter.py:42`)
2. **Sentiment Redis key reversed** — docs `sentiment:signal:{sym}`; code `signal:{sym}:sentiment`. (`redis_store.py:92`)
3. **Ensemble divergence 0.30 → 0.40** — docs/ensemble docstrings still say 0.30; runtime is `ENSEMBLE_DIVERGENCE_STD=0.40` (raised 2026-07-09). (`config.py:179`, `sentiment.py:460`)
4. **Regime Redis keys** — docs `regime_multiplier`+`regime_label`; code uses single `regime:current` JSON + `qc:sizing_multiplier`. (`redis_store.py:541`)
5. **Hold-minimum 30→90 min** — docs say 30; code `_HOLD_MINIMUM_MINUTES=90`. (`portfolio_scheduler.py:664`)
6. **Cycle lock TTL 840→1200s** — docs EX 840; code 1200. (`portfolio_scheduler.py:659`)
7. **`recovery_win_streak` 5→3** — docs 5; code/trading.yaml 3. (`trading.yaml:195`)
8. **S4 EMA20 gate** — docs "BUY gate: score>0.3 AND price>EMA20"; the portfolio path has **no EMA filter** (hardcodes `ema_pass=True`); EMA20 gate exists only in legacy execution. (`s4/ranking.py`; `portfolio_scheduler.py:1439`)
9. **Regime label vocabulary mismatch** — `RegimeDetector` uses `bull/sideways/bear/high_vol`; legacy `_regime_label()` maps the same ranges to `high_vol/risk_off/uncertain/risk_on`. (`regime.py:272` vs `execution.py:316`)
10. **EMA20 data source** — docs "yfinance, IEX"; code uses Alpaca IEX only (yfinance only in `macro.py` SPY momentum + backtest loader). (`execution.py:234`)
11. **Drawdown code fallback 10%** — config is 5% (matches docs); code fallback `MAX_DRAWDOWN_PCT=0.10` if config read fails. (`execution.py:57`)
12. **LLM budget store** — docs §4 list Redis `llm:budget:{MODEL}:{DATE}`; actual budget is PG `llm_budget` + Redis `budget_exhausted` flag. (`budget.py`, `pg_store.py`)
13. **Ingestion env flags** (`MARKETAUX/FINNHUB/SEC_EDGAR/RSS_INGESTION_ENABLED`) are referenced in beat comments but not declared as `Settings` fields in `config.py` — checked inside task bodies.
14. **SEC EDGAR partially live** — news-sentiment path disabled, but 8-K connector is active for the (shelved) S7 PEAD pipeline. (`pead_worker.py:19`)

## 10. Areas not yet fully comprehended

- **`ConstraintEnforcer` sector & correlation passes**: `_enforce_sector_exposure` is a no-op in the portfolio path (no `sector_map` passed → never binds); `_enforce_correlation_cluster` needs a correlation matrix the live path may not supply. Net effect on real constraints vs the 3 active passes (single-asset, strategy-exposure, portfolio-exposure) is unverified. (`constraints.py:252,294`)
- **VolTargeter real effect**: `PortfolioVolTargeter` is instantiated and runs before the enforcer, but `strategy_returns` provenance/quality at runtime (whether it carries meaningful per-cycle returns) is unclear — doc §8 once listed it as "not active" then "resolved." (`portfolio_scheduler.py:1136-1145`)
- **Idempotency asymmetry**: `s4:fired_signals:{date}` idempotency is S4-only; S1 BUYs are not covered by the same fired-signal guard — whether S1 relies solely on the pyramiding/position check is unconfirmed. (`portfolio_scheduler.py:649,1511`)
- **`combiner.py` / `risk_parity.py`**: an alternative aggregation path (`PortfolioCombiner` + `RiskParityAllocator`) exists but is not used by the active orchestrator — relationship/plan is unclear.
- **`zeygos_scores` / Telegram PDF ingestion**: the Zeygos analyst-score universe and PDF parsing (`zeygos_parser.py`, `telegram_poller.py`) are wired into PG and the poller, but their role in the live cycle (universe source for a strategy?) is not traced end-to-end.
- **Approval-gate fail-open**: strategies lacking a `strategy_lifecycle` row are admitted by default — which strategies actually have rows vs not (at runtime) wasn't enumerated. (`portfolio_scheduler.py:108-122`)
- **Quality / labeling closed loop**: the QX-01 rails (`news_labels`, `news_resolved_entities`, Quality dashboard, `/labeling`) are built but the enforcement→calibration→gate step is still pending; the exact state of annotation coverage and whether any finer `NO_TRADE_*` gate is close to activation is not pinned down.
- **`run-execution` is scheduled but inert** in the default `portfolio` engine — it runs every 15 min during market hours and returns early; operational cost/noise is unquantified.