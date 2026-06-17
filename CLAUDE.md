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
- **LLM models**: FinBERT (local, int8 quantized), Kimi K2.6 + Qwen3.5 via Ollama (ensemble)
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
- Use `AlpacaBroker` in `src/brokers/ibkr_adapter.py` for order placement
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
