"""S4 — News-Driven Tactical strategy.

Cross-sectional ranking of watchlist tickers by LLM ensemble sentiment score
(polarity × confidence, averaged across Kimi/Qwen/DeepSeek/GLM). Buys the
top-ranked symbols that also pass the EMA20 trend filter. Allocation: 30%.
"""
