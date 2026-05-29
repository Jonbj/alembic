"""Tests for universe management."""
from datetime import date
from pathlib import Path

import pytest
import yaml

from src.backtest.data.universe import Universe, UniverseAsset, load_universe


@pytest.fixture
def universe_yaml(tmp_path: Path) -> Path:
    config = {
        "test_universe": {
            "description": "Test universe",
            "tickers": [
                {"symbol": "SPY", "asset_class": "US_EQUITY_LARGE", "inception": "1993-01-22"},
                {"symbol": "TLT", "asset_class": "UST_LONG", "inception": "2002-07-22"},
                {"symbol": "GLD", "asset_class": "GOLD", "inception": "2004-11-18"},
            ],
        }
    }
    p = tmp_path / "universe.yaml"
    p.write_text(yaml.dump(config))
    return p


class TestUniverseAsset:
    def test_from_dict(self) -> None:
        asset = UniverseAsset.from_dict(
            {"symbol": "SPY", "asset_class": "US_EQUITY_LARGE", "inception": "1993-01-22"}
        )
        assert asset.symbol == "SPY"
        assert asset.asset_class == "US_EQUITY_LARGE"
        assert asset.inception_date == date(1993, 1, 22)


class TestUniverse:
    def test_active_at_filters_by_inception(self) -> None:
        assets = (
            UniverseAsset("SPY", "EQUITY", date(1993, 1, 22)),
            UniverseAsset("GLD", "GOLD", date(2004, 11, 18)),
        )
        universe = Universe("test", "Test", assets)

        active_2000 = universe.active_at(date(2000, 1, 1))
        assert len(active_2000) == 1
        assert active_2000[0].symbol == "SPY"

        active_2010 = universe.active_at(date(2010, 1, 1))
        assert len(active_2010) == 2

    def test_symbols(self) -> None:
        assets = (
            UniverseAsset("SPY", "EQUITY", date(1993, 1, 22)),
            UniverseAsset("TLT", "BOND", date(2002, 7, 22)),
        )
        universe = Universe("test", "Test", assets)
        assert set(universe.symbols()) == {"SPY", "TLT"}

    def test_by_symbol(self) -> None:
        assets = (UniverseAsset("SPY", "EQUITY", date(1993, 1, 22)),)
        universe = Universe("test", "Test", assets)

        assert universe.by_symbol("SPY") is not None
        assert universe.by_symbol("UNKNOWN") is None


class TestLoadUniverse:
    def test_load_from_yaml(self, universe_yaml: Path) -> None:
        universe = load_universe("test", config_path=universe_yaml)
        assert universe.universe_id == "test"
        assert len(universe.assets) == 3
        assert universe.symbols() == ("SPY", "TLT", "GLD")

    def test_missing_universe_raises(self, universe_yaml: Path) -> None:
        with pytest.raises(ValueError, match="Universe 'missing' not found"):
            load_universe("missing", config_path=universe_yaml)

    def test_load_s1_universe_from_real_config(self) -> None:
        """Verify the real config/universe.yaml has 15 S1 tickers."""
        universe = load_universe("s1", config_path=Path("config/universe.yaml"))
        assert len(universe.assets) == 15
        symbols = universe.symbols()
        assert "SPY" in symbols
        assert "TLT" in symbols
        assert "GLD" in symbols
