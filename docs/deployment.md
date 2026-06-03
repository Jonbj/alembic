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

---

## Database Initialisation

The PostgreSQL schema must be applied before first run:

```bash
# Apply migration
docker compose up -d postgres
docker compose exec postgres psql -U trading -d trading -f /dev/stdin < migrations/001_initial.sql

# Verify tables exist
docker compose exec postgres psql -U trading -d trading \
  -c "\dt" | grep -E "sentiment|llm|news|weight|portfolio|risk|decay"
```

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
docker compose up -d api worker beat frontend grafana

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
- [ ] Verify drawdown cap: set `10%` as starting threshold, monitor first session
- [ ] Enable Grafana authentication for production (disable anonymous access)
