"""Contratto SQL della metrica burned-slot S4 (#429)."""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import psycopg2
import pytest


MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "060_s4_burned_slot_metrics.sql"
)


def test_migrazione_aggiunge_le_misure_candidate_senza_update_append_only():
    sql = MIGRATION.read_text()

    assert "ADD COLUMN IF NOT EXISTS held_at_rank" in sql
    assert "ADD COLUMN IF NOT EXISTS signal_age_at_slot" in sql
    assert "UPDATE s4_intent_events" not in sql


def test_rollup_per_slot_espone_i_tre_contatori_richiesti():
    sql = MIGRATION.read_text()

    assert "CREATE VIEW s4_burned_slot_metrics" in sql
    assert "slots_burned_by_held" in sql
    assert "slots_burned_by_stale" in sql
    assert "candidates_cut_with_zero_orders" in sql
    assert "RANK_OUTSIDE_TOP_N" in sql
    assert "SUBMITTED" in sql


def test_rollup_giornaliero_conserva_denominatori_del_report_27_agosto():
    sql = MIGRATION.read_text()

    assert "CREATE VIEW s4_burned_slot_metrics_daily" in sql
    assert "decision_slots" in sql
    assert "slots_with_at_least_four_held" in sql
    assert "slots_with_candidates_cut_zero_orders" in sql
    assert "America/New_York" in sql


def test_rollup_riproduce_venti_e_otto_cicli_del_27_agosto():
    url = os.environ.get(
        "DATABASE_URL", "postgresql://trading:trading@localhost:5432/trading"
    )
    try:
        conn = psycopg2.connect(url, connect_timeout=3)
    except psycopg2.OperationalError as exc:
        pytest.skip(f"PostgreSQL locale non disponibile: {exc}")

    schema = f"test_s4_burned_{uuid4().hex}"
    migration_050 = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "050_s4_entry_intent_ledger.sql"
    ).read_text()
    try:
        with conn.cursor() as cur:
            cur.execute(f'CREATE SCHEMA "{schema}"')
            cur.execute(f'SET LOCAL search_path TO "{schema}", pg_catalog')
            cur.execute("CREATE TABLE sentiment_signals (id BIGINT PRIMARY KEY)")
            cur.execute("""
                CREATE TABLE news_resolved_entities (
                    id BIGINT PRIMARY KEY,
                    news_log_id BIGINT,
                    candidate_ticker TEXT,
                    created_at TIMESTAMPTZ
                )
            """)
            cur.execute(migration_050)
            cur.execute(MIGRATION.read_text())

            insert = """
                INSERT INTO s4_intent_events (
                    event_id, intent_id, causal_event_id, event_type,
                    occurred_at, decision_slot, symbol, model_generated_at,
                    decision_at, rank, held_at_rank, signal_age_at_slot,
                    competing_candidates, s1_state, anti_pyramiding,
                    reason_code, is_tradable, versions, snapshot, missingness
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, NULL,
                    '[]'::jsonb, '{}'::jsonb, %s, %s, %s,
                    %s::jsonb, '{}'::jsonb, '{}'::jsonb
                )
            """
            first_slot = datetime(2026, 8, 27, 13, 37, tzinfo=timezone.utc)
            versions = json.dumps({
                "ranking": {"n_top": 5},
                "gate": {"max_signal_age_hours": 4},
            })
            zero_order_slots = set(range(7)) | {16}
            rows = []
            for cycle in range(24):
                slot = first_slot + timedelta(minutes=15 * cycle)
                for rank in range(1, 9):
                    intent_id = str(uuid4())
                    symbol = "NOW" if 16 <= cycle < 22 and rank == 8 else f"S{rank}"
                    held = cycle < 20 and (rank <= 4 or (cycle == 16 and rank == 5))
                    generated_at = slot - timedelta(days=2) if rank in {1, 3} else slot
                    if rank > 5:
                        reason = "RANK_OUTSIDE_TOP_N"
                        anti_pyramiding = None
                        is_tradable = False
                    elif held:
                        reason = "SKIP_PYRAMIDING"
                        anti_pyramiding = True
                        is_tradable = True
                    elif cycle not in zero_order_slots and rank == 5:
                        reason = "SUBMITTED"
                        anti_pyramiding = False
                        is_tradable = True
                    else:
                        reason = "NO_ENTRY_ORDER"
                        anti_pyramiding = False
                        is_tradable = True
                    common = (
                        str(uuid4()), intent_id, f"signal:{cycle}:{rank}",
                    )
                    rows.append(common + (
                        "candidate", slot, slot, symbol, generated_at, slot,
                        None, None, "CANDIDATE_OBSERVED", None, versions,
                    ))
                    rows.append((str(uuid4()), intent_id, common[2]) + (
                        "disposition", slot, slot, symbol, generated_at, slot,
                        rank, anti_pyramiding, reason, is_tradable, versions,
                    ))
            cur.executemany(insert, rows)

            cur.execute("""
                SELECT decision_slots, slots_with_at_least_four_held,
                       slots_with_candidates_cut_zero_orders
                FROM s4_burned_slot_metrics_daily
                WHERE session_date = DATE '2026-08-27'
            """)
            assert cur.fetchone() == (24, 20, 8)

            cur.execute("""
                SELECT slots_burned_by_held, slots_burned_by_stale,
                       candidates_cut_with_zero_orders
                FROM s4_burned_slot_metrics
                WHERE decision_slot = TIMESTAMPTZ '2026-08-27 17:37:00+00'
            """)
            assert cur.fetchone() == (5, 2, 3)

            cur.execute("""
                SELECT COUNT(*)
                FROM s4_intent_events AS candidate
                JOIN s4_intent_events AS disposition USING (intent_id)
                WHERE candidate.event_type = 'candidate'
                  AND disposition.event_type = 'disposition'
                  AND candidate.symbol = 'NOW'
                  AND disposition.rank = 8
            """)
            assert cur.fetchone() == (6,)
    finally:
        conn.rollback()
        conn.close()
