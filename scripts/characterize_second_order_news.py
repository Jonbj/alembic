#!/usr/bin/env python3
"""Caratterizza le headline second-order/spillover senza toccare il runtime (#408).

Legge ``news_log`` e i forward return gia' calcolati in
``sentiment_signals``, applica un detector deterministico indipendente dal
modello e usa ``llm_responses.directness`` soltanto per una cross-tab di
controllo. Nessuna soglia, prompt o tabella live viene modificata.

Uso nel container worker:
    docker compose exec worker python scripts/characterize_second_order_news.py
    docker compose exec worker python scripts/characterize_second_order_news.py \
        --since 2026-08-24 --until 2026-09-03
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

from src.analysis.second_order_news import (
    CAUSAL_CONNECTORS,
    CompanyIdentity,
    SecondOrderDetector,
)

PROJECT_DIR = Path(__file__).resolve().parents[1]
OUT = PROJECT_DIR / "docs" / "evidence" / "second_order_news.json"
SCHEMA_VERSION = "1.0"
FORWARD_COLUMNS = ("forward_return", "forward_return_3d", "forward_return_5d")
SPILLOVER_DIRECTNESS = ("competitor_readthrough", "sector")


def _connect():
    import psycopg2

    url = os.environ.get(
        "DATABASE_URL", "postgresql://trading:trading@postgres:5432/trading"
    )
    return psycopg2.connect(url)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _date_arg(raw: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("usa una data ISO YYYY-MM-DD") from exc


def load_inputs(conn, since: date | None, until: date | None):
    """Carica i quattro input grezzi, senza classificare ne' aggregare."""
    from psycopg2.extras import RealDictCursor

    bounds = (since, since, until, until)
    date_filter = """
        (%s::date IS NULL OR nl.fetched_at >= %s::date)
        AND (%s::date IS NULL OR nl.fetched_at < %s::date + interval '1 day')
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT ticker, company_name, aliases FROM ticker_lookup ORDER BY ticker, company_name"
        )
        companies = [
            CompanyIdentity(
                ticker=row["ticker"],
                company_name=row["company_name"],
                aliases=tuple(row.get("aliases") or ()),
            )
            for row in cur.fetchall()
        ]

        cur.execute(
            f"""SELECT nl.id AS news_log_id, nl.ticker, nl.title,
                       nl.body_snippet, nl.fetched_at
                FROM news_log nl
                WHERE {date_filter}
                ORDER BY nl.id""",
            bounds,
        )
        news = list(cur.fetchall())

        cur.execute(
            f"""SELECT ss.id AS signal_id, ss.news_log_id,
                       ss.forward_return, ss.forward_return_3d, ss.forward_return_5d
                FROM sentiment_signals ss
                JOIN news_log nl ON nl.id = ss.news_log_id
                WHERE {date_filter}
                ORDER BY ss.id""",
            bounds,
        )
        signals = list(cur.fetchall())

        cur.execute(
            f"""SELECT lr.signal_id, lr.model_id, lr.directness
                FROM llm_responses lr
                JOIN sentiment_signals ss ON ss.id = lr.signal_id
                JOIN news_log nl ON nl.id = ss.news_log_id
                WHERE {date_filter}
                ORDER BY lr.signal_id, lr.model_id""",
            bounds,
        )
        responses = list(cur.fetchall())
    return news, companies, signals, responses


def _iso(value: object) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _distribution(rows: Iterable[dict]) -> dict[str, dict]:
    rows = list(rows)
    out: dict[str, dict] = {}
    for column in FORWARD_COLUMNS:
        values = [float(row[column]) for row in rows if row.get(column) is not None]
        out[column] = {
            "n": len(values),
            "mean": statistics.fmean(values) if values else None,
            "median": statistics.median(values) if values else None,
        }
    return out


def _pct(value: float | None) -> str:
    return "non misurabile" if value is None else f"{value:.2%}"


def build_report(
    news: list[dict],
    companies: list[CompanyIdentity],
    signals: list[dict],
    responses: list[dict],
    *,
    generated_at: datetime,
) -> dict:
    """Costruisce il report descrittivo; funzione pura per fixture e replay."""
    detector = SecondOrderDetector(companies)
    known_news_ids: set[object] = set()
    second_order_ids: set[object] = set()
    classifications: list[dict] = []

    for row in news:
        ticker = str(row.get("ticker") or "").strip().upper()
        news_log_id = row.get("news_log_id")
        if ticker not in detector.known_tickers:
            continue
        known_news_ids.add(news_log_id)
        match = None
        text_source = None
        # I quattro seed reali di #408 hanno un titolo generico; il connettore
        # causale e' nel body_snippet persistito. I campi restano separati per
        # non creare un match attraversando artificialmente il loro confine.
        for candidate_source in ("title", "body_snippet"):
            match = detector.classify(ticker, str(row.get(candidate_source) or ""))
            if match is not None:
                text_source = candidate_source
                break
        if match is None:
            continue
        second_order_ids.add(news_log_id)
        classifications.append({
            "news_log_id": news_log_id,
            "ticker": ticker,
            "title": row.get("title") or "",
            "fetched_at": _iso(row.get("fetched_at")),
            "category": match.category,
            "text_source": text_source,
            "connector": match.connector,
            "third_party_ticker": match.third_party_ticker,
            "third_party_company": match.third_party_company,
        })

    classifications.sort(key=lambda row: (int(row["news_log_id"]), row["ticker"]))
    signal_category: dict[object, bool] = {}
    second_order_signals: list[dict] = []
    other_signals: list[dict] = []
    for row in signals:
        news_log_id = row.get("news_log_id")
        if news_log_id not in known_news_ids:
            continue
        is_second_order = news_log_id in second_order_ids
        signal_category[row.get("signal_id")] = is_second_order
        (second_order_signals if is_second_order else other_signals).append(row)

    directness = [
        str(row.get("directness")).strip().casefold()
        for row in responses
        if signal_category.get(row.get("signal_id")) is True and row.get("directness")
    ]
    directness_counts = Counter(directness)
    spillover_count = sum(directness_counts[label] for label in SPILLOVER_DIRECTNESS)

    known_count = len(known_news_ids)
    second_order_count = len(second_order_ids)
    timestamps: list[datetime] = []
    for row in news:
        raw_timestamp = row.get("fetched_at")
        if isinstance(raw_timestamp, datetime):
            timestamps.append(raw_timestamp)
        elif raw_timestamp:
            timestamps.append(datetime.fromisoformat(str(raw_timestamp)))
    start = min(timestamps) if timestamps else None
    end = max(timestamps) if timestamps else None
    second_order_distribution = _distribution(second_order_signals)
    other_distribution = _distribution(other_signals)
    agreement_rate = spillover_count / len(directness) if directness else None
    summary = (
        f"Il detector deterministico ha classificato {second_order_count} su "
        f"{known_count} righe news con ticker noto come secondo ordine "
        f"({second_order_count / known_count:.2%}). Il forward return medio a 1 giorno "
        f"e' {_pct(second_order_distribution['forward_return']['mean'])} sui segnali "
        f"classificati e {_pct(other_distribution['forward_return']['mean'])} sugli altri; "
        f"directness concorda nei bucket competitor_readthrough/sector in "
        f"{spillover_count} su {len(directness)} risposte ({_pct(agreement_rate)}). "
        "Il confronto e' descrittivo, non causale; l'assenza di match significa non "
        "classificato, non notizia diretta."
        if known_count
        else "Nessuna riga news con ticker noto nella finestra; nessun tasso e' stato inventato."
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at.isoformat(),
        "window": {"start": _iso(start), "end": _iso(end)},
        "method": {
            "classification": (
                "self-reference + causal connector + different ticker_lookup company "
                "after the connector; precision-biased lower bound"
            ),
            "independent_from_llm_directness": True,
            "text_fields": ["title", "body_snippet"],
            "causal_connectors": list(CAUSAL_CONNECTORS),
            "forward_return_source": "sentiment_signals (existing columns, read-only)",
        },
        "population": {
            "news_rows_total": len(news),
            "news_rows_with_known_ticker": known_count,
            "second_order": second_order_count,
            "other": known_count - second_order_count,
            "unknown_ticker": len(news) - known_count,
            "second_order_rate": second_order_count / known_count if known_count else None,
        },
        "forward_returns": {
            "unit": "sentiment_signal",
            "second_order": second_order_distribution,
            "other": other_distribution,
        },
        "directness_agreement": {
            "unit": "llm_response",
            "responses_with_directness": len(directness),
            "spillover_labels": list(SPILLOVER_DIRECTNESS),
            "spillover": {
                "n": spillover_count,
                "rate": agreement_rate,
            },
            "by_bucket": dict(sorted(directness_counts.items())),
        },
        "classifications": classifications,
        "sintesi": summary,
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", type=_date_arg, help="inizio incluso (YYYY-MM-DD)")
    parser.add_argument("--until", type=_date_arg, help="fine inclusa (YYYY-MM-DD)")
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--no-write", action="store_true", help="stampa soltanto il JSON")
    args = parser.parse_args(argv)
    if args.since and args.until and args.since > args.until:
        parser.error("--since non puo' essere successivo a --until")

    conn = _connect()
    try:
        inputs = load_inputs(conn, args.since, args.until)
    finally:
        close = getattr(conn, "close", None)
        if close is not None:
            close()
    report = build_report(*inputs, generated_at=_utc_now())
    if args.no_write:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _write_json(args.output, report)
        print(f"Scritto {args.output}: {report['sintesi']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
