"""#432 Opzione B — la seduta di accodamento e' una proprieta' persistita.

La quota stale non e' una grandezza sola: una news accodata dal WebSocket alle
02:00Z e scartata alle 13:35Z e' fisiologia (nessun consumatore gira a mercato
chiuso), un outage del consumatore alle 15:00Z e' un guasto. Prima della
correzione cadevano entrambe in `went_stale_in_queue`, che ha fix opposti.

Il discrimine e' il momento di **accodamento**, non quello di scarto, e va
deciso qui — una volta, dal calendario — non ri-derivato in SQL con la crontab
`14-21` ricopiata (regola #169/#467: la misura chiama la regola, non la
riscrive; e una crontab UTC cablata sbaglia di un'ora per meta' anno).
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from src.workers.market_clock import is_regular_session_time
from src.workers.news_discards import build_news_discard_row
from src.workers.sentiment import build_stale_drop_row


class _Item:
    """Stand-in minimale per NewsItem — gli helper non devono servirsi del modello."""

    def __init__(self, id, timestamp, raw_ingested_at=None, source="alpaca_benzinga"):
        self.id = id
        self.timestamp = timestamp
        self.raw_ingested_at = raw_ingested_at
        self.source = source
        self.asset_tags = []
        self.title = ""


# --- is_regular_session_time ------------------------------------------------


@pytest.mark.parametrize(
    ("istante", "in_seduta"),
    [
        # Mercoledi' 2026-09-09, ora legale (EDT, UTC-4): 13:30Z-20:00Z.
        (datetime(2026, 9, 9, 13, 29, tzinfo=timezone.utc), False),
        (datetime(2026, 9, 9, 13, 30, tzinfo=timezone.utc), True),
        (datetime(2026, 9, 9, 15, 30, tzinfo=timezone.utc), True),
        (datetime(2026, 9, 9, 19, 59, tzinfo=timezone.utc), True),
        (datetime(2026, 9, 9, 20, 0, tzinfo=timezone.utc), False),
        (datetime(2026, 9, 9, 2, 0, tzinfo=timezone.utc), False),
    ],
)
def test_finestra_di_seduta_in_ora_legale(istante: datetime, in_seduta: bool) -> None:
    assert is_regular_session_time(istante) is in_seduta


@pytest.mark.parametrize(
    ("istante", "in_seduta"),
    [
        # Mercoledi' 2026-01-14, ora solare (EST, UTC-5): 14:30Z-21:00Z.
        # E' il caso che una crontab `14-21` cablata sbaglierebbe in silenzio.
        (datetime(2026, 1, 14, 13, 30, tzinfo=timezone.utc), False),
        (datetime(2026, 1, 14, 14, 29, tzinfo=timezone.utc), False),
        (datetime(2026, 1, 14, 14, 30, tzinfo=timezone.utc), True),
        (datetime(2026, 1, 14, 20, 59, tzinfo=timezone.utc), True),
        (datetime(2026, 1, 14, 21, 0, tzinfo=timezone.utc), False),
    ],
)
def test_la_finestra_segue_il_dst_e_non_un_orario_utc_cablato(
    istante: datetime, in_seduta: bool
) -> None:
    assert is_regular_session_time(istante) is in_seduta


@pytest.mark.parametrize("giorno", [date(2026, 9, 12), date(2026, 9, 13)])
def test_il_fine_settimana_e_sempre_fuori_seduta(giorno: date) -> None:
    mezzogiorno_ny = datetime(giorno.year, giorno.month, giorno.day, 16, tzinfo=timezone.utc)
    assert is_regular_session_time(mezzogiorno_ny) is False


def test_un_naive_e_letto_come_utc_come_ovunque_nel_path_di_scarto() -> None:
    # `_is_stale_news` e `build_stale_drop_row` leggono i naive come UTC: se qui
    # valesse un'altra convenzione, la stessa riga avrebbe due sedute diverse.
    assert is_regular_session_time(datetime(2026, 9, 9, 15, 30)) is True
    assert is_regular_session_time(datetime(2026, 9, 9, 2, 0)) is False


def test_una_festivita_infrasettimanale_resta_in_seduta_ed_e_deliberato() -> None:
    """Il Labor Day 2026-09-07 e' un lunedi' di borsa chiusa.

    Il calendario delle festivita' non e' modellato: senza chiamare Alpaca
    retroattivamente non e' ricostruibile per le righe gia' scritte. La scelta e'
    fail-closed **verso l'allerta** — classificare in-seduta lascia lo scarto nel
    gruppo che concorre alla soglia, quindi un guasto non viene mai scusato per
    errore. L'errore possibile e' un falso allarme, non un falso silenzio.
    """
    assert is_regular_session_time(datetime(2026, 9, 7, 15, 30, tzinfo=timezone.utc)) is True


# --- il flag viaggia sulla riga di scarto -----------------------------------


def test_la_riga_di_scarto_porta_la_seduta_del_momento_di_accodamento() -> None:
    # Accodata dal WebSocket alle 02:00Z, scartata alla campana: fuori seduta.
    item = _Item(
        "alpaca:1:AAPL",
        datetime(2026, 9, 9, 1, 55, tzinfo=timezone.utc),
        raw_ingested_at=datetime(2026, 9, 9, 2, 0, tzinfo=timezone.utc),
    )

    row = build_stale_drop_row(item, datetime(2026, 9, 9, 13, 35, tzinfo=timezone.utc))

    assert row["enqueued_off_session"] is True


def test_un_outage_a_mercato_aperto_resta_in_seduta_qualunque_cosa_segua() -> None:
    """Criterio di accettazione della deroga: l'outage 09/09 15-16Z deve allertare."""
    item = _Item(
        "alpaca:2:NVDA",
        datetime(2026, 9, 9, 15, 0, tzinfo=timezone.utc),
        raw_ingested_at=datetime(2026, 9, 9, 15, 5, tzinfo=timezone.utc),
    )

    # Scartata a mercato ormai chiuso: e' il momento di accodamento che decide.
    row = build_stale_drop_row(item, datetime(2026, 9, 9, 21, 0, tzinfo=timezone.utc))

    assert row["enqueued_off_session"] is False


def test_senza_raw_ingested_at_la_seduta_e_quella_del_momento_dello_scarto() -> None:
    # `build_news_discard_row` gia' sostituisce `now` a un raw_ingested_at
    # mancante: il flag deve restare coerente con il timestamp che finisce in riga.
    item = _Item("alpaca:3:MSFT", datetime(2026, 9, 9, 10, 0, tzinfo=timezone.utc))
    now = datetime(2026, 9, 9, 15, 30, tzinfo=timezone.utc)

    row = build_stale_drop_row(item, now)

    assert row["raw_ingested_at"] == now
    assert row["enqueued_off_session"] is False


def test_ogni_riga_di_scarto_porta_il_flag_non_solo_le_stale() -> None:
    # Il writer di pg_store e' uno solo: se il campo manca su un motivo, la
    # INSERT lo trova assente proprio quando serve.
    item = _Item(
        "alpaca:4:TSLA",
        datetime(2026, 9, 9, 3, 0, tzinfo=timezone.utc),
        raw_ingested_at=datetime(2026, 9, 9, 3, 5, tzinfo=timezone.utc),
    )

    row = build_news_discard_row(item, reason="duplicate_id", stage="ingestion")

    assert row["enqueued_off_session"] is True


def test_il_flag_non_dipende_da_quanto_e_rimasta_in_coda() -> None:
    accodata = datetime(2026, 9, 9, 14, 0, tzinfo=timezone.utc)
    item = _Item("alpaca:5:AMD", accodata - timedelta(hours=5), raw_ingested_at=accodata)

    subito = build_stale_drop_row(item, accodata + timedelta(minutes=1))
    tardi = build_stale_drop_row(item, accodata + timedelta(days=2))

    assert subito["enqueued_off_session"] == tardi["enqueued_off_session"] is False
