"""Cashtag ($AAPL) ticker extraction — shared entity fallback for news connectors.

Quality review A1 / QT-01: when a source provides NO entity/symbol metadata, the
connectors must NOT tag the article with the entire watchlist — that enqueues one
signal per uncorrelated ticker (mass false positives that pollute IC and attribution).
The fallback is instead explicit ``$cashtags`` in the text; if none are found the
article carries no ticker and is dropped downstream (``if not item.asset_tags``).
"""
import re

_CASHTAG_RE = re.compile(r"\$([A-Z]{1,5})\b")


def extract_cashtag_tickers(text: str, universe) -> list[str]:
    """Return ``universe`` tickers that appear with an explicit ``$cashtag`` in text.

    Order follows ``universe`` iteration. Empty/None text → empty list.
    """
    if not text:
        return []
    tags = {m.group(1) for m in _CASHTAG_RE.finditer(text)}
    return [t for t in universe if t in tags]
