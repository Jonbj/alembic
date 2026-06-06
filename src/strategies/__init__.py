"""Strategy registry and individual strategy implementations.

Each strategy lives in its own sub-package and must expose a class that
implements the StrategyBase interface (signal generation, backtesting,
validation gates).

Active strategies:
  s1  Time-Series Momentum Multi-Asset — 50% allocation, all gates passed
  s2  Volatility Risk Premium (short put SPY/QQQ) — 20% allocation, R&D
  s3  Cross-Sectional Momentum — demoted to R&D sleeve (Gate 3 & 5 failed)
  s4  News-Driven Tactical (LLM sentiment ranking) — 30% allocation

See config/strategies.yaml for allocation weights and gate status.
"""
