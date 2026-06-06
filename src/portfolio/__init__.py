"""Multi-strategy portfolio orchestration.

Combines signals from all active sleeves (S1/S2/S4), applies allocation
weights from config/strategies.yaml, enforces risk constraints (HHI cap,
max weight per asset, total exposure limit), and produces the final order list.

Key modules:
  orchestrator    Entry point called by the portfolio-cycle Celery task
  combiner        Aggregates per-sleeve signals into a unified weight vector
  risk_parity     Inverse-volatility weight normalisation with water-filling
  vol_targeting   Scales overall position to a target annualised volatility
  constraints     Hard limits: max weight, max exposure, HHI threshold
  types           Shared dataclasses (PortfolioSignal, RiskReport)
"""
