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
# Fermare lo script a questo conteggio e' compito nostro (edge case 8): il rate
# limit del provider potrebbe degradare in modi non documentati.
_DAILY_REQUEST_BUDGET = 700

# 8 crediti/min nel piano Basic: dopo un 429 attendiamo il minuto e riproviamo
# i simboli rinviati. Oltre _MAX_RATE_LIMIT_RETRIES giri rinunciamo: la PoC
# misura, non deve mai inseguire il provider all'infinito.
_RATE_LIMIT_BACKOFF_S = 60.0
_MAX_RATE_LIMIT_RETRIES = 2

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


def _requests_today(cur) -> int:
    """Crediti gia' consumati oggi da questa fonte (cumulativo sulle run)."""
    cur.execute(
        """
        SELECT requests FROM news_poc_request_budget
        WHERE poc_source = %s AND day = CURRENT_DATE
        """,
        (_POC_SOURCE,),
    )
    row = cur.fetchone()
    return row[0] if row else 0


def _record_request(cur) -> None:
    """Conta la richiesta che stiamo per fare nel ledger giornaliero."""
    cur.execute(
        """
        INSERT INTO news_poc_request_budget (poc_source, day, requests)
        VALUES (%s, CURRENT_DATE, 1)
        ON CONFLICT (poc_source, day)
        DO UPDATE SET requests = news_poc_request_budget.requests + 1,
                      updated_at = now()
        """,
        (_POC_SOURCE,),
    )


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


def _put_row(conn, symbol: str, item, raw: dict, stats: dict) -> None:
    try:
        with conn.cursor() as cur:
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
            conn.commit()
            stats["written"] += 1
    except Exception as exc:  # pragma: no cover - difensivo
        logger.warning("INSERT failed for %s/%s: %s", symbol, item.id, exc)
        conn.rollback()
        stats["errors"] += 1


async def _run(symbols: list[str]) -> dict:
    api_key = os.environ.get("TWELVE_DATA_API_KEY", "")
    if not api_key:
        raise SystemExit("TWELVE_DATA_API_KEY non valorizzata nell'ambiente")

    conn = _conn()
    conn.autocommit = False
    stats = {
        "requested": 0, "fetched": 0, "written": 0,
        "duplicates": 0, "rate_limited": 0, "errors": 0,
    }

    try:
        with conn.cursor() as cur:
            already_seen = _existing_external_ids(cur, symbols)

        connector = TwelveDataPressReleasesConnector(api_key=api_key, symbols=symbols)

        # I simboli sono guidati uno per volta: il budget va fermato tra una
        # richiesta e l'altra e un 429 su un simbolo non deve bloccare gli
        # altri (edge case 1). I rate-limited vengono rinviati a fine giro,
        # dopo un backoff dell'intera finestra di crediti.
        pending = list(symbols)
        deferred: list[str] = []
        retries = 0
        while True:
            if not pending:
                if not deferred:
                    break
                if retries >= _MAX_RATE_LIMIT_RETRIES:
                    logger.warning(
                        "Rinunciato dopo %d giri di backoff su %d simboli: %s",
                        retries, len(deferred), deferred,
                    )
                    break
                retries += 1
                pending, deferred = deferred, []
                logger.info("Backoff %ss prima di riprovare", _RATE_LIMIT_BACKOFF_S)
                await asyncio.sleep(_RATE_LIMIT_BACKOFF_S)

            symbol = pending.pop(0)

            with conn.cursor() as cur:
                consumed = _requests_today(cur)
                if consumed >= _DAILY_REQUEST_BUDGET:
                    logger.warning(
                        "Budget giornaliero %d/%d raggiunto — stop, %d simboli saltati: %s",
                        consumed, _DAILY_REQUEST_BUDGET, len(pending) + 1, [symbol] + pending,
                    )
                    break
                _record_request(cur)
                conn.commit()
            stats["requested"] += 1

            try:
                # drain prima di scrivere: last_response e' completo solo a fine
                # simbolo, e il raw va associato item-per-item
                items = [item async for item in connector.fetch_symbol(symbol)]
            except TwelveDataRateLimitError as exc:
                stats["rate_limited"] += 1
                logger.info("Rate limit su %s — rinviato a fine giro: %s", symbol, exc)
                deferred.append(symbol)
                continue
            except TwelveDataAuthError as exc:
                # fatale: ogni simbolo fallirebbe allo stesso modo
                logger.error("Auth error — abort: %s", exc)
                stats["errors"] += 1
                break
            except TwelveDataInvalidSymbolError as exc:
                logger.warning("Invalid symbol: %s", exc)
                stats["errors"] += 1
                continue

            raw_by_id = {
                r.get("id"): r
                for r in (connector.last_response or {}).get("press_releases") or []
                if isinstance(r, dict)
            }
            for item in items:
                stats["fetched"] += 1
                ext_id = item.id.split(":", 1)[-1]
                if ext_id in already_seen:
                    stats["duplicates"] += 1
                    continue
                already_seen.add(ext_id)
                _put_row(conn, symbol, item, raw_by_id.get(ext_id, {}), stats)

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