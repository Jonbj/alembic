"""Digest Telegram operativo del cron alpha-miss (#287, P4).

Il vecchio digest era `head -c 3800` dello stdout della sessione: un muro
dipendente dal modello, troncato a un punto arbitrario. Il nuovo digest e'
renderizzato da codice deterministico da dossier, riga materializzata e
scoreboard: cinque righe, sempre le stesse, con DATA_INCOMPLETE esplicito al
posto dei numeri mancanti — mai inventati.
"""

from src.analysis.dossier.digest import render_digest_telegram


def _dossier():
    return {
        "schema_version": "3.1",
        "data": "2026-09-15",
        "mercato": {
            "mover_3pct": 7,
            "up": 5,
            "down": 2,
            "dispersione_sigma": 0.0213,
        },
    }


def _riga():
    return {
        "data": "2026-09-15",
        "tema": "rotazione su semis",
        "catturati": 2,
        "miss": {
            "NO_NEWS": 3,
            "THIN_NEUTRAL": 1,
            "WRONG_SIGN": 0,
            "FILTERED": 1,
            "OUT_OF_STRATEGY_SCOPE": 0,
        },
    }


def _scoreboard():
    return {
        "scoreboard": {
            "giorno": {"n": 27, "denominatore": 40},
            "s4_vs_200": {"cumulato": 123.4, "soglia": 200.0, "within": True},
        }
    }


def test_digest_completo_ha_esattamente_cinque_righe_leggibili():
    righe = render_digest_telegram(
        _dossier(), _riga(), esiti_findings=[
            {"finding_id": "F-004", "titolo": "ORCL mancato", "costo_usd": 132.0}
        ],
        scoreboard=_scoreboard(),
    )

    assert len(righe) == 5
    assert righe[0] == "🔎 Alpha-miss 2026-09-15: 7 mover (5↑ 2↓), dispersione σ 2.1%"
    assert righe[1] == "Miss totale 5 — prevalente NO_NEWS 3; catturati 2"
    assert righe[2] == "Tema: rotazione su semis"
    assert righe[3] == "Findings oggi: F-004 $132.00 (ORCL mancato)"
    assert righe[4] == "Carta: giorno 27/40 — S4 economico +123.40$ vs ±200$ (DENTRO)"


def test_digest_senza_findings_lo_dice_esplicitamente():
    righe = render_digest_telegram(
        _dossier(), _riga(), esiti_findings=[], scoreboard=_scoreboard()
    )

    assert righe[3] == "Findings oggi: nessuna segnalazione"


def test_digest_con_costo_null_lo_dichiara_non_stimato():
    righe = render_digest_telegram(
        _dossier(), _riga(), esiti_findings=[
            {"finding_id": "F-001", "titolo": "copertura", "costo_usd": None}
        ],
        scoreboard=_scoreboard(),
    )

    assert "F-001" in righe[3]
    assert "non stimato" in righe[3]


def test_dossier_mancante_non_produce_numeri_inventati():
    righe = render_digest_telegram(
        {}, _riga(), esiti_findings=[], scoreboard=_scoreboard()
    )

    assert "DATA_INCOMPLETE" in righe[0]


def test_riga_mancante_non_produce_numeri_inventati():
    righe = render_digest_telegram(
        _dossier(), None, esiti_findings=[], scoreboard=_scoreboard()
    )

    assert "DATA_INCOMPLETE" in righe[1]
    assert "DATA_INCOMPLETE" in righe[2]


def test_scoreboard_mancante_non_produce_numeri_inventati():
    righe = render_digest_telegram(
        _dossier(), _riga(), esiti_findings=[], scoreboard=None
    )

    assert "DATA_INCOMPLETE" in righe[4]


def test_la_causa_prevalente_e_deterministica_in_caso_di_pareggio():
    riga = _riga()
    # Pareggio NO_NEWS=3, FILTERED=3: vince il primo nell'ordine canonico.
    riga["miss"]["FILTERED"] = 3
    righe = render_digest_telegram(
        _dossier(), riga, esiti_findings=[], scoreboard=_scoreboard()
    )

    assert "prevalente NO_NEWS 3" in righe[1]