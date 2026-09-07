#!/usr/bin/env python3
"""PoC shadow Twelve Data press_releases (#458).

Standalone: fuori dal Celery beat di produzione (vedi vincolo nel corpo
dell'issue). Per simbolo: chiama il connettore, fa dedup su `external_id`
contro le righe gia' presenti in `news_poc_samples` per `poc_source`, valida
`ticker_valid`, scrive in `news_poc_samples`. MAI in `news_log`,
`news:queue` o qualunque store letto dal path live.

Esecuzione:
    docker compose exec worker python scripts/poc_twelve_data_shadow.py
    # oppure con simboli custom:
    python scripts/poc_twelve_data_shadow.py --symbols AAPL,MSFT,NFLX
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import logging
import os
import sys
from typing import Iterable

import psycopg2
import psycopg2.extras

# aggiunge la root del repo al path quando si esegue come script standalone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.connectors.twelve_data_press_releases import (  # noqa: E402
    TwelveDataAuthError,
    TwelveDataInvalidSymbolError,
    TwelveDataPressReleasesConnector,
    TwelveDataRateLimitError,
)

logger = logging.getLogger("poc_twelve_data_shadow")

# Coorte PoC: 12 simboli US large/mid cap, bilanciamento settoriale grossolano.
_DEFAULT_SYMBOLS = [
    "AAPL", "MSFT", "AMZN", "GOOGL", "META", "NFLX",
    "JPM", "BAC", "GS", "MS", "XOM", "CVX",
]

# Cap giornaliero sotto gli 800 crediti del piano Basic (margine di sicurezza).
_DAILY_REQUEST_BUDGET = 700

_POC_SOURCE = "twelvedata_press_releases"


def _conn():
    url = os.environ.get(
        "DATABASE_URL", "postgresql://trading:trading@postgres:5432/trading"
    )
    return psycopg2.connect(url)


def _existing_external_ids(cur, symbols: Iterable[str]) -> set[str]:
    cur.execute(
        """
        SELECT external_id FROM news_poc_samples
        WHERE poc_source = %s AND symbol = ANY(%s) AND external_id IS NOT NULL
        """,
        (_POC_SOURCE, list(symbols)),
    )
    return {row[0] for row in cur.fetchall()}


def _ticker_valid(title: str, body: str, symbol: str) -> bool:
    """Il simbolo richiesto compare in title o body (case-insensitive, ASCII).

    Twelve Data non restituisce un campo `symbols`: la corrispondenza va fatta
    sul testo. Niente NLP pesante: match esatto su parola intera.
    """
    import re

    sym = re.escape(symbol)
    pattern = re.compile(rf"(?<![A-Za-z0-9]){sym}(?![A-Za-z0-9])", re.IGNORECASE)
    text = f"{title or ''}\n{body or ''}"
    return bool(pattern.search(text))


async def _run(symbols: list[str]) -> dict:
    api_key = os.environ.get("TWELVE_DATA_API_KEY", "")
    if not api_key:
        raise SystemExit("TWELVE_DATA_API_KEY non valorizzata nell'ambiente")

    conn = _conn()
    conn.autocommit = False
    stats = {"requested": 0, "fetched": 0, "written": 0, "duplicates": 0, "errors": 0}

    try:
        with conn.cursor() as cur:
            already_seen = _existing_external_ids(cur, symbols)

        conn_holder = {"c": conn}

        def _put_row(symbol: str, item, raw: dict) -> None:
            try:
                with conn_holder["c"].cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO news_poc_samples (
                            poc_source, symbol, external_id, title, body_chars,
                            url, published_at, latency_seconds, ticker_valid, raw_response
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (poc_source, external_id) WHERE external_id IS NOT NULL
                        DO NOTHING
                        """,
                        (
                            _POC_SOURCE,
                            symbol,
                            item.id.split(":", 1)[-1],  # td:<id> -> <id>
                            item.title,
                            len(item.body),
                            item.url,
                            item.timestamp,
                            (dt.datetime.now(dt.timezone.utc) - item.timestamp).total_seconds(),
                            _ticker_valid(item.title, item.body, symbol),
                            json.dumps(raw),
                        ),
                    )
                    conn_holder["c"].commit()
            except Exception as exc:  # pragma: no cover - difensivo
                logger.warning("INSERT failed for %s/%s: %s", symbol, item.id, exc)
                conn_holder["c"].rollback()
                stats["errors"] += 1

        connector = TwelveDataPressReleasesConnector(api_key=api_key, symbols=symbols)

        try:
            async for item in connector.fetch():
                stats["fetched"] += 1
                ext_id = item.id.split(":", 1)[-1]
                if ext_id in already_seen:
                    stats["duplicates"] += 1
                    continue
                already_seen.add(ext_id)
                # l'ext_id grezzo non e' sopravvissuto qui: lo recuperiamo dal raw
                # tenuto per la scrittura. Per semplicita' riusiamo item.id.
                _put_row(item.asset_tags[0] if item.asset_tags else symbols[0], item, {})
                stats["written"] += 1
        except TwelveDataRateLimitError as exc:
            logger.warning("Rate limit dopo %d richieste: %s", stats["requested"], exc)
            stats["errors"] += 1
        except TwelveDataAuthError as exc:
            logger.error("Auth error: %s", exc)
            stats["errors"] += 1
        except TwelveDataInvalidSymbolError as exc:
            logger.warning("Invalid symbol: %s", exc)
            stats["errors"] += 1

    finally:
        conn.close()

    return stats


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="PoC shadow Twelve Data press_releases")
    p.add_argument("--symbols", default=",".join(_DEFAULT_SYMBOLS),
                   help="Lista di simboli separati da virgola (default: coorte PoC)")
    p.add_argument("--log-level", default="INFO")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    stats = asyncio.run(_run(symbols))
    logger.info("PoC Twelve Data done: %s", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())