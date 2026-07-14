# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This project implements an **LLM-based Algorithmic Trading System (ATS)** following the **"Alpha Miner" paradigm**: the LLM operates as an offline research and strategy-generation engine, never in the hot execution path. The document `docs/LLM Trading System Integration.docx` contains the full Italian-language architectural specification.

Target execution: **Alpaca** (paper/live trading via SDK), **Backtrader** (backtesting).

## Architecture: Core Principle

LLMs are **never called synchronously inside trading loops**. All LLM inference happens offline or in background workers. The execution engine reads pre-computed signals from a local database or Redis.

```
[News/Data Sources] → [Background LLM Worker] → [Redis / PostgreSQL]
                                                         ↓
                             [Execution Engine (Freqtrade/Backtrader/QC)] reads signal at tick
```

## Tech Stack

- **Backend async stack**: FastAPI + Celery + Redis (background sentiment pipeline)
- **Backtesting**: Backtrader (`bt.feeds.PandasData` with custom `lines`)
- **LLM models**: FinBERT (local, int8 quantized) + an ensemble pair via Ollama Cloud (hosted at `ollama.com`, **not** local inference — `OLLAMA_BASE_URL` in `src/config.py`). The pair is not fixed: it's selected via the Redis key `config:sentiment_llm_models` (UI toggle / operator; fallback `SENTIMENT_LLM_MODELS` env, then "all") against the registry in `src/llm/model_registry.py` — 2026-07-11: `glm52,gptoss`. Swap candidates carry `in_all=False` so "all" never silently grows the live ensemble. LOO ICIR rebalancing adjusts the per-model *weights* (`ensemble:weights:current`), not the pair membership — expect the pair to change over time via explicit swaps.
- **Broker integration**: Alpaca SDK (paper/live); Backtrader for backtesting
- **Workers**: `worker` (concurrency=4, queue `celery`) + `worker-inference` (concurrency=1, queue `inference` — FinBERT/Ollama isolation)

## Engineering Constraints (Non-Negotiable)

### Latency / Async Discipline
- **Backtrader**: Never place LLM API calls in `next()`. Inject sentiment as a custom data feed by extending `bt.feeds.PandasData`, adding a `lines` tuple (e.g., `('llm_sentiment',)`) populated from a pre-computed CSV/DB.
- **Freqtrade**: LLM sentiment injected as a FreqAI feature column or via `confirm_trade_entry()` / `confirm_trade_exit()` callbacks that query a local Redis cache (never a remote API synchronously).
- **Live trading**: FastAPI/Celery workers asynchronously populate Redis; the execution engine reads from Redis at every tick.

### Input Sanitization
All text fed to LLMs **must be sanitized** before prompt construction:
- Strip/normalize Unicode homoglyphs (visually identical characters that corrupt NER)
- Remove hidden text insertions that invert sentiment
- Use normalized ASCII-safe representations for ticker symbols

### Ticker Resolution (separate from sentiment)
A wrong ticker is the worst-case error (an order on an unrelated stock), so ticker
resolution is a **separate, deterministic** task — never decided by the LLM alone. The
bare-text path only matches ambiguous tickers (short, or common words) via an explicit
`$cashtag`. A deterministic resolver (`src/connectors/ticker_resolver*.py`) confirms the
canonical, tradable symbol against internal aliases, SEC `company_tickers` and OpenFIGI,
emitting `NO_TRADE_*` when evidence is weak or ambiguous. Goal: `false_positive_ticker_rate → 0`.
Design: `docs/Alembic_ticker_sentiment_design.docx` (full) · `docs/S4_NEWS_PIPELINE_RND_BACKLOG_2026-06-29.md` (status).

**Measurement before enforcement (QX-01):** resolver enforcement, confidence calibration,
and `risk_flags` gating are **gated on a golden label set** — don't enable scoring changes
un-measured. The rails are live: `news_labels` table, blind Labeling UI (`/labeling`),
`scripts/{sample_news_labels,compute_label_forward_returns,validate_ticker_sentiment}.py`
(forward returns from **Alpaca historical**, not yfinance), and the Quality dashboard
(`/quality`). `news_log.extraction_method` records the extraction path (QT-03). See
ARCHITECTURE §3.2.

### Sentiment Scoring Formula
Convert LLM output to a numeric signal:

```
score = polarity × confidence
```

Where `polarity` ∈ [-1, +1] is the directional sentiment and `confidence` ∈ [0, 1] is the model's certainty. The product correctly scales the directional signal by how certain the model is (high polarity + low confidence → small score). This is the formula implemented in `src/workers/sentiment.py`.

### Prompt Engineering (DK-CoT)
All sentiment prompts must use **Domain Knowledge Chain-of-Thought**:
1. Assign role: "Act as a buy-side equity analyst…"
2. Require step-by-step reasoning over cash flows, competition, profitability
3. Provide few-shot analogical examples
4. Force structured JSON output (Function Calling) for deterministic parsing
5. Demand explicit bull/bear case analysis before final verdict

### Guardrails / Fallbacks
When LLM ensemble variance is high or timeout occurs, fall back to deterministic indicators (moving averages, RSI). Never block order execution waiting for an LLM response.

## Framework-Specific Notes

### Backtrader
- `self.data.close[0]` = current bar; `self.data.close[-1]` = previous bar (look-ahead prevention is built-in)
- Order lifecycle: `notify_order()` handles async fill/partial-fill events
- Live broker: `backtrader_ib_insync` for Interactive Brokers

### Alpaca (live/paper execution)
- Order placement uses `alpaca-py` directly (`TradingClient` / `MarketOrderRequest`) in `src/workers/portfolio_scheduler.py` and `src/workers/execution.py` — there is no `AlpacaBroker` class (`src/brokers/ibkr_adapter.py` holds only the unused `IBKRAdapter`)
- Paper and live trading share the same code path — switch via `config/trading.yaml` → `execution.engine`
- `execution.engine=portfolio` (default): only `portfolio-cycle` submits orders
- `execution.engine=legacy_sentiment`: only `run-execution` submits orders

## Hallucination Mitigation (Required in Production)

1. **RAG**: Ground LLM responses in retrieved source documents; verify quantitative claims against source
2. **Ensemble variance**: Query multiple models/seeds; flag high-variance outputs for human review or discard
3. **Supervisor agent**: A secondary LLM or rule-based checker cross-examines primary LLM output before it enters the signal store

## Key References

- Design specification: `docs/LLM Trading System Integration.docx`
- Architecture: `docs/ARCHITECTURE.md`
- Strategy reference: `docs/strategies.md`
- Operations guide: `docs/operations.md`
- Roadmap: `docs/superpowers/plans/2026-06-16-master-roadmap.md`
- LLM config: `docs/llm-config.md`
- FinGPT (open-source): github.com/AI4Finance-Foundation/FinGPT

## Agent skills

### Issue tracker

Issues for this repo are tracked as GitHub issues (via the `gh` CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical triage roles, label strings equal to their names. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
