"""Tests for zeygos_parser — uses real fixture PDFs from reports/Zeygos/."""

import pytest
from datetime import date
from pathlib import Path

from src.connectors.zeygos_parser import (
    ZeygosParseError,
    ZeygosRow,
    normalize_ticker,
    parse_zeygos_pdf,
)

_REPORTS_DIR = Path(__file__).parents[2] / "reports" / "Zeygos"
_PDF_APR = _REPORTS_DIR / "Report_Settoriale_Zeygos_20260430.pdf"
_PDF_JUN = _REPORTS_DIR / "Report_Settoriale_Zeygos_20260605.pdf"


# ── normalize_ticker ──────────────────────────────────────────────────────────

class TestNormalizeTicker:
    def test_strips_nyse_suffix(self):
        assert normalize_ticker("NEM.N") == "NEM"

    def test_strips_nasdaq_oq_suffix(self):
        assert normalize_ticker("APH.OQ") == "APH"

    def test_strips_nasdaq_k_suffix(self):
        assert normalize_ticker("CVSA.K") == "CVSA"

    def test_keeps_london_suffix(self):
        assert normalize_ticker("GLEN.L") == "GLEN.L"

    def test_keeps_paris_suffix(self):
        assert normalize_ticker("OREP.PA") == "OREP.PA"

    def test_keeps_milan_suffix(self):
        assert normalize_ticker("A2.MI") == "A2.MI"

    def test_keeps_frankfurt_suffix(self):
        assert normalize_ticker("NDXG.DE") == "NDXG.DE"

    def test_no_suffix_unchanged(self):
        assert normalize_ticker("AAPL") == "AAPL"


# ── parse_zeygos_pdf — April report ──────────────────────────────────────────

@pytest.mark.skipif(not _PDF_APR.exists(), reason="fixture PDF not present")
class TestParseAprilReport:
    @pytest.fixture(scope="class")
    def rows(self):
        return parse_zeygos_pdf(_PDF_APR.read_bytes())

    def test_returns_list_of_zeygos_rows(self, rows):
        assert all(isinstance(r, ZeygosRow) for r in rows)

    def test_report_date_is_april_30(self, rows):
        assert rows[0].report_date == date(2026, 4, 30)

    def test_minimum_row_count(self, rows):
        # 11 USA sectors × 5 + 10 EU sectors × 5 = 105 max; expect at least 50
        assert len(rows) >= 50

    def test_usa_and_eu_markets_present(self, rows):
        markets = {r.market for r in rows}
        assert "USA" in markets
        assert "EU" in markets

    def test_top_basic_materials_usa_is_nem(self, rows):
        nem = next(
            (r for r in rows if r.ticker == "NEM" and r.sector == "Basic Materials"),
            None,
        )
        assert nem is not None
        assert nem.rank == 1
        assert nem.score_finale == pytest.approx(73.3, abs=0.2)

    def test_ranks_are_sequential_per_sector_market(self, rows):
        from collections import defaultdict
        groups: dict = defaultdict(list)
        for r in rows:
            groups[(r.market, r.sector)].append(r.rank)
        for key, ranks in groups.items():
            assert sorted(ranks) == list(range(1, len(ranks) + 1)), (
                f"Non-sequential ranks for {key}: {ranks}"
            )

    def test_score_finale_in_valid_range(self, rows):
        for r in rows:
            assert 1.0 <= r.score_finale <= 100.0, (
                f"{r.ticker_refinitiv} score_finale={r.score_finale} out of range"
            )

    def test_us_tickers_have_no_exchange_suffix(self, rows):
        us_rows = [r for r in rows if r.market == "USA"]
        for r in us_rows:
            assert "." not in r.ticker, (
                f"US ticker still has suffix: {r.ticker_refinitiv} → {r.ticker}"
            )

    def test_eu_tickers_retain_suffix(self, rows):
        eu_rows = [r for r in rows if r.market == "EU"]
        assert any("." in r.ticker for r in eu_rows), (
            "No EU tickers retained exchange suffix"
        )

    def test_company_name_not_empty(self, rows):
        empty = [r for r in rows if not r.company_name]
        assert not empty, f"Empty company names: {[r.ticker_refinitiv for r in empty]}"


# ── parse_zeygos_pdf — June report ───────────────────────────────────────────

@pytest.mark.skipif(not _PDF_JUN.exists(), reason="fixture PDF not present")
class TestParseJuneReport:
    @pytest.fixture(scope="class")
    def rows(self):
        return parse_zeygos_pdf(_PDF_JUN.read_bytes())

    def test_report_date_is_june_5(self, rows):
        assert rows[0].report_date == date(2026, 6, 5)

    def test_minimum_row_count(self, rows):
        assert len(rows) >= 50

    def test_adsk_is_top_technology(self, rows):
        adsk = next(
            (r for r in rows if r.ticker == "ADSK" and r.sector == "Technology"),
            None,
        )
        assert adsk is not None
        assert adsk.rank == 1
        assert adsk.score_finale == pytest.approx(75.9, abs=0.2)


# ── error cases ───────────────────────────────────────────────────────────────

class TestParseErrors:
    def test_raises_on_garbage_bytes(self):
        with pytest.raises(Exception):
            parse_zeygos_pdf(b"not a pdf")

    def test_raises_parse_error_on_too_few_rows(self, tmp_path):
        """PDF with no Zeygos tables should raise ZeygosParseError."""
        import pdfplumber
        # Create a minimal valid PDF with no tables using reportlab if available,
        # otherwise just verify the exception type from empty bytes.
        try:
            from reportlab.pdfgen import canvas
            p = tmp_path / "empty.pdf"
            c = canvas.Canvas(str(p))
            c.drawString(100, 750, "This is not a Zeygos report - 01 Gennaio 2026")
            c.save()
            with pytest.raises(ZeygosParseError, match="rows extracted"):
                parse_zeygos_pdf(p.read_bytes())
        except ImportError:
            pytest.skip("reportlab not installed — skipping minimal-PDF test")
