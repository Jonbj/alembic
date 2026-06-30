"""Tests for the ticker-resolver evidence providers (OpenFIGI, SEC, gather_evidence)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.connectors.ticker_resolver_providers import (
    OpenFigiClient,
    SecCompanyTickers,
    gather_evidence,
)

_MOD = "src.connectors.ticker_resolver_providers.httpx"


def _resp(payload):
    r = MagicMock()
    r.raise_for_status = MagicMock()
    r.json.return_value = payload
    return r


class TestOpenFigiClient:
    _AAPL = [{"data": [{"figi": "BBG000B9XRY4", "name": "APPLE INC",
                        "exchCode": "US", "securityType": "Common Stock"}]}]

    def test_lookup_success(self):
        with patch(f"{_MOD}.post", return_value=_resp(self._AAPL)):
            r = OpenFigiClient(api_key="k").lookup("AAPL")
        assert r["figi"] == "BBG000B9XRY4"
        assert r["securityType"] == "Common Stock"
        assert r["exchCode"] == "US"

    def test_lookup_cached(self):
        c = OpenFigiClient()
        with patch(f"{_MOD}.post", return_value=_resp(self._AAPL)) as mp:
            c.lookup("AAPL")
            c.lookup("AAPL")
        assert mp.call_count == 1  # second call served from cache

    def test_lookup_error_returns_none(self):
        with patch(f"{_MOD}.post", side_effect=Exception("net down")):
            assert OpenFigiClient().lookup("AAPL") is None

    def test_lookup_empty_data_none(self):
        with patch(f"{_MOD}.post", return_value=_resp([{"warning": "no match"}])):
            assert OpenFigiClient().lookup("ZZZZ") is None


class TestSecCompanyTickers:
    _DATA = {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp"},
    }

    def test_name_and_confirm(self):
        with patch(f"{_MOD}.get", return_value=_resp(self._DATA)):
            sec = SecCompanyTickers("ua")
            assert sec.ticker_for_name("Apple Inc.") == "AAPL"
            assert sec.confirms("AAPL", "Apple Inc.") is True
            assert sec.confirms("AAPL") is True
            assert sec.confirms("ZZZZ") is False
            assert sec.confirms("AAPL", "Microsoft") is False  # name maps to a different ticker

    def test_load_error_fail_open(self):
        with patch(f"{_MOD}.get", side_effect=Exception("net down")):
            sec = SecCompanyTickers("ua")
            assert sec.ticker_for_name("Apple") is None
            assert sec.confirms("AAPL") is False

    def test_loads_once(self):
        with patch(f"{_MOD}.get", return_value=_resp(self._DATA)) as mg:
            sec = SecCompanyTickers("ua")
            sec.confirms("AAPL")
            sec.ticker_for_name("Microsoft Corp")
        assert mg.call_count == 1


class TestGatherEvidence:
    def test_combines_all_sources(self):
        sec = MagicMock(); sec.confirms.return_value = True
        figi = MagicMock()
        figi.lookup.return_value = {"figi": "F", "exchCode": "US", "securityType": "Common Stock", "name": "APPLE INC"}
        ev = gather_evidence(
            "AAPL", company_name="Apple Inc.", from_reliable_source=True, llm_proposed=True,
            alias_tickers={"AAPL"}, tradable_symbols={"AAPL"}, openfigi=figi, sec=sec,
        )
        assert ev.source_ticker_match and ev.alias_match and ev.sec_openfigi_match
        assert ev.llm_agreement and ev.tradable
        assert ev.figi == "F" and ev.exchange == "US"

    def test_not_tradable(self):
        ev = gather_evidence("XYZ", tradable_symbols={"AAPL"})
        assert ev.tradable is False

    def test_tradable_unknown_fail_open(self):
        ev = gather_evidence("XYZ", tradable_symbols=None)
        assert ev.tradable is True

    def test_figi_non_equity_not_a_match(self):
        figi = MagicMock()
        figi.lookup.return_value = {"securityType": "Warrant", "figi": "F", "exchCode": "US"}
        ev = gather_evidence("XYZ", openfigi=figi)  # warrant → not an equity → no sec/figi match
        assert ev.sec_openfigi_match is False

    def test_alias_only(self):
        ev = gather_evidence("AAPL", alias_tickers={"AAPL"})
        assert ev.alias_match is True
        assert ev.source_ticker_match is False
