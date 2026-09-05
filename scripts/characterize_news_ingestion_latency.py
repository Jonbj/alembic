#!/usr/bin/env python3
"""Characterise publication-to-ingestion latency from the two news ledgers.

Read-only measurement for #433.  ``news_log`` contains scored items while
``news_queue_drops`` contains items discarded before scoring.  The source
distribution collapses both ledgers to the first observation of each article,
so ticker fan-out and overlapping polls cannot inflate the percentiles.  The
stale-drop table deliberately keeps queue-item granularity to reproduce #149's
capacity-loss denominator.

Run in the deployed worker container::

    docker compose exec worker python scripts/characterize_news_ingestion_latency.py \
      --since 2026-08-03T00:00:00+00:00 --until 2026-09-04T00:00:00+00:00
"""

from __future__ import annotations

import argparse
import os
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime
from itertools import pairwise
from math import floor

DEFAULT_SINCE = datetime(2026, 8, 3, tzinfo=UTC)
DEFAULT_FOCUS_DATE = date(2026, 8, 28)


FETCH_OBSERVATIONS_SQL = """
SELECT source,
       COALESCE(NULLIF(url, ''), NULLIF(content_hash, ''),
                'news_log:' || id::text) AS article_key,
       published_at,
       raw_ingested_at,
       'news_log' AS ledger,
       NULL::text AS discarded_reason
FROM news_log
WHERE raw_ingested_at >= %s
  AND raw_ingested_at < %s
UNION ALL
SELECT source,
       COALESCE(NULLIF(url, ''), NULLIF(article_id, ''),
                NULLIF(content_hash, ''), 'drop:' || id::text) AS article_key,
       published_at,
       raw_ingested_at,
       'news_queue_drops' AS ledger,
       discarded_reason
FROM news_queue_drops
WHERE raw_ingested_at >= %s
  AND raw_ingested_at < %s
ORDER BY raw_ingested_at
"""


FETCH_STALE_DROPS_SQL = """
SELECT source, dropped_at, published_at, raw_ingested_at,
       COALESCE(NULLIF(url, ''), NULLIF(article_id, ''),
                NULLIF(content_hash, ''), 'drop:' || id::text) AS article_key
FROM news_queue_drops
WHERE discarded_reason = 'stale'
  AND dropped_at >= %s
  AND dropped_at < %s
ORDER BY dropped_at
"""


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _hours(later: datetime, earlier: datetime) -> float:
    return (_utc(later) - _utc(earlier)).total_seconds() / 3600.0


def _percentile(values: Iterable[float], quantile: float) -> float:
    """PostgreSQL-compatible continuous percentile (linear interpolation)."""
    ordered = sorted(values)
    if not ordered:
        raise ValueError("percentile of an empty sample")
    position = (len(ordered) - 1) * quantile
    lower = floor(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _distribution(source: str, values: list[float]) -> dict:
    born_stale = sum(value > 2.0 for value in values)
    return {
        "source": source,
        "articles": len(values),
        "p50_hours": _percentile(values, 0.50),
        "p75_hours": _percentile(values, 0.75),
        "p95_hours": _percentile(values, 0.95),
        "born_stale": born_stale,
        "born_stale_pct": 100.0 * born_stale / len(values),
        "negative_latency": sum(value < 0 for value in values),
    }


def _first_seen(rows: Iterable[dict]) -> list[dict]:
    articles: dict[tuple[str, str], dict] = {}
    for row in rows:
        published = row.get("published_at")
        ingested = row.get("raw_ingested_at")
        if published is None or ingested is None:
            continue
        key = (str(row.get("source") or ""), str(row.get("article_key") or ""))
        current = articles.get(key)
        if current is None or _utc(ingested) < _utc(current["raw_ingested_at"]):
            articles[key] = row
    return list(articles.values())


def summarize_first_seen(
    rows: Iterable[dict], *, stale_hours: float = 2.0
) -> tuple[list[dict], list[dict]]:
    """Return article-level latency percentiles by source and ingestion hour."""
    by_source: dict[str, list[float]] = defaultdict(list)
    by_hour: dict[tuple[str, int], list[float]] = defaultdict(list)
    for row in _first_seen(rows):
        source = str(row.get("source") or "")
        ingested = _utc(row["raw_ingested_at"])
        latency = _hours(ingested, row["published_at"])
        by_source[source].append(latency)
        by_hour[(source, ingested.hour)].append(latency)

    source_rows = []
    for source, values in sorted(by_source.items()):
        result = _distribution(source, values)
        born_stale = sum(value > stale_hours for value in values)
        result["born_stale"] = born_stale
        result["born_stale_pct"] = 100.0 * born_stale / len(values)
        source_rows.append(result)

    hourly_rows = []
    for (source, hour), values in sorted(by_hour.items()):
        result = _distribution(source, values)
        born_stale = sum(value > stale_hours for value in values)
        result.update(
            {
                "fetch_hour_utc": hour,
                "born_stale": born_stale,
                "born_stale_pct": 100.0 * born_stale / len(values),
            }
        )
        hourly_rows.append(result)
    return source_rows, hourly_rows


def summarize_stale_drops(
    rows: Iterable[dict], *, stale_hours: float = 2.0
) -> list[dict]:
    """Aggregate measurable stale drops without collapsing per-ticker queue items."""
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        if row.get("published_at") is None or row.get("raw_ingested_at") is None:
            continue
        dropped = _utc(row["dropped_at"])
        grouped[(dropped.date().isoformat(), str(row.get("source") or ""))].append(row)

    output = []
    for (session, source), group in sorted(grouped.items()):
        fetch_latencies = [
            _hours(row["raw_ingested_at"], row["published_at"]) for row in group
        ]
        queue_waits = [
            _hours(row["dropped_at"], row["raw_ingested_at"]) for row in group
        ]
        born_stale = sum(value > stale_hours for value in fetch_latencies)
        output.append(
            {
                "session": session,
                "source": source,
                "stale_drops": len(group),
                "fetch_latency_hours": sum(fetch_latencies) / len(group),
                "queue_wait_hours": sum(queue_waits) / len(group),
                "born_stale": born_stale,
                "born_stale_pct": 100.0 * born_stale / len(group),
            }
        )
    return output


def summarize_stale_fetch_cycles(
    rows: Iterable[dict], *, focus_date: date, stale_hours: float = 2.0
) -> list[dict]:
    """Split one session's stale queue items by their original ingestion cycle."""
    grouped: dict[tuple[datetime, str], list[dict]] = defaultdict(list)
    for row in rows:
        published = row.get("published_at")
        ingested = row.get("raw_ingested_at")
        if published is None or ingested is None:
            continue
        cycle_at = _cycle_minute(ingested)
        if _utc(row["dropped_at"]).date() != focus_date:
            continue
        grouped[(cycle_at, str(row.get("source") or ""))].append(row)

    output = []
    for (cycle_at, source), group in sorted(grouped.items()):
        output.append(
            {
                "cycle_at": cycle_at,
                "source": source,
                "queue_items": len(group),
                "articles": len(
                    {row.get("article_key") for row in group if row.get("article_key")}
                ),
                "born_stale": sum(
                    _hours(row["raw_ingested_at"], row["published_at"]) > stale_hours
                    for row in group
                ),
            }
        )
    return output


def _cycle_minute(value: datetime) -> datetime:
    return _utc(value).replace(second=0, microsecond=0)


def summarize_alpaca_polls(
    rows: Iterable[dict], *, stale_hours: float = 2.0
) -> tuple[dict, list[dict]]:
    """Characterise visible Alpaca poll cadence and publication-window overlap."""
    cycle_articles: dict[tuple[datetime, str], dict] = {}
    first_cycle: dict[str, datetime] = {}
    for row in rows:
        if row.get("source") != "alpaca_benzinga":
            continue
        if row.get("published_at") is None or row.get("raw_ingested_at") is None:
            continue
        cycle_at = _cycle_minute(row["raw_ingested_at"])
        article_key = str(row.get("article_key") or "")
        key = (cycle_at, article_key)
        current = cycle_articles.get(key)
        if current is None or _utc(row["published_at"]) < _utc(current["published_at"]):
            cycle_articles[key] = row
        if article_key not in first_cycle or cycle_at < first_cycle[article_key]:
            first_cycle[article_key] = cycle_at

    grouped: dict[datetime, list[tuple[str, dict]]] = defaultdict(list)
    for (cycle_at, article_key), row in cycle_articles.items():
        grouped[cycle_at].append((article_key, row))

    cycles: list[dict] = []
    page_percentile: dict[tuple[datetime, str], float] = {}
    for cycle_at, articles in sorted(grouped.items()):
        articles.sort(key=lambda pair: _utc(pair[1]["published_at"]), reverse=True)
        divisor = max(len(articles) - 1, 1)
        for position, (article_key, _row) in enumerate(articles):
            page_percentile[(cycle_at, article_key)] = position / divisor
        published = [_utc(row["published_at"]) for _, row in articles]
        cycles.append(
            {
                "cycle_at": cycle_at,
                "articles": len(articles),
                "oldest_published_at": min(published),
                "newest_published_at": max(published),
                "window_span_hours": _hours(max(published), min(published)),
                "stale_on_page": sum(
                    _hours(cycle_at, timestamp) > stale_hours for timestamp in published
                ),
                "high_latency_first_seen": 0,
                "high_latency_after_previous_session": 0,
                "high_latency_late_visibility_candidate": 0,
                "high_latency_without_previous_session": 0,
            }
        )

    intervals = []
    overlaps = 0
    gaps = 0
    for previous, current in pairwise(cycles):
        if previous["cycle_at"].date() != current["cycle_at"].date():
            continue
        intervals.append(_hours(current["cycle_at"], previous["cycle_at"]) * 60.0)
        if current["oldest_published_at"] <= previous["newest_published_at"]:
            overlaps += 1
        else:
            gaps += 1

    high_latency_edges = []
    high_latency_at_14 = 0
    session_bounds: dict[date, tuple[datetime, datetime]] = {}
    for cycle in cycles:
        session = cycle["cycle_at"].date()
        if session not in session_bounds:
            session_bounds[session] = (cycle["cycle_at"], cycle["cycle_at"])
        else:
            session_bounds[session] = (session_bounds[session][0], cycle["cycle_at"])
    previous_session_last: dict[date, datetime] = {}
    last_cycle = None
    for session in sorted(session_bounds):
        if last_cycle is not None:
            previous_session_last[session] = last_cycle
        last_cycle = session_bounds[session][1]

    after_previous_session = 0
    late_visibility_candidate = 0
    without_previous_session = 0
    cycle_by_at: dict[datetime, dict] = {
        cycle["cycle_at"]: cycle for cycle in cycles
    }
    for (cycle_at, article_key), row in cycle_articles.items():
        if cycle_at != first_cycle[article_key]:
            continue
        if _hours(cycle_at, row["published_at"]) <= stale_hours:
            continue
        high_latency_edges.append(page_percentile[(cycle_at, article_key)])
        cycle_by_at[cycle_at]["high_latency_first_seen"] += 1
        if cycle_at.hour == 14:
            high_latency_at_14 += 1
        previous_last = previous_session_last.get(cycle_at.date())
        if previous_last is None:
            without_previous_session += 1
            cycle_by_at[cycle_at]["high_latency_without_previous_session"] += 1
        elif (
            cycle_at == session_bounds[cycle_at.date()][0]
            and _utc(row["published_at"]) > previous_last
        ):
            after_previous_session += 1
            cycle_by_at[cycle_at]["high_latency_after_previous_session"] += 1
        else:
            late_visibility_candidate += 1
            cycle_by_at[cycle_at]["high_latency_late_visibility_candidate"] += 1

    high_count = len(high_latency_edges)
    summary = {
        "cycles": len(cycles),
        "first_cycle_at": cycles[0]["cycle_at"] if cycles else None,
        "last_cycle_at": cycles[-1]["cycle_at"] if cycles else None,
        "p50_intraday_interval_minutes": _percentile(intervals, 0.50) if intervals else None,
        "p95_intraday_interval_minutes": _percentile(intervals, 0.95) if intervals else None,
        "max_intraday_interval_minutes": max(intervals) if intervals else None,
        "intraday_gaps_over_20_minutes": sum(value > 20.0 for value in intervals),
        "publication_window_overlaps": overlaps,
        "publication_window_gaps": gaps,
        "max_articles_per_cycle": max((row["articles"] for row in cycles), default=0),
        "high_latency_first_seen": high_count,
        "high_latency_first_seen_at_14_utc": high_latency_at_14,
        "high_latency_at_14_pct": (
            100.0 * high_latency_at_14 / high_count if high_count else 0.0
        ),
        "high_latency_median_page_percentile": (
            _percentile(high_latency_edges, 0.50) if high_latency_edges else None
        ),
        "high_latency_in_oldest_quartile": sum(
            percentile >= 0.75 for percentile in high_latency_edges
        ),
        "high_latency_after_previous_session": after_previous_session,
        "high_latency_late_visibility_candidate": late_visibility_candidate,
        "high_latency_without_previous_session": without_previous_session,
        "schedule_gap_share_of_classifiable_pct": (
            100.0 * after_previous_session
            / (after_previous_session + late_visibility_candidate)
            if after_previous_session + late_visibility_candidate
            else 0.0
        ),
    }
    return summary, cycles


def _format(value: float | None, decimals: int = 2) -> str:
    return "n/a" if value is None else f"{value:.{decimals}f}"


def _markdown_table(headers: list[str], rows: Iterable[list[object]]) -> list[str]:
    output = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    output.extend("| " + " | ".join(str(value) for value in row) + " |" for row in rows)
    return output


def render_report(
    *,
    since: datetime,
    until: datetime,
    focus_date: date,
    source_rows: list[dict],
    hourly_rows: list[dict],
    stale_rows: list[dict],
    focus_stale_cycles: list[dict],
    stale_total: int,
    stale_measurable: int,
    poll_summary: dict,
    poll_cycles: list[dict],
) -> str:
    lines = [
        "# Latenza pubblicazione → ingestion (#433)",
        "",
        f"Finestra UTC semiaperta: `{since.isoformat()}` → `{until.isoformat()}`.",
        "I percentili sono per articolo al primo avvistamento; i drop stale restano per queue item.",
        "",
        "## Distribuzione per fonte",
        "",
    ]
    lines += _markdown_table(
        ["fonte", "articoli", "p50 h", "p75 h", "p95 h", ">2h", "% >2h", "negative"],
        (
            [
                row["source"], row["articles"], _format(row["p50_hours"]),
                _format(row["p75_hours"]), _format(row["p95_hours"]), row["born_stale"],
                _format(row["born_stale_pct"], 1), row["negative_latency"],
            ]
            for row in source_rows
        ),
    )
    lines += ["", "## Distribuzione per ora del primo avvistamento", ""]
    lines += _markdown_table(
        ["fonte", "ora UTC", "articoli", "p50 h", "p75 h", "p95 h", ">2h", "% >2h"],
        (
            [
                row["source"], row["fetch_hour_utc"], row["articles"],
                _format(row["p50_hours"]), _format(row["p75_hours"]),
                _format(row["p95_hours"]), row["born_stale"],
                _format(row["born_stale_pct"], 1),
            ]
            for row in hourly_rows
        ),
    )
    lines += [
        "",
        "## Drop stale misurabili",
        "",
        f"Copertura `raw_ingested_at`: {stale_measurable}/{stale_total} queue item stale.",
        "",
    ]
    lines += _markdown_table(
        ["sessione", "fonte", "drop", "fetch h media", "queue h media", "nati stale", "%"],
        (
            [
                row["session"], row["source"], row["stale_drops"],
                _format(row["fetch_latency_hours"]), _format(row["queue_wait_hours"]),
                row["born_stale"], _format(row["born_stale_pct"], 1),
            ]
            for row in stale_rows
        ),
    )
    lines += ["", f"### Drop stale per ciclo di ingestion del {focus_date.isoformat()}", ""]
    lines += _markdown_table(
        ["ciclo UTC", "fonte", "queue item", "articoli", "nati stale"],
        (
            [
                row["cycle_at"].isoformat(), row["source"], row["queue_items"],
                row["articles"], row["born_stale"],
            ]
            for row in focus_stale_cycles
        ),
    )
    lines += ["", "## Poll Alpaca/Benzinga osservabili", ""]
    lines += [
        (
            f"- cicli visibili: {poll_summary['cycles']} "
            f"(`{poll_summary['first_cycle_at']}` → `{poll_summary['last_cycle_at']}`)"
        ),
        (
            f"- intervallo intraday p50/p95/max: "
            f"{_format(poll_summary['p50_intraday_interval_minutes'])}/"
            f"{_format(poll_summary['p95_intraday_interval_minutes'])}/"
            f"{_format(poll_summary['max_intraday_interval_minutes'])} minuti; "
            f"gap >20 min: {poll_summary['intraday_gaps_over_20_minutes']}"
        ),
        (
            f"- finestre di pubblicazione consecutive: "
            f"{poll_summary['publication_window_overlaps']} overlap, "
            f"{poll_summary['publication_window_gaps']} gap; "
            f"massimo {poll_summary['max_articles_per_cycle']} articoli distinti/ciclo"
        ),
        (
            f"- articoli >2h al primo avvistamento: "
            f"{poll_summary['high_latency_first_seen']}; alle 14 UTC: "
            f"{poll_summary['high_latency_first_seen_at_14_utc']} "
            f"({_format(poll_summary['high_latency_at_14_pct'], 1)}%)"
        ),
        (
            f"- percentile mediano nella pagina per i >2h: "
            f"{_format(poll_summary['high_latency_median_page_percentile'], 3)} "
            f"(1 = bordo più vecchio); nel quartile più vecchio: "
            f"{poll_summary['high_latency_in_oldest_quartile']}"
        ),
        (
            f"- attribuzione contro l'ultimo poll della sessione precedente: "
            f"{poll_summary['high_latency_after_previous_session']} pubblicati dopo "
            f"(gap off-hours), "
            f"{poll_summary['high_latency_late_visibility_candidate']} candidati a "
            f"visibilità tardiva/backfill, "
            f"{poll_summary['high_latency_without_previous_session']} non classificabili; "
            f"quota gap off-hours sui classificabili "
            f"{_format(poll_summary['schedule_gap_share_of_classifiable_pct'], 1)}%"
        ),
        "",
        f"### Cicli del {focus_date.isoformat()}",
        "",
    ]
    focus_cycles = [row for row in poll_cycles if row["cycle_at"].date() == focus_date]
    lines += _markdown_table(
        [
            "ciclo UTC", "articoli", "più vecchio", "più recente", "span h",
            ">2h in pagina", ">2h nuovi", "gap off-hours", "visibilità tardiva",
        ],
        (
            [
                row["cycle_at"].isoformat(), row["articles"],
                row["oldest_published_at"].isoformat(), row["newest_published_at"].isoformat(),
                _format(row["window_span_hours"]), row["stale_on_page"],
                row["high_latency_first_seen"],
                row["high_latency_after_previous_session"],
                row["high_latency_late_visibility_candidate"],
            ]
            for row in focus_cycles
        ),
    )
    return "\n".join(lines) + "\n"


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return _utc(parsed)


def _fetch_rows(connection, sql: str, params: tuple[datetime, ...]) -> list[dict]:
    from psycopg2.extras import RealDictCursor

    with connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--since", type=_parse_datetime, default=DEFAULT_SINCE)
    parser.add_argument("--until", type=_parse_datetime, default=datetime.now(UTC))
    parser.add_argument("--focus-date", type=date.fromisoformat, default=DEFAULT_FOCUS_DATE)
    parser.add_argument("--stale-hours", type=float, default=2.0)
    args = parser.parse_args()
    if args.until <= args.since:
        parser.error("--until must be later than --since")

    import psycopg2

    database_url = os.environ.get(
        "DATABASE_URL", "postgresql://trading:trading@postgres:5432/trading"
    )
    with psycopg2.connect(database_url) as connection:
        connection.set_session(readonly=True)
        observations = _fetch_rows(
            connection,
            FETCH_OBSERVATIONS_SQL,
            (args.since, args.until, args.since, args.until),
        )
        stale = _fetch_rows(connection, FETCH_STALE_DROPS_SQL, (args.since, args.until))

    source_rows, hourly_rows = summarize_first_seen(
        observations, stale_hours=args.stale_hours
    )
    stale_rows = summarize_stale_drops(stale, stale_hours=args.stale_hours)
    focus_stale_cycles = summarize_stale_fetch_cycles(
        stale, focus_date=args.focus_date, stale_hours=args.stale_hours
    )

    # Duplicate-id telemetry records every non-empty Alpaca page only since the
    # discard ledger extension was deployed.  Starting earlier would mistake
    # "no new article" for "no poll" because news_log stores first-seen rows only.
    duplicate_times = [
        _utc(row["raw_ingested_at"])
        for row in observations
        if row.get("source") == "alpaca_benzinga"
        and row.get("ledger") == "news_queue_drops"
        and row.get("discarded_reason") == "duplicate_id"
        and row.get("raw_ingested_at") is not None
    ]
    poll_since = min(duplicate_times) if duplicate_times else args.since
    poll_rows = [
        row
        for row in observations
        if row.get("raw_ingested_at") is not None
        and _utc(row["raw_ingested_at"]) >= poll_since
    ]
    poll_summary, poll_cycles = summarize_alpaca_polls(
        poll_rows, stale_hours=args.stale_hours
    )

    print(
        render_report(
            since=args.since,
            until=args.until,
            focus_date=args.focus_date,
            source_rows=source_rows,
            hourly_rows=hourly_rows,
            stale_rows=stale_rows,
            focus_stale_cycles=focus_stale_cycles,
            stale_total=len(stale),
            stale_measurable=sum(
                row.get("published_at") is not None and row.get("raw_ingested_at") is not None
                for row in stale
            ),
            poll_summary=poll_summary,
            poll_cycles=poll_cycles,
        ),
        end="",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
