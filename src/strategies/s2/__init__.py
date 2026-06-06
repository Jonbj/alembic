"""S2 — Volatility Risk Premium strategy.

Sells cash-secured puts on SPY and QQQ during low implied-volatility regimes,
harvesting the historically persistent VIX risk premium. Uses LLM event
filtering to avoid selling into macro risk events. Allocation: 20%.
"""
