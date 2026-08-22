"""#246 Q1: `opportunity_v2` cablato alle barre intraday e al ciclo eleggibile.

Il bug: l'orchestratore passava `eligible_cycle_at: None` e `intraday_bars: []`
allo stimatore, che per costruzione restituiva `accessible_opportunity_usd =
None` su OGNI rialzo non detenuto. Il conteggio dei miss restava quindi quello
close-to-close — ORCL il 12/08 contabilizzato ~118$ invece dei ~7$ realmente
catturabili da un motore che opera in RTH.

Il fix ha due meta':
1. le barre 5Min e i cicli eleggibili si caricano PRIMA della stima (l'ordine
   dei blocchi in `costruisci_dossier` non e' cosmetico);
2. un candidato senza decisione collegata — tipicamente NO_NEWS, che non ha
   nessuna riga in `execution_decisions` — ricade sul primo ciclo da 15 minuti
   della seduta, marcato con `source: "session_open"` per non confondere un
   bound con una decisione osservata.
"""

from datetime import date, datetime, timezone

import scripts.alpha_miner_dossier as dossier


def _bar_5min(ora: str, prezzo: float) -> dict:
    return {
        "timestamp": datetime.fromisoformat(f"2026-08-12T{ora}+00:00"),
        "open": prezzo, "high": prezzo, "low": prezzo, "close": prezzo,
    }


def test_cicli_eleggibili_prende_il_primo_tick_time_per_simbolo():
    eventi = [
        {"symbol": "ORCL", "eligible_cycle_at": datetime(2026, 8, 12, 17, 7, tzinfo=timezone.utc)},
        {"symbol": "ORCL", "eligible_cycle_at": datetime(2026, 8, 12, 16, 37, tzinfo=timezone.utc)},
        {"symbol": "NVDA", "eligible_cycle_at": None},
    ]
    cicli = dossier._cicli_eleggibili(eventi, date(2026, 8, 12))
    assert cicli["ORCL"]["at"] == datetime(2026, 8, 12, 16, 37, tzinfo=timezone.utc)
    assert cicli["ORCL"]["source"] == "execution_decisions.tick_time"
    # Un evento senza tick_time non inventa un ciclo: il simbolo non c'e'.
    assert "NVDA" not in cicli


def test_candidato_no_news_ricade_sul_primo_ciclo_della_seduta():
    """14:07 UTC: il beat portfolio-cycle gira a :07/:22/:37/:52 da 14 a 21 UTC."""
    ciclo = dossier._ciclo_apertura(date(2026, 8, 12))
    assert ciclo["at"] == datetime(2026, 8, 12, 14, 7, tzinfo=timezone.utc)
    assert ciclo["source"] == "session_open"


def test_opportunity_v2_prezza_l_entry_sulle_barre_intraday():
    """Con barre e ciclo cablati, `accessible` non e' piu' None e vale una
    frazione del gross close-to-close."""
    candidato = {"symbol": "ORCL", "return": 0.0536, "in_portafoglio": False}
    barre = {"ORCL": {"open": 240.0, "high": 246.0, "low": 239.0,
                      "close": 245.0, "close_prec": 232.5}}
    barre_intraday = {"ORCL": [_bar_5min("13:35:00", 241.0),
                              _bar_5min("14:10:00", 244.25),
                              _bar_5min("15:00:00", 244.8)]}
    est = dossier._opportunity_v2(
        candidato, barre, date(2026, 8, 12), barre_intraday, {}
    )
    assert est["accessible_opportunity_usd"] is not None
    assert est["entry"]["price"] == 244.25
    assert est["entry"]["eligible_cycle_source"] == "session_open"
    assert est["accessible_opportunity_usd"] < est["gross_opportunity_usd"] / 10
    # Il bar_timestamp finisce nel JSON del dossier: deve essere serializzabile.
    assert isinstance(est["entry"]["bar_timestamp"], str)


def test_opportunity_v2_usa_il_tick_time_quando_il_candidato_ne_ha_uno():
    candidato = {"symbol": "ORCL", "return": 0.0536, "in_portafoglio": False}
    barre = {"ORCL": {"open": 240.0, "high": 246.0, "low": 239.0,
                      "close": 245.0, "close_prec": 232.5}}
    barre_intraday = {"ORCL": [_bar_5min("14:10:00", 244.25),
                              _bar_5min("17:10:00", 244.9)]}
    cicli = {"ORCL": {"at": datetime(2026, 8, 12, 17, 7, tzinfo=timezone.utc),
                      "source": "execution_decisions.tick_time"}}
    est = dossier._opportunity_v2(
        candidato, barre, date(2026, 8, 12), barre_intraday, cicli
    )
    assert est["entry"]["price"] == 244.9  # il bar delle 14:10 precede il ciclo
    assert est["entry"]["eligible_cycle_source"] == "execution_decisions.tick_time"


def test_senza_barre_intraday_accessible_resta_none_con_missingness():
    """La mancanza resta una mancanza dichiarata, mai un gross travestito."""
    candidato = {"symbol": "ORCL", "return": 0.0536, "in_portafoglio": False}
    barre = {"ORCL": {"open": 240.0, "high": 246.0, "low": 239.0,
                      "close": 245.0, "close_prec": 232.5}}
    est = dossier._opportunity_v2(candidato, barre, date(2026, 8, 12), {}, {})
    assert est["accessible_opportunity_usd"] is None
    assert est["missingness"]
    assert est["gross_opportunity_usd"] is not None


def test_la_serie_legacy_resta_affiancata_nel_dossier():
    candidato = {"symbol": "ORCL", "return": 0.0536, "in_portafoglio": False}
    barre = {"ORCL": {"open": 240.0, "high": 246.0, "low": 239.0,
                      "close": 245.0, "close_prec": 232.5}}
    barre_intraday = {"ORCL": [_bar_5min("14:10:00", 244.25)]}
    est = dossier._opportunity_v2(
        candidato, barre, date(2026, 8, 12), barre_intraday, {}
    )
    assert est["legacy"]["costo_usd"] == est["gross_opportunity_usd"]
    assert est["legacy"]["letta_dalla_sintesi_28_09"] is False
