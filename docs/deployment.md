# Alembic — Deployment Guide

Step-by-step guide for deploying Alembic to a VPS or cloud instance for paper trading and live trading.

---

## Prerequisites

- Ubuntu 22.04+ (or equivalent Linux)
- Docker 24+ and Docker Compose v2
- Python 3.11+ (for running tests locally)
- Git

---

## Environment Variables

Create `.env` in the project root. All required variables must be set before starting services.

```bash
cp .env.example .env
# Edit .env with your credentials
```

### Required

| Variable | Description |
|----------|-------------|
| `ADMIN_API_KEY` | API key for admin endpoints (min 32 chars; generate with `openssl rand -hex 20`) |
| `DATABASE_URL` | PostgreSQL connection string: `postgresql://trading:trading@postgres:5432/trading` |
| `REDIS_URL` | Redis URL: `redis://redis:6379/0` |
| `ALPACA_API_KEY` | Alpaca API key (from Alpaca dashboard) |
| `ALPACA_SECRET_KEY` | Alpaca secret key |

### Broker

| Variable | Default | Description |
|----------|---------|-------------|
| `ALPACA_BASE_URL` | `https://paper-api.alpaca.markets` | Use paper URL for paper trading |

### Notifications (optional but strongly recommended)

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | From @BotFather |
| `TELEGRAM_CHAT_ID` | Group or channel ID for alerts |
| `TELEGRAM_ALLOWED_USER_IDS` | Comma-separated IDs allowed to approve weights |

### LLM Ensemble

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama cloud or local endpoint |
| `LLM_DAILY_BUDGET_USD` | `50.0` | Daily token spend cap |

### FRED / Macro Data

| Variable | Description |
|----------|-------------|
| `FRED_API_KEY` | FRED API key for VIX and T10Y2Y data |

### Operational

| Variable | Default | Description |
|----------|---------|-------------|
| `WATCHLIST_SYMBOLS` | — | Comma-separated symbols for ExecutionWorker (e.g. `AAPL,NVDA,MSFT,GOOGL`) |
| `AUTO_APPLY_ENABLED` | `true` | Auto-apply weight suggestions when guardrails pass |
| `AUTO_APPLY_VIX_THRESHOLD` | `30.0` | Block auto-apply when VIX ≥ threshold |
| `GLOBAL_LIVE_PROMOTION_ENABLED` | `false` | **Must remain `false`.** Controls whether `StrategyRegistry` and `src/strategies/promotion.py` permit any strategy to transition to `live` mode. **Never set to `true` without explicit PO sign-off, P2-05 closure, and Kimi P2 Acceptance Audit completion.** |

---

## Database Initialisation

The PostgreSQL schema requires all migrations applied in order. The schema has grown through at least migration 026 (P1-10 strategy_lifecycle_audit). Do not apply only `001_initial.sql` — later migrations add required tables and columns.

```bash
# Apply ALL migrations in order
docker compose up -d postgres

for f in $(ls migrations/*.sql | sort); do
  echo "Applying $f..."
  docker compose exec postgres psql -U trading -d trading -f /dev/stdin < "$f"
done

# Verify key tables exist
docker compose exec postgres psql -U trading -d trading \
  -c "\dt" | grep -E "sentiment|llm|news|weight|portfolio|risk|decay|trades|execution_decisions|pead_signals|strategy_lifecycle"
```

Current schema includes tables: `sentiment_signals`, `llm_responses`, `news_log`, `weight_update_log`, `backtest_signals`, `portfolio_cycles`, `risk_reports`, `decay_reports`, `execution_decisions`, `trades`, `pead_signals`, `strategy_lifecycle`, `strategy_lifecycle_audit`.

---

## First Deployment

```bash
# 1. Clone and enter directory
git clone https://github.com/your-org/Alembic.git
cd Alembic
cp .env.example .env
# Edit .env

# 2. Build images
docker compose build

# 3. Start infrastructure services first
docker compose up -d postgres redis
sleep 10  # wait for health checks

# 4. Apply database schema
docker compose exec postgres psql -U trading -d trading -f /dev/stdin < migrations/001_initial.sql

# 5. Start application services
docker compose up -d api worker beat frontend

# 6. Verify all services healthy
docker compose ps
```

---

## Verifying the Deployment

```bash
# API health
curl http://localhost:8001/api/health
# Expected: {"status": "healthy", "redis": "connected", "postgres": "connected"}

# Check operating mode (default: not set)
curl http://localhost:8001/api/admin/status
# Expected: {"killswitch": false, "mode": "unknown", "llm_models": "all"}

# Set paper trading mode
curl -X POST http://localhost:8001/api/admin/mode \
  -H "X-API-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"mode": "paper"}'

# Verify beat schedule is running
docker compose exec beat celery -A src.workers.celery_app inspect scheduled
```

---

## Update Deployment

```bash
# Pull latest changes
git pull origin main

# Rebuild images (only services that changed)
docker compose build api worker beat

# Rolling restart
docker compose up -d --no-deps api worker beat

# Verify
docker compose ps
curl http://localhost:8001/api/health
```

---

## Health Checks

All services have Docker health checks defined in `docker-compose.yml`:

| Service | Check | Interval |
|---------|-------|---------|
| `postgres` | `pg_isready -U trading` | 5s |
| `redis` | `redis-cli ping` | 5s |
| `api` | `GET /api/health` HTTP 200 | 10s |

Services marked `depends_on: condition: service_healthy` will not start until dependencies pass health checks.

---

## Rollback

```bash
# Revert to previous git commit
git log --oneline -5  # find the target commit hash
git checkout <previous-hash>

# Rebuild and redeploy
docker compose build api worker beat
docker compose up -d --no-deps api worker beat

# Verify rollback
docker compose ps && curl http://localhost:8001/api/health
```

If the database schema changed (new migration), rollback may require restoring a database backup. Always snapshot `pgdata` volume before applying migrations.

---

## Backup and Restore

```bash
# Backup PostgreSQL data
docker compose exec postgres pg_dump -U trading trading > backup-$(date +%Y%m%d).sql

# Backup Redis snapshot
docker compose exec redis redis-cli SAVE
docker cp $(docker compose ps -q redis):/data/dump.rdb redis-backup-$(date +%Y%m%d).rdb

# Restore PostgreSQL
docker compose exec postgres psql -U trading trading < backup-20260603.sql
```

---

## Production Security Checklist

Before going live on a real brokerage account:

- [ ] Rotate `ADMIN_API_KEY` (never use a dev key in production)
- [ ] Set `ALPACA_BASE_URL` to the live endpoint (not paper)
- [ ] Restrict `TELEGRAM_ALLOWED_USER_IDS` to authorised operators only
- [ ] Verify `.env` is not committed to git (`git status` shows `.env` under `.gitignore`)
- [ ] Set `AUTO_APPLY_ENABLED=false` for first week of paper trading (manual weight approval)
- [ ] Test kill-switch works: `POST /api/admin/killswitch`, verify mode=halted in Redis
- [ ] Confirm Telegram alerts are received (deploy sends test alert)
- [ ] Verify drawdown cap: `risk.portfolio_drawdown` in `config/trading.yaml` (production value **5%**, single source of truth — B13), monitor first session
- [ ] Verify `GLOBAL_LIVE_PROMOTION_ENABLED=false` in `.env` (must remain `false` until PO sign-off + P2-05 closure + Kimi P2 Audit complete)
- [ ] Verify `GET /api/system/readiness` returns all-healthy before first session
- [ ] Apply all migrations 001–026+ (not just `001_initial.sql`)

---

## CI Gates

`.github/workflows/ci.yml` runs on every push and PR to `main`.

| Check | Blocking? | Notes |
|-------|-----------|-------|
| `ruff` lint | **Yes** | Failing ruff blocks merge |
| `pytest` full suite | **Yes** | Failing tests block merge |
| Coverage (`fail_under=60`) | **Yes** | Coverage below 60% blocks merge |
| `mypy` type check | No (soft) | `continue-on-error: true` — informational until type-annotation cleanup pass |
| `pip-audit` dependency audit | No (soft) | `continue-on-error: true` — torch/transformers CVEs tracked separately |
| `gitleaks` secret scan | No (soft) | `GITLEAKS_FAIL: false` — verify baseline before enabling hard fail |

The three soft gates are **temporary**. They must be made blocking after:
- `mypy`: after a dedicated type-annotation cleanup pass (P3 scope)
- `pip-audit`: after each known CVE is patched or explicitly accepted
- `gitleaks`: after confirming no real secrets exist in git history
