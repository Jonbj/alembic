"""Il promotion gate contro lo schema reale delle migrazioni (#470).

`_fetch_lifecycle_row` seleziona `promotion_blocked`, colonna che la migrazione
025 non ha mai creato: sul DB live promote e approve rispondevano 500 (e demote,
che passa dalla stessa SELECT, era rotta allo stesso modo). I 17 test di
test_p2_promotion_wiring.py mockano il DB, quindi la SELECT non era mai stata
eseguita contro uno schema vero.

Qui la catena completa delle migrazioni viene applicata a uno schema
usa-e-getta di un PostgreSQL locale e le funzioni del gate girano contro
quello schema, con la stessa connessione plain (cursore di default) che
`_get_db_conn()` passa in produzione.
"""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import psycopg2
import pytest

from scripts.apply_migrations import apply_migrations


@pytest.fixture
def gate_db():
    url = os.environ.get(
        "DATABASE_URL", "postgresql://trading:trading@localhost:5432/trading"
    )
    try:
        conn = psycopg2.connect(url, connect_timeout=3)
    except psycopg2.OperationalError as exc:
        pytest.skip(f"PostgreSQL locale non disponibile: {exc}")

    schema = f"test_promotion_gate_{uuid4().hex}"
    migrations_dir = Path(__file__).resolve().parents[2] / "migrations"
    try:
        with conn.cursor() as cur:
            cur.execute(f'CREATE SCHEMA "{schema}"')
            cur.execute(f'SET search_path TO "{schema}", pg_catalog')
        conn.commit()
        apply_migrations(conn, sorted(migrations_dir.glob("*.sql")))
        yield conn
    finally:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        conn.commit()
        conn.close()


def test_la_select_del_gate_gira_contro_lo_schema_delle_migrazioni(gate_db):
    from src.strategies.promotion import _fetch_lifecycle_row

    row = _fetch_lifecycle_row("S1", gate_db)

    assert row is not None, "la migrazione 025 semina S1: la riga deve esserci"
    assert row["mode"] == "supervised_paper"
    # S1 e' dichiarata bloccata in config/strategies.yaml: il backfill della
    # colonna deve mantenerla bloccata.
    assert row["promotion_blocked"] is True


def test_il_backfill_non_sblocca_nessuna_strategia(gate_db):
    # Review PR #598: il TRUE-per-tutte non e' un ritocco del flag ma la
    # materializzazione dello stato di fatto. La variante letterale «backfill
    # dallo YAML» lascerebbe S2 e S7 a FALSE, riaprendo percorsi sequenziali
    # di promozione che la rottura tiene chiusi dal giorno del seed — per S7
    # contro il blocco esplicito registrato in audit il 2026-07-03. Il freeze
    # #171 esige la variante che non apre nulla; questo test la pinna.
    with gate_db.cursor() as cur:
        cur.execute(
            "SELECT strategy_id FROM strategy_lifecycle WHERE NOT promotion_blocked"
        )
        sbloccate = [r[0] for r in cur.fetchall()]

    assert sbloccate == [], (
        "dopo la catena delle migrazioni nessuna strategia deve risultare "
        f"promuovibile: sbloccate={sbloccate}"
    )


def test_riga_nuova_nasce_bloccata_fail_closed(gate_db):
    from src.strategies.promotion import _fetch_lifecycle_row

    with gate_db.cursor() as cur:
        cur.execute("INSERT INTO strategy_lifecycle (strategy_id) VALUES ('S9')")
    gate_db.commit()

    row = _fetch_lifecycle_row("S9", gate_db)
    assert row["promotion_blocked"] is True, (
        "una riga nuova deve nascere bloccata: il default della colonna e' "
        "la salvaguardia fail-closed del gate"
    )


def test_promotion_blocked_in_tabella_blocca_la_promozione(gate_db):
    from src.strategies.promotion import PromotionBlockedError, request_promotion

    # S4: paper -> supervised_paper e' sequenziale e non tocca 'live', quindi
    # l'unico check che puo' rifiutare e' promotion_blocked (backfill: True).
    with pytest.raises(PromotionBlockedError, match="promotion_blocked"):
        request_promotion("S4", "supervised_paper", "gate-r1", "test", gate_db)


def test_ciclo_request_approve_su_riga_sbloccata_dall_operatore(gate_db):
    from src.strategies.promotion import (
        _fetch_lifecycle_row,
        approve_promotion,
        request_promotion,
    )

    # Lo sblocco e' l'azione dell'operatore (fuori da questa issue): qui la
    # simula per esercitare contro lo schema reale il percorso che il gate
    # non ha mai percorso.
    with gate_db.cursor() as cur:
        cur.execute(
            "UPDATE strategy_lifecycle SET promotion_blocked = FALSE "
            "WHERE strategy_id = 'S4'"
        )
    gate_db.commit()

    request_promotion("S4", "supervised_paper", "gate-r1", "operatore", gate_db)
    row = _fetch_lifecycle_row("S4", gate_db)
    assert row["target_mode"] == "supervised_paper"
    assert row["mode"] == "paper"

    approve_promotion("S4", "operatore", gate_db)
    row = _fetch_lifecycle_row("S4", gate_db)
    assert row["mode"] == "supervised_paper"
    assert row["target_mode"] is None
    assert row["approved"] is True

    with gate_db.cursor() as cur:
        cur.execute(
            "SELECT action FROM strategy_lifecycle_audit "
            "WHERE strategy_id = 'S4' ORDER BY id"
        )
        actions = [r[0] for r in cur.fetchall()]
    assert actions == ["requested", "approved"]


def test_demote_passa_dalla_stessa_select_e_ora_gira(gate_db):
    from src.strategies.promotion import _fetch_lifecycle_row, demote_strategy

    # La issue diceva che demote funzionava perche' "non legge quel campo":
    # falso, chiama _fetch_lifecycle_row come le altre due. Questo test lo
    # pinna contro lo schema reale.
    demote_strategy("S1", "paper", "test #470", "test", gate_db)

    row = _fetch_lifecycle_row("S1", gate_db)
    assert row["mode"] == "paper"
