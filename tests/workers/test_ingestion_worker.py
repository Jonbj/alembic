"""Tests for NewsIngestionWorker (GDELT) and MarketAuxIngestionWorker."""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.news import GKGNewsItem, MarketAuxNewsItem, NewsItem


def make_marketaux_item(
    url: str,
    tickers: list[str],
    sentiment: float | None = 0.5,
    title: str = "Market news",
) -> MarketAuxNewsItem:
    return MarketAuxNewsItem(
        id=url,
        source="marketaux",
        timestamp=datetime.now(timezone.utc),
        title=title,
        body=title,
        url=url,
        language="en",
        asset_tags=tickers,
        marketaux_sentiment=sentiment,
    )


def make_gkg_item(
    url: str, org_names: list[str], title: str | None = None
) -> GKGNewsItem:
    title = title if title is not None else " ".join(org_names) or "Tech news"
    return GKGNewsItem(
        id=url,
        source="gdelt_gkg",
        timestamp=datetime.now(timezone.utc),
        title=title,
        body=title,
        url=url,
        language="en",
        asset_tags=[],
        org_names=org_names,
    )


@pytest.mark.asyncio
async def test_ingestion_worker_queues_item_with_ticker():
    """Article with known org name queues one NewsItem with ticker."""
    from src.workers.ingestion import _process_gkg_items

    gkg_items = [make_gkg_item("https://example.com/1", ["Apple Inc"])]
    mock_extractor = MagicMock()
    mock_extractor.extract.return_value = ["AAPL"]
    mock_dedup = MagicMock()
    mock_dedup.is_duplicate_content_symbol.return_value = False  # EN-03: only is_duplicate_by_id under test here
    mock_dedup.is_duplicate_by_id.return_value = False
    mock_redis = MagicMock()

    stats = _process_gkg_items(gkg_items, mock_extractor, mock_dedup, mock_redis)

    assert stats["queued"] == 1
    assert stats["discarded"] == 0
    assert mock_redis.rpush.call_count == 1
    pushed_data = json.loads(mock_redis.rpush.call_args[0][1])
    assert pushed_data["asset_tags"] == ["AAPL"]
    assert pushed_data["id"] == "https://example.com/1:AAPL"


@pytest.mark.asyncio
async def test_ingestion_worker_discards_no_ticker():
    """Article with no known org name is discarded."""
    from src.workers.ingestion import _process_gkg_items

    gkg_items = [make_gkg_item("https://example.com/2", ["Unknown Corp XYZ"])]
    mock_extractor = MagicMock()
    mock_extractor.extract.return_value = []
    mock_dedup = MagicMock()
    mock_dedup.is_duplicate_content_symbol.return_value = False  # EN-03: only is_duplicate_by_id under test here
    mock_redis = MagicMock()

    stats = _process_gkg_items(gkg_items, mock_extractor, mock_dedup, mock_redis)

    assert stats["discarded"] == 1
    assert stats["queued"] == 0
    mock_redis.rpush.assert_not_called()


def test_ingestion_worker_multi_ticker_article():
    """Article mentioning two orgs creates two separate NewsItems."""
    from src.workers.ingestion import _process_gkg_items

    gkg_items = [make_gkg_item("https://example.com/3", ["Apple Inc", "Microsoft Corporation"])]
    mock_extractor = MagicMock()
    mock_extractor.extract.return_value = ["AAPL", "MSFT"]
    mock_dedup = MagicMock()
    mock_dedup.is_duplicate_content_symbol.return_value = False  # EN-03: only is_duplicate_by_id under test here
    mock_dedup.is_duplicate_by_id.return_value = False
    mock_redis = MagicMock()

    stats = _process_gkg_items(gkg_items, mock_extractor, mock_dedup, mock_redis)

    assert stats["tickers_found"] == 2
    assert stats["queued"] == 2
    assert mock_redis.rpush.call_count == 2
    ids = [json.loads(c[0][1])["id"] for c in mock_redis.rpush.call_args_list]
    assert "https://example.com/3:AAPL" in ids
    assert "https://example.com/3:MSFT" in ids


def test_gkg_does_not_resolve_nokian_renkaat_to_nokia():
    """#243: a GDELT prefix false positive must not enqueue the similar issuer."""
    from src.workers.ingestion import _process_gkg_items

    headline = (
        "Head to Head Survey: Iochpe-Maxion (OTCMKTS:IOCJY) vs. "
        "Nokian Renkaat Oyj (OTCMKTS:NKRKF)"
    )
    item = make_gkg_item("https://example.com/nokian", ["Nokia"], headline)
    extractor = MagicMock()
    extractor.extract.return_value = ["NOK"]
    deduplicator = MagicMock()
    deduplicator.is_duplicate_by_id.return_value = False
    deduplicator.is_duplicate_content_symbol.return_value = False
    redis_client = MagicMock()

    stats = _process_gkg_items(
        [item], extractor, deduplicator, redis_client, watchlist={"NOK"}
    )

    assert stats["queued"] == 0
    assert stats["discarded"] == 1
    redis_client.rpush.assert_not_called()


def test_gkg_prefers_out_of_universe_otc_ticker_linked_to_org_name():
    """#243: an explicit OTC ticker prevents a similar watchlist attribution."""
    from src.workers.ingestion import _process_gkg_items

    headline = "Nokian Renkaat Oyj (OTCMKTS:NKRKF) reports earnings"
    item = make_gkg_item(
        "https://example.com/nokian-explicit", ["Nokian Renkaat Oyj"], headline
    )
    extractor = MagicMock()
    extractor.extract.return_value = ["NOK"]
    deduplicator = MagicMock()
    deduplicator.is_duplicate_by_id.return_value = False
    deduplicator.is_duplicate_content_symbol.return_value = False
    redis_client = MagicMock()

    stats = _process_gkg_items(
        [item], extractor, deduplicator, redis_client, watchlist={"NOK"}
    )

    assert stats["queued"] == 0
    assert stats["discarded"] == 1
    redis_client.rpush.assert_not_called()


@pytest.mark.parametrize(
    "headline",
    [
        "Invesco S&P 500 Revenue ETF (NYSEARCA:RWL) Reaches New 52-Week High",
        "Bank of America (NYSE:BAC) Reaches New 1-Year High - Here's Why",
        "Intel plans $15 billion share sale as turnaround rally lifts stock",
        "Versigent (NYSE:VGNT) Announces Earnings Results",
        "Cerebras slumps as mixed quarterly results test AI growth narrative",
        "Aflac (NYSE:AFL) Director Joseph Moskowitz Sells 600 Shares of Stock",
        "Brenntag (OTCMKTS:BNTGY) Posts Earnings Results, Beats Expectations",
        "Where Is Elon Musk Spending His Money in 2026?",
    ],
)
def test_gkg_rejects_observed_morgan_stanley_false_positives(headline):
    """#243: the issue's adjudicated-negative MS sample stays out of the queue."""
    from src.workers.ingestion import _process_gkg_items

    item = make_gkg_item(
        f"https://example.com/ms-false/{headline}", ["Morgan Stanley"], headline
    )
    extractor = MagicMock()
    extractor.extract.return_value = ["MS"]
    redis_client = MagicMock()

    stats = _process_gkg_items(
        [item], extractor, MagicMock(), redis_client, watchlist={"MS"}
    )

    assert stats["queued"] == 0
    assert stats["discarded"] == 1
    extractor.extract.assert_not_called()
    redis_client.rpush.assert_not_called()


@pytest.mark.parametrize(
    "headline",
    [
        "HPE Stock Jumps 6% on a Morgan Stanley Upgrade",
        "Morgan Stanley (MS) Stock News & Articles",
        "SpaceX shares can double, Morgan Stanley says",
        "Morgan Stanley Issues Pessimistic Forecast for BridgeBio Pharma (NASDAQ:BBIO) Stock Price",
        "Grocery Outlet (NASDAQ:GO) Price Target Raised to $11.00 at Morgan Stanley",
        "Morgan Stanley doubles down on SpaceX stock for investors",
        "HPE Stock Hits a 52-Week High After the Morgan Stanley Upgrade",
    ],
)
def test_gkg_keeps_observed_morgan_stanley_mentions(headline):
    """#243: the seven observed MS rows with textual evidence retain coverage."""
    from src.workers.ingestion import _process_gkg_items

    item = make_gkg_item(
        f"https://example.com/ms/{headline}", ["Morgan Stanley"], headline
    )
    extractor = MagicMock()
    extractor.extract.return_value = ["MS"]
    deduplicator = MagicMock()
    deduplicator.is_duplicate_by_id.return_value = False
    deduplicator.is_duplicate_content_symbol.return_value = False
    redis_client = MagicMock()

    stats = _process_gkg_items(
        [item], extractor, deduplicator, redis_client, watchlist={"MS"}
    )

    assert stats["queued"] == 1
    assert stats["discarded"] == 0


def test_ingestion_worker_dedup_blocks_second():
    """Duplicate (url, ticker) combination is not queued twice."""
    from src.workers.ingestion import _process_gkg_items

    gkg_items = [
        make_gkg_item("https://example.com/4", ["Apple Inc"]),
        make_gkg_item("https://example.com/4", ["Apple Inc"]),
    ]
    mock_extractor = MagicMock()
    mock_extractor.extract.return_value = ["AAPL"]

    call_count = {"n": 0}

    def dedup_side_effect(item):
        call_count["n"] += 1
        return call_count["n"] > 1  # first is False, subsequent True

    mock_dedup = MagicMock()
    mock_dedup.is_duplicate_content_symbol.return_value = False  # EN-03: only is_duplicate_by_id under test here
    mock_dedup.is_duplicate_by_id.side_effect = dedup_side_effect
    mock_redis = MagicMock()

    stats = _process_gkg_items(gkg_items, mock_extractor, mock_dedup, mock_redis)

    assert stats["queued"] == 1
    assert stats["duplicates"] == 1


def test_ingestion_worker_returns_correct_stats():
    """Stats dict contains all expected keys with correct values."""
    from src.workers.ingestion import _process_gkg_items

    gkg_items = [
        make_gkg_item("https://a.com/1", ["Apple Inc"]),
        make_gkg_item("https://a.com/2", []),
    ]
    mock_extractor = MagicMock()
    mock_extractor.extract.side_effect = [["AAPL"], []]
    mock_dedup = MagicMock()
    mock_dedup.is_duplicate_content_symbol.return_value = False  # EN-03: only is_duplicate_by_id under test here
    mock_dedup.is_duplicate_by_id.return_value = False
    mock_redis = MagicMock()

    stats = _process_gkg_items(gkg_items, mock_extractor, mock_dedup, mock_redis)

    assert stats["fetched"] == 2
    assert stats["tickers_found"] == 1
    assert stats["discarded"] == 1
    assert stats["queued"] == 1
    assert stats["duplicates"] == 0


# --- MarketAux ingestion ---

def test_marketaux_process_queues_per_ticker():
    """Multi-ticker MarketAux item creates one queue entry per ticker."""
    from src.workers.ingestion import _process_marketaux_items

    items = [make_marketaux_item("https://ma.com/1", ["NVDA", "AMD"], sentiment=0.7)]
    mock_dedup = MagicMock()
    mock_dedup.is_duplicate_content_symbol.return_value = False  # EN-03: only is_duplicate_by_id under test here
    mock_dedup.is_duplicate_by_id.return_value = False
    mock_redis = MagicMock()

    stats = _process_marketaux_items(items, mock_dedup, mock_redis)

    assert stats["queued"] == 2
    assert stats["tickers_found"] == 2
    ids = [json.loads(c[0][1])["id"] for c in mock_redis.rpush.call_args_list]
    assert "https://ma.com/1:NVDA" in ids
    assert "https://ma.com/1:AMD" in ids


def test_marketaux_process_preserves_sentiment_per_ticker():
    """Each per-ticker item retains the article-level marketaux_sentiment."""
    from src.workers.ingestion import _process_marketaux_items

    items = [make_marketaux_item("https://ma.com/2", ["AAPL"], sentiment=0.65)]
    mock_dedup = MagicMock()
    mock_dedup.is_duplicate_content_symbol.return_value = False  # EN-03: only is_duplicate_by_id under test here
    mock_dedup.is_duplicate_by_id.return_value = False
    mock_redis = MagicMock()

    _process_marketaux_items(items, mock_dedup, mock_redis)

    pushed = json.loads(mock_redis.rpush.call_args[0][1])
    assert pushed["marketaux_sentiment"] == pytest.approx(0.65)
    assert pushed["asset_tags"] == ["AAPL"]


def test_marketaux_process_dedup():
    """Duplicate MarketAux items are not queued twice."""
    from src.workers.ingestion import _process_marketaux_items

    items = [
        make_marketaux_item("https://ma.com/3", ["MSFT"]),
        make_marketaux_item("https://ma.com/3", ["MSFT"]),
    ]
    call_count = {"n": 0}

    def dedup_side(item):
        call_count["n"] += 1
        return call_count["n"] > 1

    mock_dedup = MagicMock()
    mock_dedup.is_duplicate_content_symbol.return_value = False  # EN-03: only is_duplicate_by_id under test here
    mock_dedup.is_duplicate_by_id.side_effect = dedup_side
    mock_redis = MagicMock()

    stats = _process_marketaux_items(items, mock_dedup, mock_redis)

    assert stats["queued"] == 1
    assert stats["duplicates"] == 1


@pytest.mark.parametrize(
    ("id_duplicate", "content_duplicate", "expected_reason"),
    [
        (True, False, "duplicate_id"),
        (False, True, "duplicate_content"),
    ],
)
def test_marketaux_process_records_why_duplicate_was_discarded(
    id_duplicate, content_duplicate, expected_reason
):
    """FIX-06: the two dedup gates must remain distinguishable in evidence."""
    from src.workers.ingestion import _process_marketaux_items

    items = [make_marketaux_item("https://ma.com/discard", ["AAPL"])]
    mock_dedup = MagicMock()
    mock_dedup.is_duplicate_by_id.return_value = id_duplicate
    mock_dedup.is_duplicate_content_symbol.return_value = content_duplicate
    discard_rows = []

    stats = _process_marketaux_items(
        items, mock_dedup, MagicMock(), discard_rows=discard_rows
    )

    assert stats["duplicates"] == 1
    assert len(discard_rows) == 1
    assert discard_rows[0]["discarded_reason"] == expected_reason
    assert discard_rows[0]["discard_stage"] == "ingestion"
    assert discard_rows[0]["source"] == "marketaux"
    assert discard_rows[0]["symbol"] == "AAPL"


def test_marketaux_process_skips_no_tickers():
    """Items with empty asset_tags are silently skipped."""
    from src.workers.ingestion import _process_marketaux_items

    items = [make_marketaux_item("https://ma.com/4", [], sentiment=0.8)]
    mock_dedup = MagicMock()
    mock_dedup.is_duplicate_content_symbol.return_value = False  # EN-03: only is_duplicate_by_id under test here
    mock_redis = MagicMock()

    stats = _process_marketaux_items(items, mock_dedup, mock_redis)

    assert stats["queued"] == 0
    mock_redis.rpush.assert_not_called()


def test_marketaux_process_records_missing_ticker_discard():
    """FIX-06: an untagged article must not disappear before the source funnel."""
    from src.workers.ingestion import _process_marketaux_items

    item = make_marketaux_item("https://ma.com/no-ticker", [], sentiment=0.8)
    discard_rows = []

    _process_marketaux_items(
        [item], MagicMock(), MagicMock(), discard_rows=discard_rows
    )

    assert discard_rows[0]["discarded_reason"] == "no_ticker"
    assert discard_rows[0]["item_id"] == item.id
    assert discard_rows[0]["symbol"] is None


# --- Alpaca ingestion ---

def make_alpaca_item(url: str, tickers: list[str], title: str = "Benzinga news") -> NewsItem:
    return NewsItem(
        id=f"alpaca:{url}",
        source="alpaca_benzinga",
        timestamp=datetime.now(timezone.utc),
        title=title,
        body=title,
        url=url,
        language="en",
        asset_tags=tickers,
    )


def test_alpaca_process_queues_per_ticker():
    """Multi-ticker Alpaca item creates one queue entry per ticker."""
    from src.workers.ingestion import _process_alpaca_items

    items = [make_alpaca_item("https://bz.com/1", ["AAPL", "MSFT"])]
    mock_dedup = MagicMock()
    mock_dedup.is_duplicate_content_symbol.return_value = False  # EN-03: only is_duplicate_by_id under test here
    mock_dedup.is_duplicate_by_id.return_value = False
    mock_redis = MagicMock()

    stats = _process_alpaca_items(items, mock_dedup, mock_redis)

    assert stats["queued"] == 2
    assert stats["tickers_found"] == 2
    ids = [json.loads(c[0][1])["id"] for c in mock_redis.rpush.call_args_list]
    assert "alpaca:https://bz.com/1:AAPL" in ids
    assert "alpaca:https://bz.com/1:MSFT" in ids


def test_alpaca_process_single_ticker_per_item():
    """Each per-ticker item has asset_tags=[ticker] and correct source."""
    from src.workers.ingestion import _process_alpaca_items

    items = [make_alpaca_item("https://bz.com/2", ["NVDA"])]
    mock_dedup = MagicMock()
    mock_dedup.is_duplicate_content_symbol.return_value = False  # EN-03: only is_duplicate_by_id under test here
    mock_dedup.is_duplicate_by_id.return_value = False
    mock_redis = MagicMock()

    _process_alpaca_items(items, mock_dedup, mock_redis)

    pushed = json.loads(mock_redis.rpush.call_args[0][1])
    assert pushed["asset_tags"] == ["NVDA"]
    assert pushed["source"] == "alpaca_benzinga"
    assert "marketaux_sentiment" not in pushed


def test_alpaca_process_dedup():
    """Duplicate Alpaca items are not queued twice."""
    from src.workers.ingestion import _process_alpaca_items

    items = [
        make_alpaca_item("https://bz.com/3", ["TSLA"]),
        make_alpaca_item("https://bz.com/3", ["TSLA"]),
    ]
    call_count = {"n": 0}

    def dedup_side(item):
        call_count["n"] += 1
        return call_count["n"] > 1

    mock_dedup = MagicMock()
    mock_dedup.is_duplicate_content_symbol.return_value = False  # EN-03: only is_duplicate_by_id under test here
    mock_dedup.is_duplicate_by_id.side_effect = dedup_side
    mock_redis = MagicMock()

    stats = _process_alpaca_items(items, mock_dedup, mock_redis)

    assert stats["queued"] == 1
    assert stats["duplicates"] == 1


def test_alpaca_process_skips_no_tickers():
    """Alpaca items with empty asset_tags are silently skipped."""
    from src.workers.ingestion import _process_alpaca_items

    items = [make_alpaca_item("https://bz.com/4", [])]
    mock_dedup = MagicMock()
    mock_dedup.is_duplicate_content_symbol.return_value = False  # EN-03: only is_duplicate_by_id under test here
    mock_redis = MagicMock()

    stats = _process_alpaca_items(items, mock_dedup, mock_redis)

    assert stats["queued"] == 0
    mock_redis.rpush.assert_not_called()


def test_gkg_watchlist_filter_records_not_tradable_discard():
    """A resolved ticker outside the trading universe is not a no-ticker miss."""
    from src.workers.ingestion import _process_gkg_items

    item = make_gkg_item("https://gkg.com/off-watchlist", ["Acme Corp"])
    extractor = MagicMock()
    extractor.extract.return_value = ["ACME"]
    discard_rows = []

    _process_gkg_items(
        [item],
        extractor,
        MagicMock(),
        MagicMock(),
        watchlist={"AAPL"},
        discard_rows=discard_rows,
    )

    assert discard_rows[0]["discarded_reason"] == "not_tradable"
    assert discard_rows[0]["symbol"] == "ACME"


def test_alpaca_ingestion_skips_when_market_closed():
    """WS-4: beat schedule is hardcoded UTC; task exits early when market closed."""
    from unittest.mock import patch

    from src.workers.ingestion import run_alpaca_ingestion_worker

    with patch("src.workers.ingestion.is_market_open", return_value=False), \
         patch("src.workers.ingestion.Redis") as mock_redis:
        result = run_alpaca_ingestion_worker()

    assert result["skipped"] is True
    assert result["reason"] == "market_closed"
    mock_redis.from_url.return_value.close.assert_called_once()


def test_gdelt_ingestion_skips_when_market_closed():
    """WS-4: GDELT ingestion exits early when US market is closed."""
    from unittest.mock import patch

    from src.workers.ingestion import run_news_ingestion_worker

    with patch("src.workers.ingestion.is_market_open", return_value=False):
        result = run_news_ingestion_worker()

    assert result["skipped"] is True
    assert result["reason"] == "market_closed"
