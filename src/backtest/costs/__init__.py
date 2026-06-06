"""Transaction cost models for backtest simulation.

Provides spread, commission, and slippage estimates used to calculate
realistic net P&L. The default model uses half-spread + fixed commission
calibrated against Alpaca paper trading observations.
"""
