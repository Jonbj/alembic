"""Walk-forward out-of-sample validation.

Splits history into rolling in-sample (IS) and out-of-sample (OOS) windows,
fits strategy parameters on IS, and records OOS performance. IC and Sharpe
averaged across windows determine Gate 3 pass/fail.
"""
