"""#551/F-072 — selezione delle righe duplicate da riparare (script one-off)."""

from scripts.repair_f072_duplicate_signals import (
    F072_NEWS_LOG_IDS,
    rows_to_delete,
)


def make_signal(signal_id: int, news_log_id: int, model_id: str = "finbert") -> dict:
    return {
        "id": signal_id,
        "news_log_id": news_log_id,
        "symbol": "AAPL",
        "score": 0.0,
        "model_id": model_id,
        "generated_at": f"2026-09-08T15:{signal_id % 60:02d}:00+00:00",
    }


def test_il_primo_giro_resta_il_secondo_via() -> None:
    """Il re-score del crash recovery e' la riga in eccesso: si tiene il primo
    giro di scoring (id minore), quello che l'articolo ha davvero prodotto."""
    rows = [
        make_signal(101, 9902, model_id="finbert"),
        make_signal(102, 9902, model_id="single:gpt-oss"),
    ]

    dropped = rows_to_delete(rows)

    assert [r["id"] for r in dropped] == [102]


def test_gruppi_singoli_non_toccati() -> None:
    rows = [make_signal(101, 9902), make_signal(201, 55555)]

    assert rows_to_delete(rows) == []


def test_solo_i_dodici_gruppi_f072() -> None:
    # La tabella della issue: news_log 9902-9913.
    assert F072_NEWS_LOG_IDS == list(range(9902, 9914))


def test_ordine_di_ingresso_indifferente() -> None:
    rows = [
        make_signal(302, 9903, model_id="ensemble"),
        make_signal(301, 9903, model_id="finbert"),
    ]

    dropped = rows_to_delete(rows)

    assert [r["id"] for r in dropped] == [302]
