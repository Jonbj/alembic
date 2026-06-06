"""Alembic — LLM-based algorithmic trading system (Alpha Miner paradigm).

All LLM inference happens offline in background Celery workers. The execution
engine reads pre-computed signals from Redis, so latency and LLM API outages
never block order placement.

Package layout:
  src.workers       Celery tasks: ingestion, sentiment, execution, performance, regime
  src.store         Redis and PostgreSQL data access layers
  src.api           FastAPI REST endpoints (served on port 8001)
  src.strategies    S1/S2/S3/S4 strategy implementations and backtests
  src.portfolio     Multi-strategy orchestration, risk parity, vol targeting
  src.llm           LLM ensemble client, budget tracking, FinBERT fallback
  src.connectors    News source connectors (GDELT, MarketAux, Alpaca, RSS)
  src.models        Pydantic data models (news, signals, regime, performance)
  src.performance   IC/ICIR metrics, drift detection, LOO weight optimisation
  src.backtest      Event-loop backtest engine, walk-forward, validation gates
  src.notifications Alert channels (Telegram) — Notifier protocol
  src.text          Input sanitisation for LLM prompts
  src.analysis      Post-trade analysis helpers
  src.data          Market data utilities and options data
  src.config        Runtime configuration loader (config/trading.yaml)
"""

__version__ = "0.1.0"
