"""Copertura dei tier di costo sulla watchlist (#245).

`cost_model.yaml` assegna un tier esplicito a una parte dei simboli; tutti gli altri
cadono nel default `tier_d`, descritto come "small-cap, illiquid" a 20 bps. Il fallback
è corretto per un simbolo davvero sconosciuto, non per uno che abbiamo deliberatamente
messo in watchlist: il costo modellato viene sottratto da `trades.net_pnl`, quindi un
tier sbagliato falsa la serie economica su cui il periodo di osservazione giudica le
strategie.

Seam sotto test: l'interfaccia pubblica di `TradeCostCalculator`. I test non guardano
`_symbol_tier` né `_tier()` — sono interni e devono poter cambiare.
"""
from pathlib import Path

import pytest
import yaml

from src.costs.calculator import TradeCostCalculator

CONFIG = Path("config/cost_model.yaml")
TRADING = Path("config/trading.yaml")

# Il default dichiarato in cost_model.yaml (tier_d). Costante attesa, non ricalcolata
# dal file: se qualcuno cambia il default, questi test devono accorgersene.
DEFAULT_SPREAD_BPS = 20.0


@pytest.fixture
def calc():
    return TradeCostCalculator(config_path=CONFIG)


@pytest.fixture
def watchlist() -> list[str]:
    cfg = yaml.safe_load(TRADING.read_text())
    return [s.upper() for s in cfg["symbols"]["watchlist"]]


class TestUncoveredSymbols:
    """`uncovered_symbols` risponde: quali di questi simboli userebbero il default?"""

    def test_reports_a_symbol_with_no_explicit_tier(self, calc):
        assert calc.uncovered_symbols(["DEFINITELY_NOT_A_TICKER"]) == ["DEFINITELY_NOT_A_TICKER"]

    def test_does_not_report_a_symbol_with_an_explicit_tier(self, calc):
        # SPY è esplicitamente in tier_a.
        assert calc.uncovered_symbols(["SPY"]) == []

    def test_is_case_insensitive_like_the_tier_lookup(self, calc):
        assert calc.uncovered_symbols(["spy"]) == []

    def test_preserves_input_order_and_reports_only_the_uncovered(self, calc):
        result = calc.uncovered_symbols(["SPY", "NOT_A_TICKER", "INTC", "ALSO_NOT_ONE"])
        assert result == ["NOT_A_TICKER", "ALSO_NOT_ONE"]

    def test_empty_input_reports_nothing(self, calc):
        assert calc.uncovered_symbols([]) == []


class TestWatchlistIsFullyCovered:
    """Il contratto vero: nessun simbolo tradabile deve cadere nel default."""

    def test_no_watchlist_symbol_falls_back_to_the_default_tier(self, calc, watchlist):
        uncovered = calc.uncovered_symbols(watchlist)
        assert uncovered == [], (
            f"{len(uncovered)} simboli di watchlist usano il tier default "
            f"('small-cap, illiquid', {DEFAULT_SPREAD_BPS} bps) e falsano net_pnl: {uncovered}"
        )

    @pytest.mark.parametrize("symbol", ["IBM", "SONY", "HOOD", "SPCX", "NOK"])
    def test_symbols_named_in_the_issue_are_not_priced_as_illiquid(self, calc, symbol):
        """I casi concreti misurati in #245 su trade reali (SONY 20,244 bps, IBM 20,246)."""
        breakdown = calc.compute(
            symbol=symbol, notional=1_000.0, qty=10.0, fill_price=100.0, side="BUY"
        )
        assert breakdown.spread_cost_bps < DEFAULT_SPREAD_BPS, (
            f"{symbol} è in watchlist ma è prezzato al tier illiquido di default"
        )
