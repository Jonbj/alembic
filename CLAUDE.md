# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This project implements an **LLM-based Algorithmic Trading System (ATS)** following the **"Alpha Miner" paradigm**: the LLM operates as an offline research and strategy-generation engine, never in the hot execution path. The document `docs/LLM Trading System Integration.docx` contains the full Italian-language architectural specification.

Target frameworks (choose one or combine): **Freqtrade** (crypto), **Backtrader** (equities/general), **QuantConnect Lean** (multi-asset, institutional grade).

## Architecture: Core Principle

LLMs are **never called synchronously inside trading loops**. All LLM inference happens offline or in background workers. The execution engine reads pre-computed signals from a local database or Redis.

```
[News/Data Sources] → [Background LLM Worker] → [Redis / PostgreSQL]
                                                         ↓
                             [Execution Engine (Freqtrade/Backtrader/QC)] reads signal at tick
```

## Tech Stack

- **Backend async stack**: FastAPI + Celery + Redis (background sentiment pipeline)
- **Backtesting**: Backtrader (`bt.feeds.PandasData` with custom `lines`) or Freqtrade (vectorized Pandas)
- **ML/RL**: FreqAI (stable-baselines3 + PyTorch) for Reinforcement Learning integration
- **LLM models**: FinGPT (LoRA fine-tuned LLaMA/Falcon, open-source), FinBERT (sentiment), GPT-4o/Claude (via API)
- **Broker integration**: Interactive Brokers via `backtrader_ib_insync`; crypto via Binance/Freqtrade
- **QuantConnect**: MCP server on port 3001 (Dockerized), interfaced via `mcp.json`

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

### Freqtrade / FreqAI
- Strategies use vectorized Pandas over the full OHLCV DataFrame; avoid per-row Python loops
- `startup_candle_count` must be set to stabilize indicators at strategy start
- RL reward function lives in `calculate_reward()`; incorporate trade duration and floating P&L to prevent myopic convergence
- Minimum ROI and dynamic stoploss configured in strategy JSON config, not hardcoded

### QuantConnect Lean
- Use MCP server (`project-create`, cloud backtest endpoints) for agent-driven development
- Known issue: Pydantic `$ref` resolution in MCP JSON schema may show parameters as plain `string` — mitigate by explicitly structuring inputs rather than relying on schema inference
- ML model artifacts saved to Object Store for fast retrieval in live runs

## Hallucination Mitigation (Required in Production)

1. **RAG**: Ground LLM responses in retrieved source documents; verify quantitative claims against source
2. **Ensemble variance**: Query multiple models/seeds; flag high-variance outputs for human review or discard
3. **Supervisor agent**: A secondary LLM or rule-based checker cross-examines primary LLM output before it enters the signal store

## Key References

- Design specification: `docs/LLM Trading System Integration.docx`
- FinGPT (open-source): github.com/AI4Finance-Foundation/FinGPT
- FinRL (RL for finance): github.com/AI4Finance-Foundation/FinRL
- QuantConnect MCP: github.com/QuantConnect/mcp-server
