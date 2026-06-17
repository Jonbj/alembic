# Architectural & Functional Analysis Report

**Date:** 2026-06-11  
**Scope:** Full codebase review against project specifications (`CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/strategies.md`)

---

## 1. Compliance with Core Specifications (Alpha Miner Paradigm)

- **Asynchronous Execution**: LLM inference is strictly isolated in `SentimentWorker`. Execution engines (`ExecutionWorker`, `PortfolioOrchestrator`) read pre-computed signals from Redis/PostgreSQL. No synchronous LLM calls exist in trading loops. ✅
- **Sentiment Formula**: `score = polarity × confidence` is correctly implemented in both the ensemble aggregation (`src/llm/ensemble.py`) and the FinBERT fallback (`src/llm/finbert.py`). ✅
- **DK-CoT Prompting**: `_DK_COT_PROMPT` in `src/workers/sentiment.py` correctly enforces role assignment, step-by-step reasoning, bull/bear cases, and strict JSON schema output. ✅
- **Guardrails & Fallbacks**: Ensemble divergence (`std > 0.30`) and budget exhaustion (`LLMBudgetExhaustedError`) correctly trigger the local `FinBERT` fallback via `run_in_executor`, ensuring no blocking of the execution path. ✅
- **Input Sanitization**: Text is now sanitized using NFKC normalization and BiDi/homoglyph stripping *before* any truncation or prompt formatting. ✅

---

## 2. Recent Code Corrections

- **Input Sanitization Fix**: Previously, text was truncated before sanitization, risking split Unicode homoglyphs or hidden control characters. Patched `src/llm/finbert.py` and `src/workers/sentiment.py` to apply `sanitize_text()` and `sanitize_ticker()` **before** truncation (`[:_body_limit]`) and prompt construction.
- **Symbol Handling**: Replaced hardcoded `"UNKNOWN"` fallback for missing ticker symbols with `sanitize_ticker()` applied to `item.asset_tags[0]`, defaulting to a safely sanitized empty or valid ASCII string to prevent LLM hallucination.

---

## 3. Strategy & Portfolio Orchestration

- **Sleeve-Local Allocation**: `PortfolioOrchestrator` correctly implements the weighted sum logic (`sleeve_weight × allocation_pct`). The `allocation_pct` in `config/strategies.yaml` acts as the absolute source of truth for capital governance. ✅
- **Execution Engine Routing**: The `execution.engine` flag in `config/trading.yaml` correctly gates whether `portfolio-cycle` or `legacy_sentiment` submits orders, preventing duplicate executions. ✅
- **Kill-Switch & Drawdown Cap**: The portfolio cycle correctly checks the Redis `killswitch_active` flag and enforces the 10% portfolio drawdown cap (updating peak equity in Redis) before proceeding. ✅
- **Trade Persistence**: `portfolio_scheduler.py` successfully writes `open_trade`, `record_trade_exit`, and back-fills `decision_id` into the `execution_decisions` table, ensuring full auditability. ✅

---

## 4. Identified Gaps vs. Documentation

The following gaps are explicitly noted in `docs/ARCHITECTURE.md`. Their current implementation status is validated below:

| Gap | Current Status | Assessment |
|-----|----------------|------------|
| **Vol Targeting Inactive** | `PortfolioVolTargeter` is instantiated, but `strategy_returns` is not passed to `orchestrator.run_cycle()`. | **Confirmed**. Matches docs. Requires wiring historical returns to activate vol scaling. |
| **Feedback Loop Blind to S1** | Docs state `trades` table is only populated by `run-execution` (S4 flow). | **RESOLVED**. `portfolio_scheduler.py` now correctly populates the `trades` table for portfolio executions, enabling Phase B loss feedback for S1/S2/S4 merged trades. |
| **NULL P&L on Notional Orders** | `qty` can be NULL at stop-loss close if fill reconciliation hasn't occurred (24h window). | **Confirmed**. Matches docs. Requires wiring Alpaca position qty at close. |
| **Strategies API Placeholder** | Equity curves use `random.gauss()`; gate `passed` values are not from actual metrics. | **Confirmed**. Intentional Phase D placeholder. |
| **S2 Options Infrastructure** | Current implementation is an equity proxy (overnight gap), not cash-secured puts. | **Confirmed**. Intentional. S2 is correctly disabled (`allocation_pct=0.00`) in `config/strategies.yaml`. |

---

## 5. Actionable Recommendations

1. **Wire Volatility Targeting**: Fetch `strategy_returns` from PostgreSQL and pass it into `orchestrator.run_cycle()` to activate the `PortfolioVolTargeter` scaling logic (targeting 10% annualized volatility via EWMA).
2. **Update Documentation**: Remove "Feedback loop blind to S1" from the *Known Gaps* table in `docs/ARCHITECTURE.md`, as the portfolio scheduler now correctly writes to the `trades` table.
3. **Enforce S4 Allocation Cap**: Verify that S4 remains capped at 10% (`allocation_pct: 0.10`) in `config/strategies.yaml` until the dedicated backtest gate report is produced, as mandated by the spec.
4. **Add Postmortem Triggers to Portfolio Flow**: Ensure `_maybe_postmortem()` is invoked when `portfolio_scheduler.py` records a stop-loss exit, linking the diagnosis to the newly created trade row.
