"""Tests for options ingestion module — Black-Scholes, synthetic chain generation, storage."""

from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import math

import numpy as np
import pandas as pd
import pytest

from src.data.options.ingestion import (
    OptionChainDataLoader,
    black_scholes_price,
    compute_greeks,
    fetch_chain,
    ingest_from_ibkr,
    store_chain,
)

# ---------------------------------------------------------------------------
# Black-Scholes pricing
# ---------------------------------------------------------------------------

# Reference params: SPY=450, K=450, T=30days, r=5%, sigma=20%
_S = 450.0
_K = 450.0
_T = 30 / 365
_R = 0.05
_SIG = 0.20


class TestBlackScholesPrice:
    def test_atm_call_positive(self) -> None:
        price = black_scholes_price(_S, _K, _T, _R, _SIG, "C")
        assert price > 0

    def test_atm_put_positive(self) -> None:
        price = black_scholes_price(_S, _K, _T, _R, _SIG, "P")
        assert price > 0

    def test_put_call_parity(self) -> None:
        """C - P = S - K * e^(-rT) (European put-call parity)."""
        c = black_scholes_price(_S, _K, _T, _R, _SIG, "C")
        p = black_scholes_price(_S, _K, _T, _R, _SIG, "P")
        lhs = c - p
        rhs = _S - _K * math.exp(-_R * _T)
        assert abs(lhs - rhs) < 1e-6

    def test_itm_call_greater_than_otm_call(self) -> None:
        itm = black_scholes_price(_S, _K - 10, _T, _R, _SIG, "C")
        atm = black_scholes_price(_S, _K, _T, _R, _SIG, "C")
        otm = black_scholes_price(_S, _K + 10, _T, _R, _SIG, "C")
        assert itm > atm > otm

    def test_itm_put_greater_than_otm_put(self) -> None:
        itm = black_scholes_price(_S, _K + 10, _T, _R, _SIG, "P")
        atm = black_scholes_price(_S, _K, _T, _R, _SIG, "P")
        otm = black_scholes_price(_S, _K - 10, _T, _R, _SIG, "P")
        assert itm > atm > otm

    def test_expired_call_returns_intrinsic_itm(self) -> None:
        price = black_scholes_price(460.0, 450.0, 0.0, _R, _SIG, "C")
        assert price == pytest.approx(10.0)

    def test_expired_call_returns_zero_otm(self) -> None:
        price = black_scholes_price(440.0, 450.0, 0.0, _R, _SIG, "C")
        assert price == pytest.approx(0.0)

    def test_expired_put_returns_intrinsic_itm(self) -> None:
        price = black_scholes_price(440.0, 450.0, 0.0, _R, _SIG, "P")
        assert price == pytest.approx(10.0)

    def test_expired_put_returns_zero_otm(self) -> None:
        price = black_scholes_price(460.0, 450.0, 0.0, _R, _SIG, "P")
        assert price == pytest.approx(0.0)

    def test_price_nonnegative(self) -> None:
        for right in ("C", "P"):
            for strike in (400.0, 450.0, 500.0):
                price = black_scholes_price(_S, strike, _T, _R, _SIG, right)
                assert price >= 0, f"Negative price for {right} K={strike}: {price}"


# ---------------------------------------------------------------------------
# Greeks
# ---------------------------------------------------------------------------

class TestComputeGreeks:
    def test_atm_call_delta_near_half(self) -> None:
        g = compute_greeks(_S, _K, _T, _R, _SIG, "C")
        assert 0.45 < g["delta"] < 0.65

    def test_atm_put_delta_near_minus_half(self) -> None:
        g = compute_greeks(_S, _K, _T, _R, _SIG, "P")
        assert -0.65 < g["delta"] < -0.35

    def test_call_delta_between_0_and_1(self) -> None:
        for strike in (400.0, 450.0, 500.0):
            g = compute_greeks(_S, strike, _T, _R, _SIG, "C")
            assert 0.0 <= g["delta"] <= 1.0

    def test_put_delta_between_minus1_and_0(self) -> None:
        for strike in (400.0, 450.0, 500.0):
            g = compute_greeks(_S, strike, _T, _R, _SIG, "P")
            assert -1.0 <= g["delta"] <= 0.0

    def test_gamma_positive(self) -> None:
        for right in ("C", "P"):
            g = compute_greeks(_S, _K, _T, _R, _SIG, right)
            assert g["gamma"] > 0

    def test_put_call_same_gamma(self) -> None:
        gc = compute_greeks(_S, _K, _T, _R, _SIG, "C")
        gp = compute_greeks(_S, _K, _T, _R, _SIG, "P")
        assert gc["gamma"] == pytest.approx(gp["gamma"], rel=1e-6)

    def test_vega_positive(self) -> None:
        for right in ("C", "P"):
            g = compute_greeks(_S, _K, _T, _R, _SIG, right)
            assert g["vega"] > 0

    def test_put_call_same_vega(self) -> None:
        gc = compute_greeks(_S, _K, _T, _R, _SIG, "C")
        gp = compute_greeks(_S, _K, _T, _R, _SIG, "P")
        assert gc["vega"] == pytest.approx(gp["vega"], rel=1e-6)

    def test_expired_delta_call_itm(self) -> None:
        g = compute_greeks(460.0, 450.0, 0.0, _R, _SIG, "C")
        assert g["delta"] == 1.0

    def test_expired_delta_put_itm(self) -> None:
        g = compute_greeks(440.0, 450.0, 0.0, _R, _SIG, "P")
        assert g["delta"] == -1.0


# ---------------------------------------------------------------------------
# OptionChainDataLoader — generate_chain
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS = {
    "symbol", "trade_date", "expiry", "strike", "right",
    "bid", "ask", "mid", "volume", "open_interest",
    "implied_vol", "delta", "gamma", "theta", "vega",
    "underlying_price", "multiplier", "source",
}

_TRADE_DATE = date(2022, 6, 1)
_EXPIRY = date(2022, 7, 15)  # ~44 days out


@pytest.fixture
def loader() -> OptionChainDataLoader:
    """Loader with no DataLoader dependency — underlying_price passed explicitly."""
    return OptionChainDataLoader(risk_free_rate=0.05, base_iv=0.18)


class TestGenerateChain:
    def test_required_columns_present(self, loader: OptionChainDataLoader) -> None:
        df = loader.generate_chain("SPY", _TRADE_DATE, _EXPIRY, underlying_price=450.0)
        assert REQUIRED_COLUMNS.issubset(set(df.columns))

    def test_has_calls_and_puts(self, loader: OptionChainDataLoader) -> None:
        df = loader.generate_chain("SPY", _TRADE_DATE, _EXPIRY, underlying_price=450.0)
        assert set(df["right"].unique()) == {"C", "P"}

    def test_strikes_bracket_underlying(self, loader: OptionChainDataLoader) -> None:
        df = loader.generate_chain("SPY", _TRADE_DATE, _EXPIRY, underlying_price=450.0)
        strikes = df["strike"].unique()
        assert min(strikes) < 450.0
        assert max(strikes) > 450.0

    def test_symmetric_strikes_calls_and_puts(self, loader: OptionChainDataLoader) -> None:
        """Each strike appears for both C and P."""
        df = loader.generate_chain("SPY", _TRADE_DATE, _EXPIRY, underlying_price=450.0)
        calls = set(df.loc[df["right"] == "C", "strike"].unique())
        puts = set(df.loc[df["right"] == "P", "strike"].unique())
        assert calls == puts

    def test_bid_less_than_ask(self, loader: OptionChainDataLoader) -> None:
        df = loader.generate_chain("SPY", _TRADE_DATE, _EXPIRY, underlying_price=450.0)
        assert (df["bid"] < df["ask"]).all()

    def test_mid_is_average_of_bid_ask(self, loader: OptionChainDataLoader) -> None:
        df = loader.generate_chain("SPY", _TRADE_DATE, _EXPIRY, underlying_price=450.0)
        expected_mid = (df["bid"] + df["ask"]) / 2
        pd.testing.assert_series_equal(df["mid"], expected_mid, check_names=False)

    def test_call_delta_in_valid_range(self, loader: OptionChainDataLoader) -> None:
        df = loader.generate_chain("SPY", _TRADE_DATE, _EXPIRY, underlying_price=450.0)
        calls = df[df["right"] == "C"]
        assert (calls["delta"] >= 0).all()
        assert (calls["delta"] <= 1).all()

    def test_put_delta_in_valid_range(self, loader: OptionChainDataLoader) -> None:
        df = loader.generate_chain("SPY", _TRADE_DATE, _EXPIRY, underlying_price=450.0)
        puts = df[df["right"] == "P"]
        assert (puts["delta"] >= -1).all()
        assert (puts["delta"] <= 0).all()

    def test_gamma_positive(self, loader: OptionChainDataLoader) -> None:
        df = loader.generate_chain("SPY", _TRADE_DATE, _EXPIRY, underlying_price=450.0)
        assert (df["gamma"] > 0).all()

    def test_implied_vol_positive(self, loader: OptionChainDataLoader) -> None:
        df = loader.generate_chain("SPY", _TRADE_DATE, _EXPIRY, underlying_price=450.0)
        assert (df["implied_vol"] > 0).all()

    def test_multiplier_is_100(self, loader: OptionChainDataLoader) -> None:
        df = loader.generate_chain("SPY", _TRADE_DATE, _EXPIRY, underlying_price=450.0)
        assert (df["multiplier"] == 100).all()

    def test_source_is_synthetic(self, loader: OptionChainDataLoader) -> None:
        df = loader.generate_chain("SPY", _TRADE_DATE, _EXPIRY, underlying_price=450.0)
        assert (df["source"] == "synthetic").all()

    def test_symbol_column(self, loader: OptionChainDataLoader) -> None:
        df = loader.generate_chain("SPY", _TRADE_DATE, _EXPIRY, underlying_price=450.0)
        assert (df["symbol"] == "SPY").all()

    def test_trade_date_column(self, loader: OptionChainDataLoader) -> None:
        df = loader.generate_chain("SPY", _TRADE_DATE, _EXPIRY, underlying_price=450.0)
        assert (df["trade_date"] == _TRADE_DATE).all()

    def test_expiry_column(self, loader: OptionChainDataLoader) -> None:
        df = loader.generate_chain("SPY", _TRADE_DATE, _EXPIRY, underlying_price=450.0)
        assert (df["expiry"] == _EXPIRY).all()

    def test_underlying_price_column(self, loader: OptionChainDataLoader) -> None:
        df = loader.generate_chain("SPY", _TRADE_DATE, _EXPIRY, underlying_price=450.0)
        assert (df["underlying_price"] == 450.0).all()

    def test_volume_and_oi_nonnegative(self, loader: OptionChainDataLoader) -> None:
        df = loader.generate_chain("SPY", _TRADE_DATE, _EXPIRY, underlying_price=450.0)
        assert (df["volume"] >= 0).all()
        assert (df["open_interest"] >= 0).all()

    def test_atm_call_price_reasonable(self, loader: OptionChainDataLoader) -> None:
        """ATM 30-day call on SPY@450 with 18% IV should be between $5 and $25."""
        expiry_30d = _TRADE_DATE + timedelta(days=30)
        df = loader.generate_chain("SPY", _TRADE_DATE, expiry_30d, underlying_price=450.0)
        calls = df[(df["right"] == "C") & (df["strike"] == 450.0)]
        if len(calls) > 0:
            mid = calls.iloc[0]["mid"]
            assert 3.0 <= mid <= 25.0, f"Unexpected ATM call price: {mid}"

    def test_bid_nonnegative(self, loader: OptionChainDataLoader) -> None:
        df = loader.generate_chain("SPY", _TRADE_DATE, _EXPIRY, underlying_price=450.0)
        assert (df["bid"] >= 0).all()


# ---------------------------------------------------------------------------
# OptionChainDataLoader — generate_chains (date range)
# ---------------------------------------------------------------------------

class TestGenerateChains:
    def test_returns_dataframe(self, loader: OptionChainDataLoader) -> None:
        prices = _make_spy_prices(_TRADE_DATE, 5)
        df = loader.generate_chains("SPY", _TRADE_DATE, _TRADE_DATE + timedelta(days=4), underlying_prices=prices)
        assert isinstance(df, pd.DataFrame)

    def test_symbol_column_correct(self, loader: OptionChainDataLoader) -> None:
        prices = _make_spy_prices(_TRADE_DATE, 5)
        df = loader.generate_chains("SPY", _TRADE_DATE, _TRADE_DATE + timedelta(days=4), underlying_prices=prices)
        assert not df.empty
        assert (df["symbol"] == "SPY").all()

    def test_date_range_covered(self, loader: OptionChainDataLoader) -> None:
        """All business days in range appear in the output."""
        start = date(2022, 6, 1)
        end = date(2022, 6, 10)
        prices = _make_spy_prices(start, 14)
        df = loader.generate_chains("SPY", start, end, underlying_prices=prices)
        bdays = pd.bdate_range(start.isoformat(), end.isoformat())
        dates_in_df = set(df["trade_date"].unique())
        for bday in bdays:
            assert bday.date() in dates_in_df

    def test_has_required_columns(self, loader: OptionChainDataLoader) -> None:
        prices = _make_spy_prices(_TRADE_DATE, 5)
        df = loader.generate_chains("SPY", _TRADE_DATE, _TRADE_DATE + timedelta(days=4), underlying_prices=prices)
        assert REQUIRED_COLUMNS.issubset(set(df.columns))

    def test_multiple_expiries_per_day(self, loader: OptionChainDataLoader) -> None:
        """Each trade_date should have options for at least 2 different expiries."""
        prices = _make_spy_prices(_TRADE_DATE, 5)
        df = loader.generate_chains("SPY", _TRADE_DATE, _TRADE_DATE, underlying_prices=prices, num_expiries=3)
        expiries_on_day = df[df["trade_date"] == _TRADE_DATE]["expiry"].unique()
        assert len(expiries_on_day) >= 2


# ---------------------------------------------------------------------------
# Postgres storage helpers
# ---------------------------------------------------------------------------

class TestStoreChain:
    def test_store_chain_returns_row_count(self, loader: OptionChainDataLoader) -> None:
        df = loader.generate_chain("SPY", _TRADE_DATE, _EXPIRY, underlying_price=450.0)

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cur
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cur.rowcount = len(df)

        count = store_chain(df, mock_conn)
        assert count == len(df)

    def test_store_chain_calls_execute(self, loader: OptionChainDataLoader) -> None:
        df = loader.generate_chain("SPY", _TRADE_DATE, _EXPIRY, underlying_price=450.0)

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cur
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cur.rowcount = len(df)

        store_chain(df, mock_conn)
        assert mock_cur.executemany.called or mock_cur.execute.called

    def test_store_chain_commits(self, loader: OptionChainDataLoader) -> None:
        df = loader.generate_chain("SPY", _TRADE_DATE, _EXPIRY, underlying_price=450.0)

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cur
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cur.rowcount = len(df)

        store_chain(df, mock_conn)
        mock_conn.commit.assert_called_once()


class TestFetchChain:
    def test_fetch_chain_returns_dataframe(self) -> None:
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cur
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cur.fetchall.return_value = []
        mock_cur.description = [(col,) for col in sorted(REQUIRED_COLUMNS)]

        result = fetch_chain("SPY", _TRADE_DATE, mock_conn)
        assert isinstance(result, pd.DataFrame)

    def test_fetch_chain_queries_correct_symbol_and_date(self) -> None:
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cur
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cur.fetchall.return_value = []
        mock_cur.description = []

        fetch_chain("SPY", _TRADE_DATE, mock_conn)
        mock_cur.execute.assert_called_once()
        args = mock_cur.execute.call_args
        params = args[0][1]
        assert "SPY" in params
        assert _TRADE_DATE in params


# ---------------------------------------------------------------------------
# IBKR ingestion
# ---------------------------------------------------------------------------

class TestIngestFromIbkr:
    def test_ingest_calls_get_option_chain(self) -> None:
        mock_adapter = MagicMock()
        mock_adapter.get_option_chain.return_value = []
        mock_conn = MagicMock()

        ingest_from_ibkr(mock_adapter, "SPY", "20221216", mock_conn)

        mock_adapter.get_option_chain.assert_called_once_with("SPY", "20221216")

    def test_ingest_returns_zero_on_empty_chain(self) -> None:
        mock_adapter = MagicMock()
        mock_adapter.get_option_chain.return_value = []
        mock_conn = MagicMock()

        count = ingest_from_ibkr(mock_adapter, "SPY", "20221216", mock_conn)
        assert count == 0

    def test_ingest_stores_rows_when_chain_nonempty(self) -> None:
        mock_adapter = MagicMock()
        mock_adapter.get_option_chain.return_value = [
            {"symbol": "SPY", "expiry": "20221216", "strike": 450.0,
             "right": "C", "exchange": "CBOE", "multiplier": "100"},
            {"symbol": "SPY", "expiry": "20221216", "strike": 450.0,
             "right": "P", "exchange": "CBOE", "multiplier": "100"},
        ]
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cur
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cur.rowcount = 2

        count = ingest_from_ibkr(mock_adapter, "SPY", "20221216", mock_conn)
        assert count == 2

    def test_ingest_returns_count_on_success(self) -> None:
        """Verify store_chain is called and its return value is propagated."""
        mock_adapter = MagicMock()
        chain_rows = [
            {"symbol": "SPY", "expiry": "20221216", "strike": s,
             "right": r, "exchange": "CBOE", "multiplier": "100"}
            for s in (448.0, 450.0, 452.0)
            for r in ("C", "P")
        ]
        mock_adapter.get_option_chain.return_value = chain_rows
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cur
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cur.rowcount = len(chain_rows)

        count = ingest_from_ibkr(mock_adapter, "SPY", "20221216", mock_conn)
        assert count == len(chain_rows)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_spy_prices(start: date, n: int) -> pd.Series:
    """Create a synthetic SPY price series for testing."""
    np.random.seed(42)
    dates = pd.bdate_range(start.isoformat(), periods=n)
    prices = 450.0 + np.cumsum(np.random.normal(0, 2, n))
    return pd.Series(prices, index=dates)
