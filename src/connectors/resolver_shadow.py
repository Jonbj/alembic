"""Resolver SHADOW mode (Fase A) — compute and persist the deterministic ticker
resolution for live news WITHOUT gating signals.

Lets us measure resolver precision against news_labels before any enforcement (QX-01).
Fail-open everywhere: a provider outage or any error skips the row, never affects the
live sentiment signal. Never called from a trading loop.
"""
from __future__ import annotations

import logging

from src.connectors.ticker_resolver import resolve
from src.connectors.ticker_resolver_providers import (
    OpenFigiClient,
    SecCompanyTickers,
    gather_evidence,
)

log = logging.getLogger(__name__)

# Tickers whose extraction path is trustworthy enough to count as a source match.
_RELIABLE_METHODS = {"source_metadata", "cashtag"}

_openfigi: OpenFigiClient | None = None
_sec: SecCompanyTickers | None = None
_watchlist: set[str] | None = None


def _tradable_symbols() -> set[str] | None:
    """Lazily load the tradable watchlist. None on failure (fail-open → tradable)."""
    global _watchlist
    if _watchlist is None:
        try:
            import os

            import yaml
            path = os.path.join(os.path.dirname(__file__), "..", "..", "config", "trading.yaml")
            with open(path) as f:
                _watchlist = set(yaml.safe_load(f).get("symbols", {}).get("watchlist", []))
        except Exception:
            _watchlist = set()
    return _watchlist or None


def _providers() -> tuple[OpenFigiClient | None, SecCompanyTickers | None]:
    """Lazily build and reuse the (internally cached) providers. Fail-open to None."""
    global _openfigi, _sec
    try:
        from src.config import config
        if _openfigi is None:
            _openfigi = OpenFigiClient(api_key=getattr(config, "OPENFIGI_API_KEY", "") or "")
        if _sec is None:
            _sec = SecCompanyTickers(user_agent=getattr(config, "SEC_USER_AGENT", ""))
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("resolver shadow providers init failed: %s", exc)
    return _openfigi, _sec


def resolve_and_log_shadow(items, pg_store, *, tradable_symbols=None, alias_tickers=None) -> int:
    """Resolve each item's primary ticker in shadow and write to news_resolved_entities.

    Returns the number of verdicts written. Never raises.
    """
    openfigi, sec = _providers()
    if tradable_symbols is None:
        tradable_symbols = _tradable_symbols()
    written = 0
    for item in items:
        try:
            tickers = getattr(item, "asset_tags", None) or []
            if not tickers:
                continue
            ticker = str(tickers[0])
            method = getattr(item, "extraction_method", "") or ""
            evidence = gather_evidence(
                ticker,
                from_reliable_source=method in _RELIABLE_METHODS,
                alias_tickers=alias_tickers,
                tradable_symbols=tradable_symbols,
                openfigi=openfigi,
                sec=sec,
            )
            verdict = resolve([evidence])
            pg_store.write_resolved_entity(
                candidate_ticker=ticker,
                extraction_method=method,
                verdict=verdict,
                evidence=evidence,
                url=getattr(item, "url", None),
            )
            written += 1
        except Exception as exc:
            log.warning("resolver shadow failed for %s: %s", getattr(item, "url", "?"), exc)
    return written
