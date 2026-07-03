"""Resolver shadow mode: persist verdicts without affecting signals; fail-safe."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.connectors import resolver_shadow


def _item(tags, method="cashtag", url="u", item_id="u"):
    return SimpleNamespace(asset_tags=tags, extraction_method=method, url=url, id=item_id)


def test_writes_verdict_per_item():
    items = [_item(["AAPL"], "cashtag", item_id="u:AAPL")]
    mock_pg = MagicMock()
    with patch.object(resolver_shadow, "_providers", return_value=(None, None)), \
         patch.object(resolver_shadow, "_tradable_symbols", return_value={"AAPL"}):
        verdicts = resolver_shadow.resolve_and_log_shadow(items, mock_pg)

    mock_pg.write_resolved_entity.assert_called_once()
    kw = mock_pg.write_resolved_entity.call_args.kwargs
    assert kw["candidate_ticker"] == "AAPL"
    assert kw["extraction_method"] == "cashtag"
    assert hasattr(kw["verdict"], "decision")          # ResolvedTicker
    assert len(verdicts) == 1
    assert verdicts["u:AAPL"] == kw["verdict"].decision
    assert kw["evidence"].source_ticker_match is True   # cashtag → reliable source


def test_skips_items_without_ticker():
    mock_pg = MagicMock()
    with patch.object(resolver_shadow, "_providers", return_value=(None, None)), \
         patch.object(resolver_shadow, "_tradable_symbols", return_value=None):
        verdicts = resolver_shadow.resolve_and_log_shadow([_item([])], mock_pg)
    assert verdicts == {}
    mock_pg.write_resolved_entity.assert_not_called()


def test_fail_safe_on_store_error():
    mock_pg = MagicMock()
    mock_pg.write_resolved_entity.side_effect = RuntimeError("db down")
    with patch.object(resolver_shadow, "_providers", return_value=(None, None)), \
         patch.object(resolver_shadow, "_tradable_symbols", return_value={"AAPL"}):
        verdicts = resolver_shadow.resolve_and_log_shadow([_item(["AAPL"])], mock_pg)  # no raise
    assert verdicts == {}
