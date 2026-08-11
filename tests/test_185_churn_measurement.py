"""#185: misura del churn S1 post-flip, senza DB o Redis reali.

La firma che questa issue chiede di misurare e' specifica: *reingresso **S1**
allo stesso **peso** entro **15-60 minuti***. La PR #207 fu respinta perche'
classificava come churn qualunque BUY dello stesso simbolo entro 60 minuti,
senza filtrare per strategia, peso ne' esecuzione. Questi test inchiodano i
quattro vincoli della firma e — soprattutto — il verdetto di uscita, che deve
distinguere "niente da misurare" da "churn fermato": un numero che si legge
come successo a vuoto (zero drop post-deploy perche' non c'e' stata una
finestra di ribilanciamento) e' lo stesso modo di sbagliare di #191/#210.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from scripts.measure_185_churn import (
    _fetch_rows,
    classify_drops,
    per_session,
    verdict,
)


def _ts(day: int, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 8, day, hour, minute, second, tzinfo=timezone.utc)


def _row(
    day: int,
    hour: int,
    minute: int,
    symbol: str,
    decision: str,
    *,
    strategy_id: str = "S1",
    target_weight: float = 0.012,
    order_id: str | None = "executed-order",
    exit_mechanism: str | None = None,
) -> dict:
    return {
        "tick_time": _ts(day, hour, minute),
        "symbol": symbol,
        "decision": decision,
        "exit_mechanism": exit_mechanism,
        "strategy_id": strategy_id,
        "target_weight": target_weight,
        "order_id": order_id,
    }


def _drop(*, day: int = 5, hour: int = 17, minute: int = 52, **overrides) -> dict:
    return _row(
        day,
        hour,
        minute,
        overrides.pop("symbol", "BP"),
        "SELL",
        exit_mechanism="s1_weight_drop",
        **overrides,
    )


def _buy(*, day: int = 5, hour: int = 18, minute: int = 7, **overrides) -> dict:
    return _row(
        day,
        hour,
        minute,
        overrides.pop("symbol", "BP"),
        "BUY",
        **overrides,
    )


# ── i quattro vincoli della firma prescritta ──────────────────────────────────


def test_same_s1_weight_rebought_after_15_minutes_is_churn():
    drops = classify_drops([_drop(), _buy()])

    assert drops == [
        {
            "tick_time": _ts(5, 17, 52),
            "symbol": "BP",
            "target_weight": pytest.approx(0.012),
            "reentry_time": _ts(5, 18, 7),
            "is_churn": True,
        }
    ]


def test_reentry_before_15_minutes_is_not_churn():
    drops = classify_drops([_drop(), _buy(hour=18, minute=6)])

    assert drops[0]["is_churn"] is False


def test_reentry_at_60_minutes_is_churn_but_later_is_not():
    at_limit = classify_drops([_drop(), _buy(hour=18, minute=52)])
    after_limit = classify_drops([_drop(), _buy(hour=18, minute=53)])

    assert at_limit[0]["is_churn"] is True
    assert after_limit[0]["is_churn"] is False


def test_s4_buy_is_not_an_s1_reentry():
    # #207 fu respinto anche perche' contava i reingressi S4, che sono un
    # meccanismo distinto (l'overlay S4 che liquida il core S1, #182).
    drops = classify_drops([_drop(), _buy(strategy_id="S4")])

    assert drops[0]["is_churn"] is False


def test_different_weight_is_not_the_round_trip_signature():
    drops = classify_drops([_drop(target_weight=0.012), _buy(target_weight=0.02)])

    assert drops[0]["is_churn"] is False


def test_same_reported_weight_uses_the_scheduler_display_granularity():
    # BP 2026-08-05: entrambi sono il target 1,2% riportato dal Decision Log.
    # Il peso raw si muove leggermente col NAV fra cicli, quindi confrontiamo
    # il peso visibile all'operatore (un decimale in percentuale) invece di
    # pretendere che i float binari siano identici.
    drops = classify_drops(
        [
            _drop(target_weight=0.01158564164115341),
            _buy(target_weight=0.011585121552000146),
        ]
    )

    assert drops[0]["is_churn"] is True


def test_buy_without_order_id_was_not_executed_and_is_not_churn():
    drops = classify_drops([_drop(), _buy(order_id=None)])

    assert drops[0]["is_churn"] is False


def test_different_symbol_is_not_a_reentry():
    drops = classify_drops([_drop(), _buy(symbol="SNOW")])

    assert drops[0]["is_churn"] is False


def test_only_executed_s1_weight_drops_are_classified():
    rows = [
        _drop(symbol="BP"),
        _drop(symbol="SNOW", strategy_id="S4"),
        _drop(symbol="SBUX", order_id=None),
        _row(5, 17, 52, "ABBV", "SELL", exit_mechanism="sentiment_reversal"),
    ]

    assert [drop["symbol"] for drop in classify_drops(rows)] == ["BP"]


def test_no_matching_reentry_is_a_definitive_monthly_liquidation():
    # Con la cadenza MONTHLY rispettata, un'uscita senza reingresso entro
    # 60 minuti e' una liquidazione definitiva fino alla prossima finestra
    # mensile — non churn.
    drops = classify_drops([_drop(day=7, hour=14, minute=22, symbol="BRK.B")])

    assert drops[0]["reentry_time"] is None
    assert drops[0]["is_churn"] is False


# ── la query acquisisce strategia, peso e prova di esecuzione ────────────────


def test_fetch_rows_acquires_strategy_weight_and_executed_order_id():
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            "tick_time": _ts(5, 17, 52),
            "symbol": "BP",
            "decision": "SELL",
            "exit_mechanism": "s1_weight_drop",
            "strategy_id": "S1",
            "target_weight": 0.012,
            "order_id": "sell-order",
        }
    ]
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor

    rows = _fetch_rows(conn, _ts(1, 0, 0))

    assert rows == [dict(cursor.fetchall.return_value[0])]
    sql = " ".join(cursor.execute.call_args.args[0].split()).lower()
    # I tre attributi che #207 non acquisiva e che distinguono la firma.
    assert "stop_strategy as strategy_id" in sql
    assert "score as target_weight" in sql
    assert sql.count("order_id is not null") == 2


# ── aggregazione per sessione e fase di deploy ──────────────────────────────


def test_drops_are_aggregated_by_utc_session_and_deploy_phase():
    deploy = _ts(7, 14, 7)
    drops = [
        {
            "tick_time": _ts(5, 17, 52),
            "symbol": "BP",
            "target_weight": 0.012,
            "reentry_time": _ts(5, 18, 7),
            "is_churn": True,
        },
        {
            "tick_time": _ts(7, 14, 22),
            "symbol": "BRK.B",
            "target_weight": 0.012,
            "reentry_time": None,
            "is_churn": False,
        },
    ]

    assert per_session(drops, deploy) == [
        {"date": "2026-08-05", "phase": "pre", "drops": 1, "churn": 1},
        {"date": "2026-08-07", "phase": "post", "drops": 1, "churn": 0},
    ]


# ── il verdetto distingue "niente da misurare" da "churn fermato" ─────────────
# Questo e' il gap che la PR #217 (v2) lascia aperto: il suo main() stampa
# "Firma assente dopo il deploy" quando post_churn == 0, anche se post_drops ==
# 0. Ma nel scenario probabile — nessun ribilanciamento mensile nei primi
# giorni post-deploy — zero drop significa "nessuna finestra osservata", non
# "il churn e' sparito". Riportare un successo a vuoto e' proprio la classe di
# errore (una misura che non misura cio' che dichiara) che ha fatto respingere
# #207 e che #191/#210 documentano altrove.


def test_verdict_post_phase_with_no_drops_is_inconclusive_not_resolved():
    sessions = [
        {"date": "2026-08-05", "phase": "pre", "drops": 6, "churn": 6},
        {"date": "2026-08-08", "phase": "post", "drops": 0, "churn": 0},
    ]

    result = verdict(sessions)

    assert result["post_drops"] == 0
    assert result["post_churn"] == 0
    assert result["post_status"] == "inconclusive"


def test_verdict_post_drops_with_zero_churn_is_resolved():
    sessions = [
        {"date": "2026-08-05", "phase": "pre", "drops": 6, "churn": 6},
        {"date": "2026-08-31", "phase": "post", "drops": 3, "churn": 0},
    ]

    result = verdict(sessions)

    assert result["post_drops"] == 3
    assert result["post_churn"] == 0
    assert result["post_status"] == "resolved"


def test_verdict_post_churn_present_is_still_present():
    sessions = [
        {"date": "2026-08-05", "phase": "pre", "drops": 6, "churn": 6},
        {"date": "2026-08-31", "phase": "post", "drops": 3, "churn": 2},
    ]

    result = verdict(sessions)

    assert result["post_churn"] == 2
    assert result["post_status"] == "still_present"


def test_verdict_reports_pre_phase_baselines_for_comparison():
    sessions = [
        {"date": "2026-08-05", "phase": "pre", "drops": 6, "churn": 4},
        {"date": "2026-08-31", "phase": "post", "drops": 3, "churn": 0},
    ]

    result = verdict(sessions)

    assert result["pre_drops"] == 6
    assert result["pre_churn"] == 4


# ── disclosure della caveat #184 ──────────────────────────────────────────────
# Il repo impone (scripts/daily_analysis.sh, docs/exit_mechanism_labels.md) di
# dichiarare esplicitamente quando un conteggio su exit_mechanism tocca righe
# pre-fix-#184. s1_weight_drop e' in realta' esente (e' il path #72 osservato,
# non il classificatore S4 dedotto per eta'), ma lo strumento deve dirlo invece
# di lasciare che un lettore lo scopra da solo.


def test_module_discloses_the_184_caveat_and_the_s1_weight_drop_exemption():
    import scripts.measure_185_churn as m

    caveat = m.EXIT_MECHANISM_CAVEAT
    assert "184" in caveat
    assert "s1_weight_drop" in caveat
    # L'esenzione: s1_weight_drop deriva dall'origine osservata della posizione
    # (#72), non dall'eta' del segnale che il fix #184 ha corretto.
    assert "72" in caveat


# ---------------------------------------------------------------------------
# Giorno del deploy (rilievo bloccante della review su PR #218).
# Il deploy cade a meta' seduta: aggregando per sola data, una singola uscita
# pre-deploy marcava tutta la giornata come `pre` e scartava l'evidenza post
# dello stesso giorno — con il verdetto che poteva dire `inconclusive` avendo
# in mano dati che dicevano il contrario.
# ---------------------------------------------------------------------------

def test_il_giorno_del_deploy_si_divide_in_due_fasi():
    from datetime import datetime, timezone
    from scripts.measure_185_churn import per_session

    cutoff = datetime(2026, 8, 7, 14, 7, tzinfo=timezone.utc)
    drops = [
        {"tick_time": datetime(2026, 8, 7, 13, 30, tzinfo=timezone.utc), "is_churn": True},
        {"tick_time": datetime(2026, 8, 7, 15, 0, tzinfo=timezone.utc), "is_churn": False},
        {"tick_time": datetime(2026, 8, 7, 16, 0, tzinfo=timezone.utc), "is_churn": False},
    ]
    righe = per_session(drops, cutoff)

    assert len(righe) == 2, f"il giorno misto deve produrre due righe, non {len(righe)}"
    pre = [r for r in righe if r["phase"] == "pre"][0]
    post = [r for r in righe if r["phase"] == "post"][0]
    assert pre["drops"] == 1 and pre["churn"] == 1
    assert post["drops"] == 2 and post["churn"] == 0, (
        "le due uscite post-deploy non devono finire nel bucket pre"
    )


def test_pre_viene_prima_di_post_nello_stesso_giorno():
    from datetime import datetime, timezone
    from scripts.measure_185_churn import per_session

    cutoff = datetime(2026, 8, 7, 14, 7, tzinfo=timezone.utc)
    drops = [
        {"tick_time": datetime(2026, 8, 7, 16, 0, tzinfo=timezone.utc), "is_churn": False},
        {"tick_time": datetime(2026, 8, 7, 13, 0, tzinfo=timezone.utc), "is_churn": True},
    ]
    assert [r["phase"] for r in per_session(drops, cutoff)] == ["pre", "post"]
