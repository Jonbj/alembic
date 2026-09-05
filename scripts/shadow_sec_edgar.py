#!/usr/bin/env python3
"""Measure the corrected SEC EDGAR connector without touching the live pipeline.

The command only reads the public SEC Latest Filings feeds and company_tickers
mapping. It does not set SEC_EDGAR_INGESTION_ENABLED, enqueue news, write to the
database, or alter evidence ledgers.

Use the ``tagging_audit`` rows to verify issuer/ticker precision against the linked
official filing before an operator considers enabling the source.

Usage:
    python -m scripts.shadow_sec_edgar --max-results 100
"""
from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from datetime import datetime, timezone

from src.config import config
from src.connectors.sec_edgar import SECEdgarConnector
from src.models.news import NewsItem


def summarize_shadow(
    items: list[NewsItem],
    watchlist: set[str],
    *,
    audit_limit: int | None = None,
) -> dict:
    """Build read-only coverage and mapping metrics from a connector sample."""
    tagged = [item for item in items if item.asset_tags]
    volume_by_day = Counter(item.timestamp.date().isoformat() for item in items)
    matched_tickers: set[str] = set()
    matched_items: list[tuple[NewsItem, list[str]]] = []

    for item in items:
        matches = sorted(set(item.asset_tags) & watchlist)
        if matches:
            matched_tickers.update(matches)
            matched_items.append((item, matches))

    audit_rows = [
        {
            "title": item.title,
            "matched_tickers": matches,
            "url": item.url,
        }
        for item, matches in matched_items[:audit_limit]
    ]
    return {
        "filings": len(items),
        "tagged_filings": len(tagged),
        "tagging_rate": len(tagged) / len(items) if items else 0.0,
        "volume_by_day": dict(sorted(volume_by_day.items())),
        "watchlist_tickers": sorted(matched_tickers),
        "watchlist_coverage": len(matched_tickers) / len(watchlist) if watchlist else 0.0,
        "watchlist_filings": len(matched_items),
        "tagging_audit": audit_rows,
    }


async def _fetch(max_results: int) -> list[NewsItem]:
    connector = SECEdgarConnector(
        form_types=["8-K", "6-K"],
        max_results=max_results,
        user_agent=config.SEC_USER_AGENT,
    )
    return [item async for item in connector.fetch()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-results",
        type=int,
        default=100,
        help="maximum combined 8-K/6-K filings in the shadow sample (default: 100)",
    )
    parser.add_argument(
        "--audit-limit",
        type=int,
        default=20,
        help="maximum watchlist mappings printed for manual precision review (default: 20)",
    )
    args = parser.parse_args(argv)
    if args.max_results < 1 or args.audit_limit < 1:
        parser.error("--max-results and --audit-limit must be positive")

    items = asyncio.run(_fetch(args.max_results))
    report = summarize_shadow(
        items,
        set(config.WATCHLIST_SYMBOLS or []),
        audit_limit=args.audit_limit,
    )
    report["sampled_at"] = datetime.now(timezone.utc).isoformat()
    report["sample_limit"] = args.max_results
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if items else 1


if __name__ == "__main__":
    raise SystemExit(main())
