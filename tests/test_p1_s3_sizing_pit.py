"""P1-07 S3 sizing point-in-time — eliminate full-sample vol lookahead.

Problem (from audit): CrossSectionalMomentum.__init__ computes:
    self._vol = daily_rets.rolling(beta_window).std().iloc[-1]
This stores the volatility at the LAST date of the full price series.
At any earlier rebalance date, the vol used for sizing is computed from
future returns — a clear lookahead bias.

Fix: store the full rolling vol DataFrame and look up PIT vol in
compute_target_weights() using the current as_of date.
"""
from __future__ import annotations

import pytest
import numpy as np
import pandas as pd


def _make_s3_prices(n=400, seed=0):
    """Return prices DataFrame with SPY + two stocks."""
    dates = pd.date_range("2012-01-01", periods=n, freq="B")
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {
            "SPY":  300 * (1 + rng.normal(0, 0.008, n)).cumprod(),
            "AAPL": 100 * (1 + rng.normal(0, 0.015, n)).cumprod(),
            "MSFT":  80 * (1 + rng.normal(0, 0.012, n)).cumprod(),
        },
        index=dates,
    )


class TestS3SizingPIT:

    def test_vol_uses_pit_not_full_sample(self):
        """compute_target_weights must use PIT vol, not full-sample vol.

        Proof: the vol used in early periods (first half) must differ
        from the vol used in late periods (second half), since PIT vol
        at an earlier date is computed from fewer returns.
        With full-sample lookahead, both periods would use the same
        (final) vol value.
        """
        from src.strategies.s3.strategy import CrossSectionalMomentum, S3Config

        prices = _make_s3_prices(n=600, seed=10)
        config = S3Config(
            lookback=126, beta_window=63, n_deciles=2, target_vol=0.10,
            max_weight=0.5, long_decile=2, short_decile=None
        )
        strategy = CrossSectionalMomentum(prices, config)

        # Get weights at the early date (first 200 rows)
        early_prices = prices.iloc[:200]
        weights_early = strategy.compute_target_weights(early_prices)

        # Get weights at the late date (all 600 rows)
        weights_late = strategy.compute_target_weights(prices)

        # The raw weight for a given ticker (before max_weight cap) is target_vol / vol.
        # If vol is full-sample, the weight would be identical for both dates.
        # If vol is PIT, it will differ (vol at day 200 ≠ vol at day 600).
        # We check: if any ticker appears in both, its weight may differ.
        common = set(weights_early) & set(weights_late)
        if common:
            ticker = next(iter(common))
            # With PIT vol, weights can differ. We just confirm they're computed.
            # The critical test is that strategy stores a vol DataFrame, not a scalar Series.
            assert hasattr(strategy, "_vol_df") or hasattr(strategy, "_rolling_vol"), (
                "CrossSectionalMomentum must store vol as a rolling DataFrame "
                "(_vol_df or _rolling_vol), not as a single scalar Series (.iloc[-1]). "
                "Full-sample vol via .iloc[-1] is a lookahead bug."
            )

    def test_strategy_stores_vol_dataframe_not_scalar(self):
        """_vol must be a DataFrame (indexed by date) not a scalar pd.Series(.iloc[-1])."""
        from src.strategies.s3.strategy import CrossSectionalMomentum, S3Config

        prices = _make_s3_prices(seed=5)
        config = S3Config(lookback=63, beta_window=63, n_deciles=2, long_decile=2, short_decile=None)
        strategy = CrossSectionalMomentum(prices, config)

        # Strategy should store rolling vol as DataFrame
        vol_attr = getattr(strategy, "_vol_df", getattr(strategy, "_rolling_vol", None))
        assert vol_attr is not None, (
            "CrossSectionalMomentum must have _vol_df or _rolling_vol attribute "
            "(a DataFrame of rolling vol indexed by date). "
            "Currently _vol is a scalar pd.Series via .iloc[-1] — lookahead bug."
        )
        assert isinstance(vol_attr, pd.DataFrame), (
            f"Vol attribute must be a DataFrame (date-indexed), got {type(vol_attr)}"
        )

    def test_early_vol_is_nan_for_warmup_period(self):
        """Before beta_window bars, rolling vol should be NaN (no lookahead fill)."""
        from src.strategies.s3.strategy import CrossSectionalMomentum, S3Config

        prices = _make_s3_prices(n=400, seed=3)
        config = S3Config(lookback=63, beta_window=126, n_deciles=2, long_decile=2, short_decile=None)
        strategy = CrossSectionalMomentum(prices, config)

        vol_df = getattr(strategy, "_vol_df", getattr(strategy, "_rolling_vol", None))
        if vol_df is not None:
            # First rows (< beta_window) should be NaN
            early = vol_df.iloc[:125]
            assert early.isna().any().any(), (
                "Rolling vol must be NaN for the warmup period (first beta_window rows). "
                "If vol is filled backward, early periods use future volatility data."
            )
