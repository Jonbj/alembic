"""Core backtest event loop.

The engine replays historical bars in chronological order, calling
strategy logic at each bar without look-ahead. Slippage, position
tracking, and order matching are handled internally.
"""
