# Alembic — Operations Guide

Day-to-day operational reference for running, monitoring, and troubleshooting the system.

---

## Docker Compose Services

| Service | Port | Role |
|---------|------|------|
| `postgres` | 5432 | PostgreSQL 16 (trading database) |
| `redis` | 6379 | Redis 7 (signal cache, task queue) |
| `api` | 8001→8000 | FastAPI application |
| `worker` | — | Celery worker (queue `celery`, concurrency=4 — task generici) |
| `worker-inference` | — | Celery worker (queue `inference`, concurrency=1 — FinBERT/Ollama/PEAD) |
| `beat` | — | Celery beat (task scheduler) |
| `frontend` | 3000→80 | React dashboard (Nginx) |
| `grafana` | 3001→3000 | Grafana dashboards |
| `backtest` | — | One-shot backtest runner (profile: backtest) |

### Common Commands

```bash
# Start all services
docker compose up -d

# Rebuild and restart (after code changes)
docker compose build api worker worker-inference beat frontend
docker compose up -d api worker worker-inference beat frontend

# View logs (follow)
docker compose logs -f worker
docker compose logs -f beat
docker compose logs -f api

# Stop all services
docker compose down

# Restart a single service
docker compose restart worker

# Run backtest (starts the backtest profile)
docker compose --profile backtest run --rm backtest \
  python scripts/run_backtest.py --start 2025-10-01 --end 2026-04-30 --run-id gkg-6m-v1
```

### Health Checks

```bash
# API health
curl http://localhost:8001/api/health

# PostgreSQL readiness
docker compose exec postgres pg_isready -U trading

# Redis ping
docker compose exec redis redis-cli ping

# Celery worker status
docker compose exec worker celery -A src.workers.celery_app inspect active
```

---

## Celery Beat Schedule

Beat schedules are defined in `src/workers/celery_app.py`. All times are UTC.

| Task name | Cron | Description |
|-----------|------|-------------|
| `run-news-ingestion` | */15 14-21 Mon-Fri | GDELT GKG → news:queue |
| `run-marketaux-ingestion` | */15 14-21 Mon-Fri | MarketAux → news:queue |
| `run-alpaca-ingestion` | */15 14-21 Mon-Fri | Alpaca/Benzinga → news:queue |
| `sentiment-worker` | */15 14-21 Mon-Fri | news:queue → LLM → Redis + PG |
| `run-execution` | */15 14-21 Mon-Fri | signals → Alpaca orders |
| `portfolio-cycle` | 0 14-21 Mon-Fri | PortfolioOrchestrator multi-strategy |
| `regime-detector` | 7:00 Mon-Fri | Macro → LLM pair → regime → Redis |
| `forward-return-worker` | 22:00 daily | Populate `forward_return` after close |
| `risk-monitor` | 22:30 daily | HHI + correlation + drawdown alerts |
| `performance-daily` | 3:00 daily | IC report + drift + Telegram digest |
| `drift-detection` | 4:30 Sunday | PSI + CUSUM over full window |
| `check-suggestion-expiry` | 5:00 daily | Expire stale weight suggestions |
| `performance-weekly` | 4:00 Monday | LOO ICIR → weight suggestion |
| `run-retention-sweep` | 3:30 daily | Old data cleanup |
| `decay-monitor` | 23:00 1st of month | Actual vs backtest baseline |
| `poll-telegram-updates` | every 5s | Process approve/reject callbacks |
| `run-sec-edgar-ingestion` | */30 14-21 Mon-Fri | SEC EDGAR 8-K filings → news queue |
| `pead-ingestion` | 5,35 14-21 Mon-Fri | Classifica 8-K via Ollama → pead_signals (queue: inference) |
| `loss-feedback-check` | */30 14-21 Mon-Fri | Phase B: detect loss patterns → adjust threshold/regime scale |
| `counterfactual-worker` | 22:45 daily | Phase C: compute 1h counterfactual returns for SKIP rows |
| `reconcile-fills-evening` | 21:30 Mon-Fri | Reconcile fill prices after NYSE close |

### Manual Task Triggering

```bash
# Trigger sentiment worker manually
docker compose exec worker celery -A src.workers.celery_app call \
  src.workers.sentiment.run_sentiment_worker

# Trigger regime detection now
docker compose exec worker celery -A src.workers.celery_app call \
  src.workers.regime.detect_regime

# Run forward-return worker immediately
docker compose exec worker celery -A src.workers.celery_app call \
  src.workers.performance.run_forward_return_worker

# Check scheduled tasks
docker compose exec beat celery -A src.workers.celery_app inspect scheduled
```

---

## Script Operativi

### Analisi giornaliera (cron 14:30 CEST, lun-ven)

```bash
scripts/daily_analysis.sh
```

Lancia Claude Code in modalità non-interattiva, analizza i dati del giorno precedente (trades, signals, decisions, log docker), invia report su Telegram. Log in `logs/daily_analysis_YYYY-MM-DD.log`.

Richiede `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` in `.env`.

Per aggiungere al crontab:
```bash
crontab -e
# Aggiungere: 30 12 * * 1-5 /path/to/scripts/daily_analysis.sh
# (12:30 UTC = 14:30 CEST)
```

---

## Redis Operations

```bash
# Connect to Redis CLI
docker compose exec redis redis-cli

# Read current signal for a symbol
GET sentiment:signal:AAPL

# Check kill-switch state
GET killswitch_active

# Check current operating mode
GET system:mode

# Read regime multiplier
GET regime_multiplier

# Read current ensemble weights
GET ensemble:weights:current

# Check LLM daily budget for a model
GET llm:budget:kimi-k2.6:cloud:2026-06-03

# View news queue depth
LLEN news:queue

# Manually set kill-switch
SET killswitch_active 1

# Manually clear kill-switch (use only after investigation)
SET killswitch_active 0

# Set paper trading mode
SET system:mode paper
```

---

## PostgreSQL Operations

```bash
# Connect to database
docker compose exec postgres psql -U trading -d trading

# Recent signals
SELECT symbol, score, confidence, generated_at
FROM sentiment_signals
ORDER BY generated_at DESC
LIMIT 20;

# IC by symbol over last 30 days
SELECT symbol,
       CORR(score, forward_return) AS ic,
       COUNT(*) AS n
FROM sentiment_signals
WHERE generated_at >= now() - INTERVAL '30 days'
  AND forward_return IS NOT NULL
GROUP BY symbol
ORDER BY ic DESC;

# Weight update history
SELECT source, applied_weights, freeze_reason, created_at
FROM weight_update_log
ORDER BY created_at DESC
LIMIT 10;

# Recent portfolio cycles
SELECT timestamp, strategies_run, orders_count, constraints_fired
FROM portfolio_cycles
ORDER BY timestamp DESC
LIMIT 10;

# Latest risk report
SELECT timestamp, nav, combined_drawdown, herfindahl_index,
       jsonb_array_length(alerts) AS n_alerts
FROM risk_reports
ORDER BY timestamp DESC
LIMIT 5;

# Backtest run summary
SELECT run_id,
       COUNT(*) AS total,
       COUNT(score) AS scored,
       AVG(score) AS avg_score
FROM backtest_signals
GROUP BY run_id
ORDER BY MIN(generated_at) DESC;
```

---

## Grafana Dashboards

Grafana runs on port 3001. Default credentials: `admin / alembic123`.

Anonymous read access is enabled — no login required for viewing.

### Dashboard provisioning

Dashboards are auto-provisioned from `grafana/dashboards/*.json`. To add a new dashboard:
1. Create/export the dashboard JSON from the UI
2. Save to `grafana/dashboards/your-dashboard.json`
3. Restart Grafana: `docker compose restart grafana`

### Data source

The Grafana PostgreSQL data source connects to the `trading` database at `postgres:5432`. Connection is configured in `grafana/provisioning/datasources/`.

### Key panels to watch during paper trading

- **Signal score distribution** — median score and std per day; watch for mean drift
- **IC rolling 30d** — information coefficient; should be consistently positive
- **Daily P&L** — from Alpaca paper account equity curve
- **Kill-switch events** — any unintended activations during overnight sessions
- **Sentiment queue depth** — `news:queue` LLEN; should drain to 0 within 15 min of each ingest

---

## Monitoring Alerts (Telegram)

Telegram alerts are sent to `TELEGRAM_CHAT_ID` via the bot token configured in `.env`.

| Alert type | Level | Trigger |
|-----------|-------|---------|
| Daily IC digest | INFO | Daily 03:00 PerformanceWorker |
| IC below threshold N consecutive days | CRITICAL | Circuit breaker fires |
| PSI > 0.25 (signal distribution drift) | CRITICAL | DriftDetector |
| Weight suggestion ready (guardrails passed) | INFO | Monday 04:00 |
| Weight approval required (guardrail blocked) | INFO | Inline [✅ Approve] [❌ Reject] |
| Drawdown cap reached (≥10% daily loss) | CRITICAL | ExecutionWorker |
| Decay metric CRITICAL | CRITICAL | DecayMonitor (monthly) |
| Risk alert (drawdown, weight drift) | WARNING | RiskMonitor (daily) |

---

## Troubleshooting

### Kill-switch stuck active

```bash
# Check who activated it
docker compose logs worker | grep "kill.switch"

# Clear manually after investigation
docker compose exec redis redis-cli SET killswitch_active 0
docker compose exec redis redis-cli SET system:mode paper
```

### News queue not draining

```bash
# Check queue depth
docker compose exec redis redis-cli LLEN news:queue

# Check sentiment worker logs
docker compose logs worker | grep "SentimentWorker\|sentiment" | tail -50

# Check if beat is running
docker compose ps beat
```

### No signals in Redis

1. Check `news:queue` has items (ingestion running?)
2. Check `system:mode` — if `halted`, no new signals written
3. Check `llm:budget:*` keys — daily budget may be exhausted
4. Check worker logs for LLM connection errors (Ollama cloud timeout)

### PostgreSQL connection pool exhausted

Symptom: `psycopg2.pool.PoolError: connection pool exhausted`

Cause: A worker process did not call `pg.close()` in its `finally` block.

Fix:
```bash
# Restart the worker to release all connections
docker compose restart worker

# Verify pool recovery
docker compose exec postgres psql -U trading -d trading \
  -c "SELECT count(*) FROM pg_stat_activity WHERE datname='trading';"
```

### FinBERT cold-start latency

First article in a new worker process triggers FinBERT model load from disk (~10–30s). This is normal. Subsequent calls in the same process reuse the loaded model.

### Alpaca order rejected

Common causes:
- `account not active` — paper account may need reactivation
- `insufficient buying power` — portfolio fully invested; position already held
- `asset not tradable` — symbol halted or delisted; system logs error and continues

Check logs: `docker compose logs worker | grep "Alpaca\|alpaca\|order" | tail -50`

### yfinance stale data

yfinance occasionally returns cached or incorrect data. If EMA20 values look wrong:
```bash
# Trigger an immediate regime detection with fresh data
docker compose exec worker celery -A src.workers.celery_app call \
  src.workers.regime.detect_regime
```
