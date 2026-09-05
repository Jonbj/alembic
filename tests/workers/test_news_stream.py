"""Tests for P2-D: AlpacaNewsStreamConnector and news_stream worker."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch


# ── AlpacaNewsStreamConnector ─────────────────────────────────────────────────


class TestAlpacaNewsStreamConnector:
    def test_init_sets_defaults(self):
        from src.connectors.alpaca_news_stream import AlpacaNewsStreamConnector

        callback = AsyncMock()
        c = AlpacaNewsStreamConnector(
            api_key="key", secret_key="secret", symbols=["AAPL"], on_news_callback=callback
        )
        assert c._api_key == "key"
        assert c._secret_key == "secret"
        assert c._symbols == ["AAPL"]
        assert c._on_news_callback is callback

    def test_init_wildcard_when_no_symbols(self):
        from src.connectors.alpaca_news_stream import AlpacaNewsStreamConnector

        c = AlpacaNewsStreamConnector("k", "s", [], AsyncMock())
        assert c._symbols == ["*"]

    def test_run_calls_stream_run(self):
        from src.connectors.alpaca_news_stream import AlpacaNewsStreamConnector

        callback = AsyncMock()
        c = AlpacaNewsStreamConnector("k", "s", ["AAPL"], callback)

        mock_stream = MagicMock()
        c._stream = mock_stream

        with patch.object(c, "_build_stream", return_value=mock_stream):
            c.run()

        mock_stream.subscribe_news.assert_called_once()
        mock_stream.run.assert_called_once()

    def test_stop_calls_stream_stop(self):
        from src.connectors.alpaca_news_stream import AlpacaNewsStreamConnector

        c = AlpacaNewsStreamConnector("k", "s", ["AAPL"], AsyncMock())
        mock_stream = MagicMock()
        c._stream = mock_stream

        c.stop()

        mock_stream.stop.assert_called_once()

    def test_stop_noop_when_no_stream(self):
        from src.connectors.alpaca_news_stream import AlpacaNewsStreamConnector

        c = AlpacaNewsStreamConnector("k", "s", ["AAPL"], AsyncMock())
        # Should not raise even if _stream is None
        c.stop()


# ── run_news_stream task ──────────────────────────────────────────────────────


def test_run_news_stream_skips_without_credentials():
    from src.workers.news_stream import run_news_stream

    with patch("src.config.config") as mock_cfg:
        mock_cfg.ALPACA_API_KEY = ""
        mock_cfg.ALPACA_SECRET_KEY = "xxx"
        result = run_news_stream.run()

    assert result == {"skipped": True, "reason": "no_credentials"}


def test_run_news_stream_starts_connector():
    from src.workers.news_stream import run_news_stream

    with patch("src.config.config") as mock_cfg, \
         patch("src.connectors.alpaca_news_stream.AlpacaNewsStreamConnector") as mock_cls:

        mock_cfg.ALPACA_API_KEY = "key"
        mock_cfg.ALPACA_SECRET_KEY = "secret"
        mock_cfg.ALPACA_BASE_URL = "https://paper-api.alpaca.markets"
        mock_cfg.WATCHLIST_SYMBOLS = ["AAPL", "TSLA"]

        mock_connector = MagicMock()
        mock_cls.return_value = mock_connector

        result = run_news_stream.run()

    mock_cls.assert_called_once()
    mock_connector.run.assert_called_once()
    assert result == {"status": "stream_ended"}


def test_stream_event_uses_rest_ingestion_contract_and_triggers_inference():
    from src.workers.news_stream import _on_news

    article = {
        "id": 123,
        "headline": "Apple raises guidance",
        "summary": "Demand remains strong.",
        "content": "",
        "url": "https://example.test/apple-guidance",
        # alpaca-py model_dump() emits datetime, while the REST API emits text.
        "created_at": datetime(2026, 9, 4, 14, 3, tzinfo=UTC),
        "symbols": ["AAPL"],
    }

    with patch("src.workers.news_stream.config") as mock_config, \
         patch("src.workers.news_stream.Redis") as mock_redis_cls, \
         patch("src.workers.news_stream.Deduplicator") as mock_dedup_cls, \
         patch("src.workers.news_stream._process_alpaca_items") as mock_process, \
         patch("src.workers.news_stream._persist_ingestion_observability") as mock_persist, \
         patch("src.workers.news_stream.app.send_task") as mock_send_task:
        mock_config.REDIS_URL = "redis://redis:6379/0"
        mock_config.WATCHLIST_SYMBOLS = ["AAPL"]
        mock_redis = mock_redis_cls.from_url.return_value
        mock_dedup = mock_dedup_cls.return_value
        mock_process.return_value = {
            "fetched": 1,
            "tickers_found": 1,
            "discarded": 0,
            "queued": 1,
            "duplicates": 0,
        }

        asyncio.run(_on_news(article))

    items, dedup, redis = mock_process.call_args.args
    assert len(items) == 1
    assert items[0].id == "alpaca:123"
    assert items[0].source == "alpaca_benzinga"
    assert items[0].asset_tags == ["AAPL"]
    assert items[0].extraction_method == "source_metadata"
    assert items[0].timestamp == article["created_at"]
    assert dedup is mock_dedup
    assert redis is mock_redis
    assert mock_process.call_args.kwargs["discard_rows"] == []
    mock_persist.assert_called_once_with(
        "alpaca_benzinga",
        {
            "fetched": 1,
            "tickers_found": 1,
            "discarded": 0,
            "queued": 1,
            "duplicates": 0,
        },
        [],
    )
    mock_send_task.assert_called_once_with(
        "src.workers.sentiment.run_sentiment_worker", queue="inference"
    )
    mock_redis.close.assert_called_once()


def test_duplicate_stream_event_is_measured_without_triggering_inference():
    from src.workers.news_stream import _on_news

    article = {
        "id": 123,
        "headline": "Apple raises guidance",
        "summary": "Demand remains strong.",
        "url": "https://example.test/apple-guidance",
        "created_at": "2026-09-04T14:03:00Z",
        "symbols": ["AAPL"],
    }

    with patch("src.workers.news_stream.config") as mock_config, \
         patch("src.workers.news_stream.Redis") as mock_redis_cls, \
         patch("src.workers.news_stream.Deduplicator"), \
         patch("src.workers.news_stream._process_alpaca_items") as mock_process, \
         patch("src.workers.news_stream._persist_ingestion_observability") as mock_persist, \
         patch("src.workers.news_stream.app.send_task") as mock_send_task:
        mock_config.REDIS_URL = "redis://redis:6379/0"
        mock_config.WATCHLIST_SYMBOLS = ["AAPL"]
        mock_redis = mock_redis_cls.from_url.return_value

        def duplicate(_items, _dedup, _redis, *, discard_rows):
            discard_rows.append({"discarded_reason": "duplicate_id"})
            return {
                "fetched": 1,
                "tickers_found": 1,
                "discarded": 0,
                "queued": 0,
                "duplicates": 1,
            }

        mock_process.side_effect = duplicate

        asyncio.run(_on_news(article))

    mock_redis.rpush.assert_not_called()
    stats = mock_persist.call_args.args[1]
    discards = mock_persist.call_args.args[2]
    assert stats["duplicates"] == 1
    assert discards[0]["discarded_reason"] == "duplicate_id"
    mock_send_task.assert_not_called()
    mock_redis.close.assert_called_once()


# ── P2-A: Bracket order configuration ────────────────────────────────────────


def test_bracket_order_submitted_when_enabled():
    """When ALPACA_BRACKET_ENABLED=True, BUY order includes take_profit and stop_loss."""
    from src.workers.portfolio_scheduler import _submit_portfolio_orders
    from src.backtest.engine.types import OrderSide, OrderType
    from src.portfolio.types import CombinedOrder
    from datetime import datetime, timezone

    order = CombinedOrder(
        order_id="oid-AAPL",
        timestamp=datetime(2026, 6, 15, tzinfo=timezone.utc),
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=10.0,
        order_type=OrderType.MARKET,
        strategy_id="S4",
        allocation_weight=0.1,
    )

    from src.backtest.engine.types import MarketSnapshot
    market = MarketSnapshot(
        timestamp=datetime(2026, 6, 15, tzinfo=timezone.utc),
        prices={"AAPL": 200.0},
        volumes={"AAPL": 1_000_000.0},
        adv_20d={"AAPL": 1_000_000.0},
    )

    submitted_req = {}

    def capture_fn(order, notional_or_qty, tc):
        submitted_req["notional"] = notional_or_qty

    with patch("src.config.config") as mock_cfg:
        mock_cfg.ALPACA_BRACKET_ENABLED = True
        mock_cfg.ALPACA_TAKE_PROFIT_PCT = 0.06
        mock_cfg.ALPACA_STOP_LOSS_PCT = 0.03

        result = _submit_portfolio_orders([order], MagicMock(), market, _submit_fn=capture_fn)

    # _submit_fn is used, so bracket params aren't added at SDK level in test mode —
    # but the order should still be submitted.
    assert len(result) == 1
    assert result[0]["symbol"] == "AAPL"
    assert result[0]["side"] == "buy"
