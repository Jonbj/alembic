"""T-101: S1 universe validation, data quality checks, and screening rules."""
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.backtest.data.universe import Universe, UniverseAsset, load_universe
from src.backtest.data.validator import (
    ValidationResult,
    validate_ohlcv,
    validate_universe_data,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

S1_EXPECTED_TICKERS = [
    "SPY", "QQQ", "IWM", "VEA", "VWO", "EWJ",
    "TLT", "IEF", "SHY", "LQD", "HYG", "TIP",
    "GLD", "DBC", "VNQ",
]

S1_ASSET_CLASSES = {
    "US_EQUITY_LARGE", "US_EQUITY_TECH", "US_EQUITY_SMALL",
    "INTL_DEV_EQUITY", "EM_EQUITY", "JAPAN_EQUITY",
    "UST_LONG", "UST_INTERMEDIATE", "UST_SHORT",
    "IG_CREDIT", "HY_CREDIT", "TIPS",
    "GOLD", "BROAD_COMMODITY", "US_REITS",
}

S1_BROAD_CATEGORIES = {
    "equity": {"US_EQUITY_LARGE", "US_EQUITY_TECH", "US_EQUITY_SMALL", "INTL_DEV_EQUITY", "EM_EQUITY", "JAPAN_EQUITY"},
    "bond": {"UST_LONG", "UST_INTERMEDIATE", "UST_SHORT", "IG_CREDIT", "HY_CREDIT", "TIPS"},
    "commodity": {"BROAD_COMMODITY"},
    "gold": {"GOLD"},
    "real_estate": {"US_REITS"},
}


@pytest.fixture
def clean_df() -> pd.DataFrame:
    """500 trading days of clean OHLCV data."""
    np.random.seed(0)
    dates = pd.date_range("2020-01-01", periods=500, freq="B")
    n = len(dates)
    prices = 100 * np.exp(np.cumsum(np.random.normal(0.0003, 0.008, n)))
    return pd.DataFrame(
        {
            "Open": prices * 0.999,
            "High": prices * 1.005,
            "Low": prices * 0.995,
            "Close": prices,
            "Volume": np.ones(n) * 5_000_000,
            "Adj Close": prices,
        },
        index=dates,
    )


@pytest.fixture
def short_df() -> pd.DataFrame:
    """Only 100 trading days — below min-history threshold."""
    np.random.seed(1)
    dates = pd.date_range("2023-01-01", periods=100, freq="B")
    n = len(dates)
    prices = 50 * np.exp(np.cumsum(np.random.normal(0, 0.01, n)))
    return pd.DataFrame(
        {
            "Open": prices,
            "High": prices * 1.01,
            "Low": prices * 0.99,
            "Close": prices,
            "Volume": np.ones(n) * 1_000_000,
            "Adj Close": prices,
        },
        index=dates,
    )


@pytest.fixture
def gapped_df(clean_df: pd.DataFrame) -> pd.DataFrame:
    """Data with a 10-calendar-day gap (> 5 business days) in the middle."""
    mid = len(clean_df) // 2
    return pd.concat([clean_df.iloc[:mid], clean_df.iloc[mid + 8:]])


@pytest.fixture
def spiked_df(clean_df: pd.DataFrame) -> pd.DataFrame:
    """Data with an anomalous 40% price spike."""
    df = clean_df.copy()
    idx = 50
    df.iloc[idx, df.columns.get_loc("Close")] *= 1.40
    df.iloc[idx, df.columns.get_loc("Adj Close")] *= 1.40
    return df


@pytest.fixture
def nan_heavy_df(clean_df: pd.DataFrame) -> pd.DataFrame:
    """Data with 10% NaN in Adj Close."""
    df = clean_df.copy()
    rng = np.random.default_rng(42)
    nan_idx = rng.choice(len(df), size=len(df) // 10, replace=False)
    df.iloc[nan_idx, df.columns.get_loc("Adj Close")] = np.nan
    return df


@pytest.fixture
def no_adj_close_df(clean_df: pd.DataFrame) -> pd.DataFrame:
    """Data missing the Adj Close column."""
    return clean_df.drop(columns=["Adj Close"])


# ---------------------------------------------------------------------------
# T-101.1 — S1 Universe YAML Validation
# ---------------------------------------------------------------------------

class TestS1UniverseDefinition:
    """The real config/universe.yaml defines the S1 universe correctly."""

    @pytest.fixture(autouse=True)
    def load_s1(self) -> None:
        self.universe = load_universe("s1", config_path=Path("config/universe.yaml"))

    def test_has_exactly_15_tickers(self) -> None:
        assert len(self.universe.assets) == 15

    def test_all_expected_tickers_present(self) -> None:
        symbols = set(self.universe.symbols())
        assert symbols == set(S1_EXPECTED_TICKERS)

    def test_all_asset_classes_present(self) -> None:
        classes = {a.asset_class for a in self.universe.assets}
        assert classes == S1_ASSET_CLASSES

    def test_cross_asset_coverage(self) -> None:
        classes = {a.asset_class for a in self.universe.assets}
        for category, members in S1_BROAD_CATEGORIES.items():
            assert classes & members, f"No asset in category '{category}'"

    def test_inception_dates_are_historical(self) -> None:
        today = date.today()
        for asset in self.universe.assets:
            assert asset.inception_date < today, f"{asset.symbol} inception in future"
            assert asset.inception_date >= date(1990, 1, 1), f"{asset.symbol} inception implausibly old"

    def test_point_in_time_pre_2000(self) -> None:
        active = self.universe.active_at(date(1999, 12, 31))
        symbols = {a.symbol for a in active}
        # SPY (1993), EWJ (1996), QQQ (1999-03-10) all incepted before 1999-12-31
        assert "SPY" in symbols
        assert "EWJ" in symbols
        assert "QQQ" in symbols
        # IWM incepted 2000-05-22 — not yet active
        assert "IWM" not in symbols
        # GLD incepted 2004-11-18 — not yet active
        assert "GLD" not in symbols

    def test_point_in_time_2005(self) -> None:
        active = self.universe.active_at(date(2005, 1, 1))
        symbols = {a.symbol for a in active}
        # QQQ (2000), TLT/IEF/SHY/LQD (2002), TIP (2003), GLD (2004) should all be active
        for sym in ("SPY", "QQQ", "TLT", "IEF", "SHY", "LQD", "TIP", "GLD"):
            assert sym in symbols, f"{sym} should be active by 2005"

    def test_all_have_unique_symbols(self) -> None:
        symbols = list(self.universe.symbols())
        assert len(symbols) == len(set(symbols))


# ---------------------------------------------------------------------------
# T-101.2 — Data Validation
# ---------------------------------------------------------------------------

class TestValidateOhlcv:
    """validate_ohlcv() correctly identifies data quality issues."""

    def test_clean_data_is_valid(self, clean_df: pd.DataFrame) -> None:
        result = validate_ohlcv("TEST", clean_df)
        assert result.is_valid
        assert result.symbol == "TEST"
        assert len(result.gaps) == 0
        assert len(result.spikes) == 0
        assert result.has_adj_close
        assert result.trading_days >= 252

    def test_detects_long_gap(self, gapped_df: pd.DataFrame) -> None:
        result = validate_ohlcv("GAP", gapped_df, max_gap_days=5)
        assert not result.is_valid
        assert len(result.gaps) >= 1

    def test_gap_shorter_than_threshold_is_ok(self, clean_df: pd.DataFrame) -> None:
        # Create a 2-business-day gap (weekend-sized), should be ignored
        df = pd.concat([clean_df.iloc[:100], clean_df.iloc[102:]])
        result = validate_ohlcv("OK", df, max_gap_days=5)
        assert len(result.gaps) == 0

    def test_detects_price_spike(self, spiked_df: pd.DataFrame) -> None:
        result = validate_ohlcv("SPIKE", spiked_df, spike_threshold=0.25)
        assert len(result.spikes) >= 1

    def test_spike_below_threshold_not_flagged(self, clean_df: pd.DataFrame) -> None:
        df = clean_df.copy()
        df.iloc[50, df.columns.get_loc("Close")] *= 1.10  # 10% move, below 25% threshold
        result = validate_ohlcv("OK", df, spike_threshold=0.25)
        assert len(result.spikes) == 0

    def test_missing_adj_close_is_invalid(self, no_adj_close_df: pd.DataFrame) -> None:
        result = validate_ohlcv("NOADJ", no_adj_close_df)
        assert not result.is_valid
        assert not result.has_adj_close

    def test_trading_days_count(self, clean_df: pd.DataFrame) -> None:
        result = validate_ohlcv("TEST", clean_df)
        assert result.trading_days == len(clean_df)

    def test_nan_fraction_reported(self, nan_heavy_df: pd.DataFrame) -> None:
        result = validate_ohlcv("NAN", nan_heavy_df)
        assert result.nan_fraction > 0.05
        assert not result.is_valid  # high NaN → invalid

    def test_clean_data_has_zero_nan_fraction(self, clean_df: pd.DataFrame) -> None:
        result = validate_ohlcv("CLEAN", clean_df)
        assert result.nan_fraction == 0.0

    def test_validation_result_is_dataclass(self, clean_df: pd.DataFrame) -> None:
        result = validate_ohlcv("TEST", clean_df)
        assert isinstance(result, ValidationResult)
        assert hasattr(result, "symbol")
        assert hasattr(result, "is_valid")
        assert hasattr(result, "gaps")
        assert hasattr(result, "spikes")
        assert hasattr(result, "has_adj_close")
        assert hasattr(result, "trading_days")
        assert hasattr(result, "nan_fraction")


# ---------------------------------------------------------------------------
# T-101.3 — Universe Screening
# ---------------------------------------------------------------------------

class TestUniverseScreening:
    """Universe.screen() filters out assets that fail quality thresholds."""

    def test_clean_assets_pass_screening(
        self, clean_df: pd.DataFrame
    ) -> None:
        assets = (UniverseAsset("GOOD", "EQUITY", date(2020, 1, 1)),)
        universe = Universe("test", "Test", assets)
        data = {"GOOD": clean_df}

        screened = universe.screen(data, min_history_days=252, max_nan_fraction=0.02)
        assert "GOOD" in screened.symbols()

    def test_short_history_excluded(
        self, clean_df: pd.DataFrame, short_df: pd.DataFrame
    ) -> None:
        assets = (
            UniverseAsset("LONG", "EQUITY", date(2020, 1, 1)),
            UniverseAsset("SHORT", "EQUITY", date(2023, 1, 1)),
        )
        universe = Universe("test", "Test", assets)
        data = {"LONG": clean_df, "SHORT": short_df}

        screened = universe.screen(data, min_history_days=252)
        assert "LONG" in screened.symbols()
        assert "SHORT" not in screened.symbols()

    def test_high_nan_excluded(
        self, clean_df: pd.DataFrame, nan_heavy_df: pd.DataFrame
    ) -> None:
        assets = (
            UniverseAsset("CLEAN", "EQUITY", date(2020, 1, 1)),
            UniverseAsset("NANSY", "EQUITY", date(2020, 1, 1)),
        )
        universe = Universe("test", "Test", assets)
        data = {"CLEAN": clean_df, "NANSY": nan_heavy_df}

        screened = universe.screen(data, max_nan_fraction=0.02)
        assert "CLEAN" in screened.symbols()
        assert "NANSY" not in screened.symbols()

    def test_missing_data_excluded(self, clean_df: pd.DataFrame) -> None:
        assets = (
            UniverseAsset("PRESENT", "EQUITY", date(2020, 1, 1)),
            UniverseAsset("ABSENT", "EQUITY", date(2020, 1, 1)),
        )
        universe = Universe("test", "Test", assets)
        data = {"PRESENT": clean_df}  # ABSENT not downloaded

        screened = universe.screen(data, min_history_days=252)
        assert "PRESENT" in screened.symbols()
        assert "ABSENT" not in screened.symbols()

    def test_returns_universe_instance(self, clean_df: pd.DataFrame) -> None:
        assets = (UniverseAsset("SPY", "EQUITY", date(1993, 1, 22)),)
        universe = Universe("test", "Test", assets)
        screened = universe.screen({"SPY": clean_df})
        assert isinstance(screened, Universe)

    def test_screened_universe_preserves_metadata(self, clean_df: pd.DataFrame) -> None:
        assets = (UniverseAsset("SPY", "EQUITY", date(1993, 1, 22)),)
        universe = Universe("s1", "Cross-asset ETF", assets)
        screened = universe.screen({"SPY": clean_df})
        assert screened.universe_id == "s1"
        assert screened.description == "Cross-asset ETF"


# ---------------------------------------------------------------------------
# T-101.4 — validate_universe_data helper
# ---------------------------------------------------------------------------

class TestValidateUniverseData:
    """validate_universe_data() runs validate_ohlcv per symbol, returns dict."""

    def test_returns_result_per_symbol(self, clean_df: pd.DataFrame) -> None:
        data = {"SPY": clean_df, "TLT": clean_df}
        results = validate_universe_data(data)
        assert set(results.keys()) == {"SPY", "TLT"}
        for r in results.values():
            assert isinstance(r, ValidationResult)

    def test_clean_data_all_valid(self, clean_df: pd.DataFrame) -> None:
        data = {"A": clean_df, "B": clean_df}
        results = validate_universe_data(data)
        assert all(r.is_valid for r in results.values())

    def test_mixed_data_reports_correctly(
        self, clean_df: pd.DataFrame, gapped_df: pd.DataFrame
    ) -> None:
        data = {"GOOD": clean_df, "BAD": gapped_df}
        results = validate_universe_data(data)
        assert results["GOOD"].is_valid
        assert not results["BAD"].is_valid

    def test_empty_dict_returns_empty(self) -> None:
        results = validate_universe_data({})
        assert results == {}
