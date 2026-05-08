---
name: LLM Trading System - Project State
description: Current state and architecture of the LLM-based algorithmic trading system
type: project
originSessionId: d463b4ac-a870-4ca6-91e4-f2b227e2688e
---
As of 2026-05-08, the system is **feature-complete for the offline pipeline** (Fase 1 + extensions). All 433 tests pass.

**Goal**: Build an LLM-based ATS using the "Alpha Miner" paradigm — LLM generates signals offline, execution engine reads from Redis/DB.

**Target stack**: Freqtrade (crypto) or Backtrader (equities) + FastAPI/Celery/Redis async pipeline + FreqAI (RL with stable-baselines3/PyTorch) + FinGPT/FinBERT for sentiment.

**Why:** Spec mandates no synchronous LLM calls in trading loops; all inference is pre-computed and cached.

**Implemented modules:**
- Fase 1 foundation: config, models, sanitizer, LLM clients (Opus/Qwen3.5/Deepseek), ensemble, budget tracker, RedisStore, PostgreSQLStore
- Connectors: RSS, GDELT (with A/B test + historical backfill), SEC Edgar, macro (VIX/yield-curve/SPY)
- FinBERT fallback with entropic confidence mapping
- FastAPI: signals/admin/performance routes + X-API-Key auth
- SentimentWorker Celery + budget-gated FinBERT fallback
- Performance pipeline: Composite IC B4, LOO ICIR weights, PSI/CUSUM drift, post-mortem, threshold suggester
- QuantConnect PythonData feed + intraday strategy
- Weight Approval Loop (FastAPI GET/POST + audit trail)
- Auto-Apply Weights (guardrail VIX/IC/delta)
- Regime Detector (macro → sizing multiplier, 2 LLM parallel, Celery beat 07:00 UTC)
- Telegram Approval Flow: inline keyboard ✅/❌, Celery polling every 5s, anti-replay token

**How to apply:** All new features must respect async discipline (no LLM in execution loop), ALLOWED_MODEL_IDS validation, Redis OOM handling, parameterized SQL.
