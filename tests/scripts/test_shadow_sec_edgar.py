"""Read-only SEC EDGAR shadow report tests."""
from datetime import datetime, timezone

from scripts.shadow_sec_edgar import summarize_shadow
from src.models.news import NewsItem


def _item(item_id: str, day: int, title: str, tickers: list[str]) -> NewsItem:
    return NewsItem(
        id=item_id,
        source="sec_edgar",
        timestamp=datetime(2026, 9, day, 14, tzinfo=timezone.utc),
        title=title,
        body="Filing summary",
        url=f"https://www.sec.gov/Archives/{item_id}",
        asset_tags=tickers,
        extraction_method="source_metadata",
    )


def test_summarize_shadow_measures_volume_mapping_and_watchlist_audit():
    items = [
        _item("one", 4, "8-K - Apple Inc (0000320193) (Filer)", ["AAPL"]),
        _item("two", 4, "8-K - Unknown Corp (0000000001) (Filer)", []),
        _item("three", 3, "6-K - News Corp (0001564708) (Filer)", ["NWS", "NWSA"]),
    ]

    report = summarize_shadow(items, {"AAPL", "NWSA", "MSFT"})

    assert report["filings"] == 3
    assert report["tagged_filings"] == 2
    assert report["tagging_rate"] == 2 / 3
    assert report["volume_by_day"] == {"2026-09-03": 1, "2026-09-04": 2}
    assert report["watchlist_tickers"] == ["AAPL", "NWSA"]
    assert report["watchlist_coverage"] == 2 / 3
    assert report["watchlist_filings"] == 2
    assert report["tagging_audit"] == [
        {
            "title": "8-K - Apple Inc (0000320193) (Filer)",
            "matched_tickers": ["AAPL"],
            "url": "https://www.sec.gov/Archives/one",
        },
        {
            "title": "6-K - News Corp (0001564708) (Filer)",
            "matched_tickers": ["NWSA"],
            "url": "https://www.sec.gov/Archives/three",
        },
    ]
