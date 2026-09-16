"""Test sulle funzioni pure della misura di eseguibilita' pre-market (#608).

Coprono i tre punti dove la misura puo' mentire in silenzio:
  - l'inferenza clusterizzata per giornata (una giornata rumorosa con molti
    eventi non deve dominare la media, e il `t` va sugli errori standard FRA
    giornate);
  - `ultimo_prezzo_entro`, che non deve mai pescare un prezzo del giorno prima;
  - la regola del verdetto, che deve applicare la soglia dichiarata alla
    lettera e far vincere `INSUFFICIENT_N` su tutto il resto.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

import scripts.measure_608_premarket_feasibility as m

ET = ZoneInfo("America/New_York")


# --------------------------------------------------------------------------- #
# media_t: l'unita' di inferenza e' la giornata
# --------------------------------------------------------------------------- #


def test_media_t_pesa_le_giornate_non_gli_eventi():
    """Una giornata con 100 eventi pesa quanto una con 1: e' la regola di #606."""
    per_giorno = {
        date(2026, 7, 1): [0.10] * 100,
        date(2026, 7, 2): [0.00],
        date(2026, 7, 3): [0.00],
        date(2026, 7, 6): [0.00],
    }
    out = m.media_t(per_giorno)
    assert out["n_giornate"] == 4
    assert out["n_eventi"] == 103
    # media delle medie giornaliere = (0.10 + 0 + 0 + 0)/4 = 0.025 = 250 bp
    assert out["media_bp"] == pytest.approx(250.0)


def test_media_t_pubblica_effetto_rilevabile_a_t3():
    per_giorno = {
        date(2026, 7, d): [v, v + 0.001]
        for d, v in zip((1, 2, 3, 6, 7), (0.001, 0.004, -0.002, 0.003, 0.000))
    }
    out = m.media_t(per_giorno)
    assert out["effetto_rilevabile_a_t3_bp"] >= 0.0
    # la soglia di rilevabilita' e' 3x l'errore standard: coerente col t
    assert out["media_bp"] / out["effetto_rilevabile_a_t3_bp"] * 3 == pytest.approx(
        out["t"]
    )


def test_media_t_con_una_sola_giornata_non_inventa_un_t():
    out = m.media_t({date(2026, 7, 1): [0.01, 0.02]})
    assert out["n_giornate"] == 1
    assert "t" not in out
    assert "media_bp" not in out


def test_media_t_conta_le_giornate_positive():
    per_giorno = {
        date(2026, 7, 1): [0.01],
        date(2026, 7, 2): [-0.01],
        date(2026, 7, 3): [0.02],
    }
    assert m.media_t(per_giorno)["giornate_positive"] == 2


# --------------------------------------------------------------------------- #
# ultimo_prezzo_entro: mai un prezzo di un altro giorno
# --------------------------------------------------------------------------- #


def _barra(ts: datetime, close: float) -> dict:
    return {
        "ts": ts,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 100.0,
        "trades": 1.0,
        "vwap": close,
    }


def test_ultimo_prezzo_entro_prende_l_ultima_barra_utile():
    d = date(2026, 7, 8)
    barre = [
        _barra(datetime.combine(d, time(6, 58), tzinfo=ET), 10.0),
        _barra(datetime.combine(d, time(6, 59), tzinfo=ET), 11.0),
        _barra(datetime.combine(d, time(7, 5), tzinfo=ET), 99.0),
    ]
    limite = datetime.combine(d, time(7, 0), tzinfo=ET)
    assert m.ultimo_prezzo_entro(barre, limite) == 11.0


def test_ultimo_prezzo_entro_non_pesca_il_giorno_prima():
    """Senza scambi nella fascia il risultato e' None, non il close di ieri.

    E' la differenza fra «non eseguibile» e «eseguibile a un prezzo stantio»:
    restituire il prezzo del giorno prima renderebbe la misura ottimista
    esattamente sui casi in cui il pre-market e' vuoto.
    """
    ieri = date(2026, 7, 7)
    oggi = date(2026, 7, 8)
    barre = [_barra(datetime.combine(ieri, time(15, 59), tzinfo=ET), 50.0)]
    limite = datetime.combine(oggi, time(7, 0), tzinfo=ET)
    assert m.ultimo_prezzo_entro(barre, limite) is None


def test_ultimo_prezzo_entro_su_lista_vuota():
    assert m.ultimo_prezzo_entro([], datetime.now(ET)) is None


# --------------------------------------------------------------------------- #
# potenza
# --------------------------------------------------------------------------- #


def test_giornate_necessarie_scala_col_quadrato():
    """80 giornate bastano su 56 bp; su meta' dell'effetto ne servono 4 volte."""
    assert m.giornate_necessarie(m.LORDO_BP) == pytest.approx(m.GIORNATE_A_56BP)
    assert m.giornate_necessarie(m.LORDO_BP / 2) == pytest.approx(
        4 * m.GIORNATE_A_56BP
    )


def test_giornate_necessarie_su_effetto_non_positivo():
    assert m.giornate_necessarie(0.0) is None
    assert m.giornate_necessarie(-3.0) is None
    assert m.giornate_necessarie(None) is None


# --------------------------------------------------------------------------- #
# popolazione: seduta di reazione e troncamento dell'embargo
# --------------------------------------------------------------------------- #


def _sedute(giorni: list[date]) -> list[dict]:
    return [
        {
            "data": g,
            "apertura": datetime.combine(g, time(9, 30), tzinfo=ET),
            "chiusura": datetime.combine(g, time(16, 0), tzinfo=ET),
        }
        for g in giorni
    ]


def test_seduta_di_reazione_e_la_prima_che_apre_dopo():
    sedute = _sedute([date(2026, 7, 7), date(2026, 7, 8)])
    pubblicata = datetime.combine(date(2026, 7, 7), time(18, 0), tzinfo=ET)
    assert m.seduta_di_reazione(pubblicata, sedute)["data"] == date(2026, 7, 8)


def test_seduta_di_reazione_e_la_stessa_se_pubblicata_prima_dell_apertura():
    sedute = _sedute([date(2026, 7, 7), date(2026, 7, 8)])
    pubblicata = datetime.combine(date(2026, 7, 8), time(8, 0), tzinfo=ET)
    assert m.seduta_di_reazione(pubblicata, sedute)["data"] == date(2026, 7, 8)


def test_costruisci_popolazione_tronca_sull_embargo_e_dedupica():
    sedute = _sedute([date(2026, 7, 7), date(2026, 7, 8), date(2026, 7, 9)])
    taglio = datetime.combine(date(2026, 7, 9), time(0, 0), tzinfo=ET)
    pub = datetime.combine(date(2026, 7, 7), time(18, 0), tzinfo=ET)
    base = {"symbol": "NVDA", "score": 0.5, "published_at": pub}
    segnali = [
        # stessa (simbolo, seduta): vince il non-fallback anche se piu' vecchio
        {**base, "fallback": True, "generated_at": pub + timedelta(hours=3)},
        {**base, "fallback": False, "generated_at": pub + timedelta(hours=1)},
        # seduta oltre il taglio: scartato, non incluso a meta'
        {
            "symbol": "AAPL",
            "score": 0.5,
            "fallback": False,
            "published_at": datetime.combine(date(2026, 7, 8), time(18, 0), tzinfo=ET),
            "generated_at": datetime.combine(date(2026, 7, 8), time(19, 0), tzinfo=ET),
        },
    ]
    scelti, scarti = m.costruisci_popolazione(segnali, sedute, taglio)
    assert len(scelti) == 1
    assert scelti[0]["symbol"] == "NVDA"
    assert scelti[0]["fallback"] is False
    assert scarti["oltre_taglio_embargo"] == 1
    assert scarti["senza_seduta_di_reazione"] == 0


# --------------------------------------------------------------------------- #
# verdetto: la soglia dichiarata, applicata alla lettera
# --------------------------------------------------------------------------- #


def _risultato(residuo_bp: float, t3_bp: float, spread_bp: float = 8.0) -> dict:
    ore = ["07:00", "08:00", "09:00", "09:29"]
    finestre = ["06:55-07:00", "07:55-08:00", "08:55-09:00", "09:25-09:30"]
    fasce = ["04:00-07:00", "07:00-08:00", "08:00-09:00", "09:00-09:30"]
    return {
        "residuo": {
            "scorati": {
                ora: {
                    "media_bp": residuo_bp if ora == "07:00" else -50.0,
                    "t": 1.0,
                    "effetto_rilevabile_a_t3_bp": t3_bp,
                    "n_giornate": 40,
                    "n_eventi": 200,
                }
                for ora in ore
            }
        },
        "spread": {
            **{
                f: {"spread_rel_mediano_bp": spread_bp, "tocco_mediano_usd": 20_000.0}
                for f in finestre
            },
            "09:30-09:31": {
                "spread_rel_mediano_bp": spread_bp,
                "tocco_mediano_usd": 20_000.0,
            },
        },
        "liquidita": {f: {"quota_senza_scambi": 0.0} for f in fasce},
        "azionabilita": {ora: {"tutti": 200, "pubblicati": 200, "scorati": 200} for ora in ore},
    }


def test_verdetto_raccoglibile_sopra_la_soglia():
    # 40 bp lordi - 8 bp all-in = 32 bp > 18,7
    v = m.verdetto(_risultato(residuo_bp=40.0, t3_bp=10.0), [1000.0])
    assert v["esito"] == "RACCOGLIBILE"
    assert v["migliore"]["ora"] == "07:00"
    assert v["migliore"]["netto_bp"] == pytest.approx(32.0)


def test_verdetto_non_raccoglibile_appena_sotto_la_soglia():
    """Appena sotto e' sotto: la soglia non si sposta dopo aver visto il numero."""
    netto_voluto = m.SOGLIA_NETTO_BP - 0.5
    v = m.verdetto(_risultato(residuo_bp=netto_voluto + 8.0, t3_bp=10.0), [1000.0])
    assert v["esito"] == "NON_RACCOGLIBILE"
    assert v["migliore"]["netto_bp"] == pytest.approx(netto_voluto)


def test_insufficient_n_batte_raccoglibile():
    """Lordo sotto il proprio effetto rilevabile: nessun verdetto di merito."""
    v = m.verdetto(_risultato(residuo_bp=40.0, t3_bp=64.0), [1000.0])
    assert v["esito"] == "INSUFFICIENT_N"


def test_verdetto_usa_la_variante_azionabile_per_default():
    assert m.verdetto(_risultato(40.0, 10.0), [1000.0])["variante"] == "scorati"


def test_verdetto_segnala_la_size_oltre_il_tocco():
    ris = _risultato(residuo_bp=40.0, t3_bp=10.0)
    v = m.verdetto(ris, [50_000.0])  # size sopra i $20k di profondita' al tocco
    assert v["migliore"]["size_oltre_il_tocco"] is True
    v_piccola = m.verdetto(ris, [1_000.0])
    assert v_piccola["migliore"]["size_oltre_il_tocco"] is False


def test_soglia_dichiarata_e_un_terzo_del_lordo():
    """Il numero del §5 della pre-registrazione non deve derivare in silenzio."""
    assert m.LORDO_BP == pytest.approx(56.0)
    assert m.SOGLIA_NETTO_BP == pytest.approx(56.0 / 3.0)
    assert m.GIORNI_EMBARGO == 3
