"""QT-03: extraction_method provenance set by the connectors and carried through."""
from src.connectors.marketaux import MarketAuxConnector
from src.models.news import NewsItem


def _art(description, entities=None):
    a = {"title": "t", "description": description, "url": "u",
         "published_at": "2025-11-01T00:00:00Z"}
    if entities is not None:
        a["entities"] = entities
    return a


class TestMarketauxExtractionMethod:
    def _conn(self):
        return MarketAuxConnector(api_key="k", symbols=["AAPL"])

    def test_source_metadata_when_entities(self):
        item = self._conn()._parse_article(_art("Apple beat.", entities=[{"symbol": "AAPL", "sentiment_score": 0.5}]))
        assert item.asset_tags == ["AAPL"]
        assert item.extraction_method == "source_metadata"

    def test_cashtag_when_no_entities(self):
        item = self._conn()._parse_article(_art("Big day for $AAPL today."))
        assert item.asset_tags == ["AAPL"]
        assert item.extraction_method == "cashtag"

    def test_empty_when_no_ticker(self):
        item = self._conn()._parse_article(_art("Macro outlook, rates steady, no companies."))
        assert item.asset_tags == []
        assert item.extraction_method == ""


def test_extraction_method_round_trips_json():
    item = NewsItem(id="x", body="b", title="t", url="u", asset_tags=["AAPL"], extraction_method="org_lookup")
    restored = NewsItem.model_validate_json(item.model_dump_json())
    assert restored.extraction_method == "org_lookup"


def test_default_extraction_method_empty():
    assert NewsItem(id="x", body="b").extraction_method == ""
