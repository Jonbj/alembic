#!/usr/bin/env python3
"""Export an immutable, read-only snapshot of the S4 entry funnel.

The snapshot is deliberately normalised into two JSONL tables:

* ``signals.jsonl``: source article, resolver evidence, raw model outputs and
  the ensemble signal (one row per signal in the selected intent population);
* ``intents.jsonl``: every point-in-time S4 candidate/disposition pair, plus
  execution, trade and shadow-lifecycle evidence (one row per intent).

The destination directory is created atomically and is never overwritten.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping
from uuid import UUID

import psycopg2
from psycopg2.extras import RealDictCursor

from src.config import config


SIGNALS_SQL_TEMPLATE = """
WITH population AS (
    __SIGNAL_POPULATION_SQL__
), model_outputs AS (
    SELECT
        response.signal_id,
        jsonb_agg(
            jsonb_build_object(
                'response_id', response.id,
                'model_id', response.model_id,
                'polarity', response.polarity,
                'confidence', response.confidence,
                'eligible', response.eligible,
                'event_type', response.event_type,
                'directness', response.directness,
                'materiality', response.materiality,
                'novelty', response.novelty,
                'risk_flags', response.risk_flags,
                'evidence_sentences', response.evidence_sentences,
                'reasoning', response.reasoning,
                'generated_at', response.generated_at
            ) ORDER BY response.generated_at, response.id
        ) AS outputs
    FROM llm_responses AS response
    JOIN population USING (signal_id)
    GROUP BY response.signal_id
), resolver_outputs AS (
    SELECT
        resolved.news_log_id,
        jsonb_agg(
            jsonb_build_object(
                'resolver_row_id', resolved.id,
                'candidate_ticker', resolved.candidate_ticker,
                'extraction_method', resolved.extraction_method,
                'decision', resolved.decision,
                'resolved_ticker', resolved.resolved_ticker,
                'resolution_confidence', resolved.resolution_confidence,
                'ambiguity_margin', resolved.ambiguity_margin,
                'directness', resolved.directness,
                'tradable', resolved.tradable,
                'exchange', resolved.exchange,
                'figi', resolved.figi,
                'source_ticker_match', resolved.source_ticker_match,
                'alias_match', resolved.alias_match,
                'sec_openfigi_match', resolved.sec_openfigi_match,
                'llm_agreement', resolved.llm_agreement,
                'created_at', resolved.created_at
            ) ORDER BY resolved.created_at, resolved.id
        ) AS outputs
    FROM news_resolved_entities AS resolved
    GROUP BY resolved.news_log_id
)
SELECT
    1 AS schema_version,
    signal.id AS signal_id,
    signal.symbol,
    signal.score,
    signal.confidence,
    signal.reasoning AS ensemble_reasoning,
    signal.model_id AS ensemble_model_id,
    signal.ensemble_std,
    signal.fallback_used,
    signal.generated_at,
    signal.published_at AS signal_published_at,
    signal.forward_return AS forward_return_1d,
    signal.forward_return_3d,
    signal.forward_return_5d,
    signal.news_log_id,
    news.title,
    news.url,
    news.source,
    news.ticker AS source_ticker,
    news.raw_sentiment,
    news.published_at AS news_published_at,
    news.raw_ingested_at,
    news.fetched_at,
    news.extraction_method,
    news.content_hash,
    news.discarded_reason,
    COALESCE(resolver.outputs, '[]'::jsonb) AS resolver_outputs,
    COALESCE(models.outputs, '[]'::jsonb) AS model_outputs
FROM population
JOIN sentiment_signals AS signal ON signal.id = population.signal_id
LEFT JOIN news_log AS news ON news.id = signal.news_log_id
LEFT JOIN resolver_outputs AS resolver ON resolver.news_log_id = signal.news_log_id
LEFT JOIN model_outputs AS models ON models.signal_id = signal.id
ORDER BY signal.id
"""


SIGNAL_POPULATION_SQL = {
    "intent": """
        SELECT DISTINCT signal_id
        FROM s4_intent_events
        WHERE event_type = 'candidate'
          AND signal_id IS NOT NULL
          AND decision_slot >= %s
          AND decision_slot < %s
    """,
    "generated": """
        SELECT id AS signal_id
        FROM sentiment_signals
        WHERE generated_at >= %s
          AND generated_at < %s
    """,
}


INTENTS_SQL = """
WITH candidates AS (
    SELECT *
    FROM s4_intent_events
    WHERE event_type = 'candidate'
      AND decision_slot >= %s
      AND decision_slot < %s
), dispositions AS (
    SELECT *
    FROM s4_intent_events
    WHERE event_type = 'disposition'
), execution AS (
    SELECT
        decision.signal_id,
        jsonb_agg(
            jsonb_build_object(
                'decision_id', decision.id,
                'tick_time', decision.tick_time,
                'symbol', decision.symbol,
                'allocation_score', decision.score,
                'signal_score', decision.signal_score,
                'regime_mult', decision.regime_mult,
                'ema_pass', decision.ema_pass,
                'decision', decision.decision,
                'order_id', decision.order_id,
                'reason', decision.reason,
                'exit_mechanism', decision.exit_mechanism,
                'counterfactual_return_1h', decision.counterfactual_return_1h,
                'counterfactual_return_overnight', decision.counterfactual_return_overnight,
                'counterfactual_computed_at', decision.counterfactual_computed_at,
                'counterfactual_skip_reason', decision.counterfactual_skip_reason,
                'counterfactual_attempts', decision.counterfactual_attempts
            ) ORDER BY decision.tick_time, decision.id
        ) AS rows
    FROM execution_decisions AS decision
    JOIN (SELECT DISTINCT signal_id FROM candidates) AS population USING (signal_id)
    GROUP BY decision.signal_id
), trade_rows AS (
    SELECT
        trade.signal_id,
        jsonb_agg(
            jsonb_build_object(
                'trade_id', trade.id,
                'decision_id', trade.decision_id,
                'symbol', trade.symbol,
                'entry_order_id', trade.entry_order_id,
                'entry_price', trade.entry_price,
                'entry_time', trade.entry_time,
                'entry_notional', trade.entry_notional,
                'allocation_score', trade.score,
                'signal_score', trade.signal_score,
                'regime_mult', trade.regime_mult,
                'exit_order_id', trade.exit_order_id,
                'exit_order_ids', trade.exit_order_ids,
                'exit_price', trade.exit_price,
                'exit_time', trade.exit_time,
                'exit_reason', trade.exit_reason,
                'qty', trade.qty,
                'quantity_remaining', trade.quantity_remaining,
                'gross_pnl', trade.gross_pnl,
                'slippage_est', trade.slippage_est,
                'net_pnl', trade.net_pnl,
                'cost_bps', trade.cost_bps,
                'cost_usd', trade.cost_usd,
                'spread_cost_bps', trade.spread_cost_bps,
                'impact_cost_bps', trade.impact_cost_bps,
                'regulatory_cost_usd', trade.regulatory_cost_usd,
                'stop_strategy', trade.stop_strategy,
                'stop_mode', trade.stop_mode,
                'stop_vol_at_entry', trade.stop_vol_at_entry,
                'stop_d_init', trade.stop_d_init,
                'stop_vol_source', trade.stop_vol_source
            ) ORDER BY trade.entry_time, trade.id
        ) AS rows
    FROM trades AS trade
    JOIN (SELECT DISTINCT signal_id FROM candidates) AS population USING (signal_id)
    GROUP BY trade.signal_id
), lifecycle_rows AS (
    SELECT
        lifecycle.intent_id,
        jsonb_agg(
            jsonb_build_object(
                'event_id', lifecycle.event_id,
                'event_type', lifecycle.event_type,
                'observed_at', lifecycle.observed_at,
                'order_id', lifecycle.order_id,
                'status', lifecycle.status,
                'reason_code', lifecycle.reason_code,
                'fill_id', lifecycle.fill_id,
                'filled_at', lifecycle.filled_at,
                'filled_quantity', lifecycle.filled_quantity,
                'filled_notional', lifecycle.filled_notional,
                'fill_price', lifecycle.fill_price,
                'first_executable_price', lifecycle.first_executable_price,
                'first_executable_price_source', lifecycle.first_executable_price_source,
                'd0', lifecycle.d0,
                'due_session', lifecycle.due_session,
                'policy_version', lifecycle.policy_version,
                's1_virtual_quantity', lifecycle.s1_virtual_quantity,
                's4_virtual_quantity', lifecycle.s4_virtual_quantity,
                'broker_quantity', lifecycle.broker_quantity,
                'unattributed_quantity', lifecycle.unattributed_quantity,
                'virtual_exit_quantity', lifecycle.virtual_exit_quantity,
                'virtual_exit_price', lifecycle.virtual_exit_price,
                'reconstructible', lifecycle.reconstructible,
                'details', lifecycle.details
            ) ORDER BY lifecycle.observed_at, lifecycle.event_id
        ) AS rows
    FROM s4_lifecycle_events AS lifecycle
    JOIN candidates ON candidates.intent_id = lifecycle.intent_id
    GROUP BY lifecycle.intent_id
)
SELECT
    1 AS schema_version,
    candidate.intent_id,
    candidate.causal_event_id,
    candidate.event_id AS candidate_event_id,
    disposition.event_id AS disposition_event_id,
    candidate.decision_slot,
    candidate.symbol,
    candidate.signal_id,
    candidate.published_at,
    candidate.first_seen_at,
    candidate.model_generated_at,
    candidate.decision_at,
    candidate.rank AS candidate_rank,
    disposition.rank AS final_rank,
    disposition.anti_pyramiding AS held_at_rank_legacy_proxy,
    EXTRACT(
        EPOCH FROM candidate.decision_slot - candidate.model_generated_at
    ) AS signal_age_at_slot_seconds,
    candidate.competing_candidates,
    candidate.s1_state AS candidate_s1_state,
    disposition.s1_state AS final_s1_state,
    disposition.anti_pyramiding,
    candidate.reason_code AS candidate_reason_code,
    disposition.reason_code AS final_reason_code,
    disposition.is_tradable,
    candidate.versions,
    candidate.snapshot AS candidate_snapshot,
    disposition.snapshot AS disposition_snapshot,
    candidate.missingness AS candidate_missingness,
    disposition.missingness AS disposition_missingness,
    COALESCE(execution.rows, '[]'::jsonb) AS execution_decisions,
    COALESCE(trades.rows, '[]'::jsonb) AS trades,
    COALESCE(lifecycle.rows, '[]'::jsonb) AS lifecycle_events
FROM candidates AS candidate
LEFT JOIN dispositions AS disposition
  ON disposition.intent_id = candidate.intent_id
LEFT JOIN execution ON execution.signal_id = candidate.signal_id
LEFT JOIN trade_rows AS trades ON trades.signal_id = candidate.signal_id
LEFT JOIN lifecycle_rows AS lifecycle ON lifecycle.intent_id = candidate.intent_id
ORDER BY candidate.decision_slot, candidate.symbol, candidate.intent_id
"""


COUNTS_SQL = """
SELECT
    COUNT(*) FILTER (WHERE event_type = 'candidate') AS candidate_events,
    COUNT(*) FILTER (WHERE event_type = 'disposition') AS disposition_events,
    COUNT(DISTINCT signal_id) FILTER (WHERE event_type = 'candidate') AS distinct_signals,
    COUNT(DISTINCT causal_event_id) FILTER (WHERE event_type = 'candidate') AS distinct_causal_events,
    COUNT(DISTINCT symbol) FILTER (WHERE event_type = 'candidate') AS distinct_symbols,
    MIN(decision_slot) FILTER (WHERE event_type = 'candidate') AS first_decision_slot,
    MAX(decision_slot) FILTER (WHERE event_type = 'candidate') AS last_decision_slot
FROM s4_intent_events
WHERE decision_slot >= %s
  AND decision_slot < %s
"""


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamps must include a timezone")
    return parsed


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"cannot serialise {type(value).__name__}")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> int:
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            json.dump(
                dict(row),
                handle,
                default=_json_default,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            handle.write("\n")
            count += 1
        handle.flush()
        os.fsync(handle.fileno())
    return count


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(
            dict(value),
            handle,
            default=_json_default,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_snapshot(
    output_dir: Path,
    start: datetime,
    end: datetime,
    *,
    signal_population: str = "intent",
) -> dict[str, Any]:
    if end <= start:
        raise ValueError("end must be later than start")
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite immutable snapshot: {output_dir}")
    population_sql = SIGNAL_POPULATION_SQL[signal_population]
    signals_sql = SIGNALS_SQL_TEMPLATE.replace(
        "__SIGNAL_POPULATION_SQL__", population_sql
    )
    signal_count_sql = f"SELECT COUNT(*) AS rows FROM ({population_sql}) AS population"

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary_dir = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent)
    )
    connection = None
    try:
        connection = psycopg2.connect(config.DATABASE_URL)
        connection.set_session(readonly=True, autocommit=False)

        signals_path = temporary_dir / "signals.jsonl"
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(signals_sql, (start, end))
            signal_count = _write_jsonl(signals_path, cursor)

        intents_path = temporary_dir / "intents.jsonl"
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(INTENTS_SQL, (start, end))
            intent_count = _write_jsonl(intents_path, cursor)

        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(COUNTS_SQL, (start, end))
            source_counts = dict(cursor.fetchone())
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(signal_count_sql, (start, end))
            signal_population_rows = int(cursor.fetchone()["rows"])

        connection.rollback()

        if intent_count != source_counts["candidate_events"]:
            raise RuntimeError(
                "intent export is incomplete: "
                f"{intent_count} rows vs {source_counts['candidate_events']} candidates"
            )
        if signal_count != signal_population_rows:
            raise RuntimeError(
                "signal export is incomplete: "
                f"{signal_count} rows vs {signal_population_rows} signals"
            )

        manifest = {
            "schema_version": 1,
            "generated_at": datetime.now().astimezone(),
            "window": {"start_inclusive": start, "end_exclusive": end},
            "database_transaction": "READ ONLY",
            "signal_population": signal_population,
            "signal_population_rows": signal_population_rows,
            "tables": {
                "signals.jsonl": {
                    "rows": signal_count,
                    "sha256": _sha256(signals_path),
                },
                "intents.jsonl": {
                    "rows": intent_count,
                    "sha256": _sha256(intents_path),
                },
            },
            "source_counts": source_counts,
            "query_sha256": {
                "signals": hashlib.sha256(signals_sql.encode()).hexdigest(),
                "intents": hashlib.sha256(INTENTS_SQL.encode()).hexdigest(),
                "counts": hashlib.sha256(COUNTS_SQL.encode()).hexdigest(),
                "signal_count": hashlib.sha256(signal_count_sql.encode()).hexdigest(),
            },
        }
        _write_json(temporary_dir / "manifest.json", manifest)
        os.replace(temporary_dir, output_dir)
        return manifest
    except Exception:
        shutil.rmtree(temporary_dir, ignore_errors=True)
        raise
    finally:
        if connection is not None:
            connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--start", required=True, type=_parse_datetime)
    parser.add_argument("--end", required=True, type=_parse_datetime)
    parser.add_argument(
        "--signal-population",
        choices=sorted(SIGNAL_POPULATION_SQL),
        default="intent",
        help="signals selected from S4 intents (default) or generated_at",
    )
    args = parser.parse_args()

    manifest = export_snapshot(
        args.output_dir,
        args.start,
        args.end,
        signal_population=args.signal_population,
    )
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir),
                "signal_rows": manifest["tables"]["signals.jsonl"]["rows"],
                "intent_rows": manifest["tables"]["intents.jsonl"]["rows"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
