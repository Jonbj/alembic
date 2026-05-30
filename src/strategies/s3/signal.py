"""Cross-sectional residual momentum signal for S3 strategy."""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_beta(
    prices: pd.DataFrame,
    market_col: str = "SPY",
    window: int = 252,
) -> pd.DataFrame:
    """Rolling OLS beta of each stock against the market.

    beta = Cov(stock_ret, market_ret) / Var(market_ret) over trailing `window` days.

    Args:
        prices: Wide DataFrame, index=DatetimeIndex, columns include market_col and tickers.
        market_col: Column name for the market index (excluded from output columns).
        window: Rolling window in trading days.

    Returns:
        Wide DataFrame of beta values, same index as prices, columns=non-market tickers.
        NaN for dates with insufficient history (< window observations).
    """
    daily_rets = prices.pct_change()
    market_ret = daily_rets[market_col]
    market_var = market_ret.rolling(window).var()

    stock_cols = [c for c in prices.columns if c != market_col]
    betas: dict[str, pd.Series] = {}
    for col in stock_cols:
        cov = daily_rets[col].rolling(window).cov(market_ret)
        betas[col] = cov / market_var

    return pd.DataFrame(betas, index=prices.index)


def compute_residual_momentum(
    prices: pd.DataFrame,
    market_col: str = "SPY",
    lookback: int = 252,
    beta_window: int = 252,
) -> pd.DataFrame:
    """Residual momentum: raw momentum minus beta-adjusted market momentum.

    residual = (P_t / P_{t-lookback} - 1) - beta * (SPY_t / SPY_{t-lookback} - 1)

    Args:
        prices: Wide DataFrame, index=DatetimeIndex, columns include market_col.
        market_col: Column name for the market index.
        lookback: Momentum lookback in trading days (default 252 ≈ 12 months).
        beta_window: Rolling window for beta estimation.

    Returns:
        Wide DataFrame of residual momentum, same index as prices, columns=non-market tickers.
    """
    stock_cols = [c for c in prices.columns if c != market_col]

    momentum = prices / prices.shift(lookback) - 1
    market_momentum = momentum[market_col]
    stock_momentum = momentum[stock_cols]

    beta_df = compute_beta(prices, market_col=market_col, window=beta_window)

    # residual = stock_mom - beta * market_mom (broadcast market_mom along columns)
    residual = stock_momentum.sub(beta_df.mul(market_momentum, axis=0))
    return residual


def compute_cross_sectional_ranks(
    residual_momentum: pd.DataFrame,
    n_deciles: int = 10,
) -> pd.DataFrame:
    """Cross-sectional rank and decile assignment for residual momentum.

    At each date, tickers are ranked ascending (1 = lowest, N = highest).
    decile = ceil(rank * n_deciles / N).

    Args:
        residual_momentum: Wide DataFrame of residual momentum values.
        n_deciles: Number of decile bins (default 10).

    Returns:
        Long-format DataFrame with columns: as_of, ticker, residual_momentum, rank, decile.
    """
    valid_rows = residual_momentum.notna().any(axis=1)
    rm = residual_momentum[valid_rows]

    if rm.empty:
        return pd.DataFrame(columns=["as_of", "ticker", "residual_momentum", "rank", "decile"])

    ranks = rm.rank(axis=1, method="average", ascending=True, na_option="keep")
    n_valid = rm.notna().sum(axis=1)

    # decile = ceil(rank * n_deciles / n_valid); divide by n_valid broadcast along rows
    deciles = np.ceil(ranks.div(n_valid, axis="index") * n_deciles)

    rm_long = rm.stack().rename("residual_momentum")
    rank_long = ranks.stack().rename("rank")
    decile_long = deciles.stack().rename("decile")

    result = pd.concat([rm_long, rank_long, decile_long], axis=1).reset_index()
    result.columns = ["as_of", "ticker", "residual_momentum", "rank", "decile"]
    result = result.dropna(subset=["residual_momentum"])
    result["decile"] = result["decile"].astype(int)

    return result[["as_of", "ticker", "residual_momentum", "rank", "decile"]].reset_index(drop=True)


def generate_s3_signals(
    prices: pd.DataFrame,
    market_col: str = "SPY",
    lookback: int = 252,
    beta_window: int = 252,
    n_deciles: int = 10,
) -> pd.DataFrame:
    """Generate S3 cross-sectional residual momentum signals.

    Args:
        prices: Wide DataFrame, index=DatetimeIndex, columns include market_col and >=1 stock.
        market_col: Column name for the market index.
        lookback: Momentum lookback in trading days.
        beta_window: Rolling window for beta estimation.
        n_deciles: Number of decile bins.

    Returns:
        Long-format DataFrame with columns: as_of, ticker, residual_momentum, rank, decile.
        Only includes dates where all stocks have valid residual momentum (no NaN).
    """
    residual = compute_residual_momentum(
        prices, market_col=market_col, lookback=lookback, beta_window=beta_window
    )

    # Require all tickers to have valid residual momentum at each date
    valid_rows = residual.notna().all(axis=1)
    residual_clean = residual[valid_rows]

    return compute_cross_sectional_ranks(residual_clean, n_deciles=n_deciles)
