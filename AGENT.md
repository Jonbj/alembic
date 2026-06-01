# Alembic — Agent Briefing

This document gives you everything you need to interact with **Alembic**, an LLM-based algorithmic trading system, via its REST API.

---

## What is Alembic?

Alembic is an **offline-first sentiment trading system** built on the "Alpha Miner" paradigm:

- **News articles** are fetched from GDELT and RSS feeds, then analysed by an ensemble of LLMs (Kimi, Qwen, DeepSeek, GLM) using Domain Knowledge Chain-of-Thought prompting.
- Each article produces a **sentiment signal**: a score in `[-1.0, +1.0]` multiplied by model confidence, indicating bullish or bearish sentiment for a specific ticker.
- Signals are stored in a PostgreSQL database and read by the execution engine (Alpaca broker), which places buy/sell orders based on pre-configured thresholds.
- **LLMs are never called in the live trading path** — all inference happens asynchronously in background workers.

The system currently covers ~89 tickers (US mega-cap equities, ETFs, and international ADRs).

### Operating Modes

| Mode | Meaning |
|---|---|
| `backtest` | Historical signal evaluation only, no live orders |
| `paper` | Paper trading on Alpaca (no real money) |
| `semi_auto` | Live trading — human approval required for each order |
| `full_auto` | Live trading — fully autonomous |
| `halted` | All activity frozen (killswitch engaged) |

---

## API Access

**Base URL:** `http://localhost:8001`

**Authentication:** Every protected endpoint requires this HTTP header:

```
X-API-Key: eJvMeuHhJS27FPugKIu4qKGgV7roIdLfcv7h20MwuQg
```

Endpoints that do **not** require authentication: `GET /api/health`, `GET /api/admin/status`, `GET /api/config`, and all `/api/backtest/*` and `/api/performance/*` routes.

---

## Endpoint Reference

### Health

```
GET /api/health
```
Returns `{"status": "ok", "mode": "<current_mode>"}`. Use this to verify the system is up.

---

### System Status & Control

```
GET  /api/admin/status          → killswitch state, current mode, active LLM models
POST /api/admin/mode            → change operating mode
POST /api/admin/killswitch      → emergency stop (halts all trading)
POST /api/admin/llm-models      → change which LLM models are active
```

**Change mode example:**
```json
POST /api/admin/mode
Body: {"mode": "paper"}
```

**Change LLM models example:**
```json
POST /api/admin/llm-models
Body: {"models": "kimi,deepseek"}
```
Valid model names: `all`, `kimi`, `qwen`, `deepseek`, `glm` (comma-separated for subsets).

---

### Sentiment Signals

```
GET /api/signals                → latest signal for every watched ticker
GET /api/signals/{symbol}       → latest signal for one ticker (e.g. /api/signals/AAPL)
```

**Signal fields:**
| Field | Type | Meaning |
|---|---|---|
| `symbol` | str | Ticker symbol |
| `score` | float [-1, +1] | Sentiment score (negative = bearish, positive = bullish) |
| `confidence` | float [0, 1] | Model certainty |
| `reasoning` | str | DK-CoT chain-of-thought explanation |
| `model_id` | str | Which model/ensemble produced this |
| `ensemble_std` | float | Disagreement between ensemble members (high = uncertain) |
| `fallback_used` | bool | True if FinBERT fallback was triggered due to ensemble divergence |
| `generated_at` | ISO datetime | When the signal was produced |

**Interpretation guide:**
- `score > 0.3` → moderately bullish
- `score > 0.6` → strongly bullish
- `score < -0.3` → moderately bearish
- High `ensemble_std` (> 0.3) + `fallback_used: true` → conflicting models, lower reliability

---

### Positions & Orders (live/paper trading)

```
GET /api/positions              → all currently open positions on Alpaca
GET /api/orders?limit=50        → recent order history (filled + cancelled)
```

**Position fields:** `symbol`, `qty`, `market_value`, `unrealized_pl`, `unrealized_plpc`, `avg_entry_price`, `current_price`

**Order fields:** `id`, `symbol`, `side` (buy/sell), `qty`, `filled_avg_price`, `status`, `filled_at`, `submitted_at`

---

### News Feed

```
GET /api/news/recent?limit=100&ticker=AAPL&source=gdelt_gkg
```

Returns the most recent processed news articles. Filters:
- `ticker` — filter by specific symbol
- `source` — filter by news source (`gdelt`, `gdelt_gkg`, `rss`)
- `limit` — max 500

---

### LLM Feedback (per-article model outputs)

```
GET /api/llm/feedback?limit=50&ticker=NVDA&model_id=ensemble:kimi-k2.6:cloud
```

Shows the raw LLM reasoning and per-model sentiment for individual articles. Useful for auditing why a signal was generated.

---

### Performance & Weights

```
GET /api/performance/latest     → most recent IC/ICIR performance report with post-mortems
GET /api/performance/pnl?period=6M  → daily + monthly P&L history
GET /api/weights/current        → current ensemble model weights
GET /api/weights/suggestion     → system-recommended weight update (with expiry date)
POST /api/weights/approve       → apply weights (pass null to accept system suggestion)
```

**Weight approval example:**
```json
POST /api/weights/approve
Body: {"override_weights": null, "note": "accepting system suggestion"}
```

To override manually:
```json
{"override_weights": {"kimi-k2.6:cloud": 0.40, "deepseek-v4-pro:cloud": 0.35, "qwen3.5:cloud": 0.15, "glm-5.1:cloud": 0.10}, "note": "manual rebalance"}
```

Constraints: each weight must be in `[0.10, 0.70]` and all weights must sum to `1.0`.

---

### Backtest Analysis

All backtest endpoints are public (no API key needed). Completed runs: `gkg-nov25-v1`, `gkg-dec25-v1`, `gkg-jan26-v1`.

```
GET /api/backtest/runs                              → list all backtest runs
GET /api/backtest/{run_id}/summary                  → IC, ICIR, hit_rate, avg returns
GET /api/backtest/{run_id}/model_ic                 → per-model IC and hit rate
GET /api/backtest/{run_id}/symbol_ic                → per-ticker IC and hit rate
GET /api/backtest/{run_id}/bucket_analysis          → avg 24h return by score decile
GET /api/backtest/{run_id}/pnl_curve?threshold=0.05 → daily cumulative P&L curve
GET /api/backtest/{run_id}/signals?limit=200&offset=0&symbol=AAPL  → raw signals with pagination
```

**Key metrics:**
- **IC (Information Coefficient)**: Correlation between signal score and forward return. Good values: > 0.15.
- **ICIR**: IC / std(IC). Good values: > 2.0 (robust predictive consistency).
- **hit_rate**: Fraction of signals where the directional prediction was correct.

---

### Config

```
GET  /api/config                → current trading.yaml as JSON (watchlist, risk limits, etc.)
POST /api/config                → update config (deep merge, workers pick it up without restart)
```

---

## Common Task Recipes

### "Come stanno andando le news su NVDA?"

1. `GET /api/signals/NVDA` — see the current sentiment score and reasoning.
2. `GET /api/news/recent?ticker=NVDA&limit=20` — see the raw articles feeding that signal.
3. `GET /api/llm/feedback?ticker=NVDA&limit=10` — see per-model breakdowns.

### "Ci sono posizioni aperte?"

`GET /api/positions` — lists all live positions with market value and unrealized P&L.

### "Quali ordini sono stati eseguiti oggi?"

`GET /api/orders?limit=50` — filter `filled_at` for today's date client-side.

### "Come sta performando il sistema?"

`GET /api/performance/latest` — returns IC, ICIR, hit rate, per-model breakdown, and post-mortems on losing trades.

### "Qual è il modello LLM che performa meglio?"

`GET /api/backtest/gkg-jan26-v1/model_ic` — shows per-model IC and hit rate on the most recent backtest.

### "Voglio fermare tutto"

`POST /api/admin/killswitch` (with API key) — engages emergency stop, switches mode to `halted`.

---

## Score Reference Card

| Score range | Interpretation |
|---|---|
| +0.6 → +1.0 | Strongly bullish — high conviction long signal |
| +0.3 → +0.6 | Moderately bullish |
| -0.3 → +0.3 | Neutral / noisy — system typically ignores |
| -0.6 → -0.3 | Moderately bearish |
| -1.0 → -0.6 | Strongly bearish — high conviction short signal |

The system uses `score × confidence` as the effective signal strength. A score of 0.9 with confidence 0.4 yields an effective strength of 0.36 — treated as moderate, not strong.

---

## Notes for Agents

- Always check `GET /api/admin/status` first to confirm the system mode before interpreting positions or signals.
- If `killswitch: true` in status, no signals are being acted on regardless of score values.
- Signals have a freshness window of **30 minutes** — if `generated_at` is older than that, the signal may be stale.
- `BRK.B` is known to fail yfinance downloads (timezone issue) — expect missing forward return data for this ticker in backtests.
- `finbert: n=0` in model IC reports is normal — FinBERT only activates as a fallback when the primary ensemble diverges.
