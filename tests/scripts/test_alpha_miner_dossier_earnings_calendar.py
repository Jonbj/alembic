"""#507 — cecita' del calendario earnings nel dossier (F-063).

Il difetto: `FMP_API_KEY` non arrivava al dossier quando girava da cron, e il
ramo "credenziali assenti" e il ramo "chiamata HTTP fallita" emettevano lo
stesso marker `earnings_calendar_unavailable`. Quattro sedute di un difetto di
configurazione sono quindi risultate indistinguibili da un problema di provider,
senza nessuna allerta.

Qui si verifica la separazione dei due marker, il blocco `calendario_earnings`
che registra status e streak, e l'inferenza della cecita' sui dossier storici
(pre-blocco) dalla qualifica `giorno_di_earnings=None` degli intenti.

Misura read-only: nessun ordine cambiato, nessuna soglia di strategia toccata.
"""

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import scripts.alpha_miner_dossier as dossier


def test_credenziali_fmp_assenti_marca_no_credentials_non_generico():
    with patch.dict(
        "os.environ",
        {"FMP_API_KEY": "", "ALPACA_API_KEY": "", "ALPACA_SECRET_KEY": ""},
    ):
        out = dossier._corporate_calendar(date(2026, 9, 2), ["NVDA"])

    assert "earnings_calendar_no_credentials" in out["missingness"]
    # il marker conflato pre-#507 non deve piu' esistere: un difetto di
    # configurazione non puo' passare per un problema di provider
    assert "earnings_calendar_unavailable" not in out["missingness"]


def test_fetch_fmp_fallito_marca_fetch_failed():
    def _boom(*args, **kwargs):
        raise RuntimeError("timeout provider")

    with (
        patch.dict("os.environ", {"FMP_API_KEY": "k", "ALPACA_API_KEY": "", "ALPACA_SECRET_KEY": ""}),
        patch("httpx.get", side_effect=_boom),
    ):
        out = dossier._corporate_calendar(date(2026, 9, 2), ["NVDA"])

    assert "earnings_calendar_fetch_failed" in out["missingness"]
    assert "earnings_calendar_no_credentials" not in out["missingness"]


def test_fetch_fmp_riuscito_registra_la_fonte():
    response = SimpleNamespace(
        json=lambda: [
            {"symbol": "NVDA", "date": "2026-08-26", "time": "amc"},
            {"symbol": "ZZZZ", "date": "2026-08-26"},
        ],
        raise_for_status=lambda: None,
    )
    with (
        patch.dict("os.environ", {"FMP_API_KEY": "k", "ALPACA_API_KEY": "", "ALPACA_SECRET_KEY": ""}),
        patch("httpx.get", return_value=response),
    ):
        out = dossier._corporate_calendar(date(2026, 8, 26), ["NVDA"])

    assert out["sources_succeeded"] == ["FMP earnings-calendar"]
    # solo i simboli dell'universo entrano negli eventi
    assert [e["symbol"] for e in out["events"]] == ["NVDA"]


def test_earnings_symbols_restano_none_con_i_marker_separati():
    """ UNKNOWN, non False per difetto di fonte (#335), con entrambi i nuovi marker."""
    for marker in ("earnings_calendar_no_credentials", "earnings_calendar_fetch_failed"):
        cal = {
            "events": [{"symbol": "MSFT", "event_type": "dividend"}],
            "missingness": [marker],
            "complete": False,
        }
        assert dossier._earnings_symbols_from_calendar(cal) is None


# --- inferenza della cecita' sui dossier gia' scritti ----------------------


def _dossier_storico(cieco: bool) -> dict:
    valore = None if cieco else False
    return {
        "schema_version": "2.8",
        "intenti_ingresso_s4": [
            {"symbol": "NVDA", "giorno_di_earnings": valore}
        ],
    }


def test_cecita_inferita_dagli_intenti_nei_dossier_pre_blocco():
    assert dossier._calendario_earnings_cieco(_dossier_storico(cieco=True)) is True
    assert dossier._calendario_earnings_cieco(_dossier_storico(cieco=False)) is False


def test_cecita_legge_il_blocco_nei_dossier_post_507():
    con_blocco = {"calendario_earnings": {"status": "UNKNOWN"}, "intenti_ingresso_s4": []}
    assert dossier._calendario_earnings_cieco(con_blocco) is True
    con_blocco = {"calendario_earnings": {"status": "OBSERVED"}, "intenti_ingresso_s4": []}
    assert dossier._calendario_earnings_cieco(con_blocco) is False


def test_cecita_indeterminabile_senza_blocco_né_intenti():
    assert dossier._calendario_earnings_cieco({"intenti_ingresso_s4": []}) is None


# --- streak delle sedute consecutive cieche -------------------------------


def _scrivi_dossier(dir_dossier: Path, seduta: str, payload: dict) -> None:
    (dir_dossier / f"{seduta}.json").write_text(json.dumps(payload))


def test_streak_conta_le_sedute_consecutive_cieche_inclusa_oggi(tmp_path: Path):
    sedute = ["2026-08-31", "2026-09-01", "2026-09-02", "2026-09-03"]
    for seduta in sedute[:-1]:
        _scrivi_dossier(tmp_path, seduta, _dossier_storico(cieco=True))

    streak = dossier._streak_calendario_earnings_sconosciuto(
        cieca_oggi=True, sedute=sedute, dossier_dir=tmp_path
    )
    assert streak == 4


def test_streak_si_ferma_sulla_prima_seduta_sana(tmp_path: Path):
    sedute = ["2026-08-27", "2026-08-31", "2026-09-01", "2026-09-02"]
    _scrivi_dossier(tmp_path, "2026-09-01", _dossier_storico(cieco=True))
    _scrivi_dossier(tmp_path, "2026-08-31", _dossier_storico(cieco=False))

    streak = dossier._streak_calendario_earnings_sconosciuto(
        cieca_oggi=True, sedute=sedute, dossier_dir=tmp_path
    )
    # 09-02 oggi cieca + 09-01 cieca; 08-31 sana interrompe
    assert streak == 2


def test_streak_si_ferma_su_seduta_senza_dossier(tmp_path: Path):
    # 09-01 senza file (cron non girato): la consecutivita' non e' rivendicabile,
    # anche se la seduta piu' vecchia era effettivamente cieca
    sedute = ["2026-08-27", "2026-08-31", "2026-09-01"]
    _scrivi_dossier(tmp_path, "2026-08-27", _dossier_storico(cieco=True))

    streak = dossier._streak_calendario_earnings_sconosciuto(
        cieca_oggi=True, sedute=sedute, dossier_dir=tmp_path
    )
    assert streak == 1


def test_streak_zero_se_oggi_osservato(tmp_path: Path):
    sedute = ["2026-08-31", "2026-09-01"]
    _scrivi_dossier(tmp_path, "2026-08-31", _dossier_storico(cieco=True))

    streak = dossier._streak_calendario_earnings_sconosciuto(
        cieca_oggi=False, sedute=sedute, dossier_dir=tmp_path
    )
    assert streak == 0


def test_streak_none_se_il_calendario_di_borsa_non_risponde(tmp_path: Path):
    streak = dossier._streak_calendario_earnings_sconosciuto(
        cieca_oggi=True, sedute=[], dossier_dir=tmp_path
    )
    assert streak is None


# --- blocco persistito nel dossier -----------------------------------------


def test_blocco_calendario_earnings_dichiarato_con_marker_oggi_cieco(tmp_path: Path):
    cal = {
        "events": [],
        "sources_succeeded": ["Alpaca Corporate Actions API"],
        "complete": False,
        "missingness": ["earnings_calendar_no_credentials"],
    }
    blocco = dossier._blocco_calendario_earnings(
        cal, sedute=["2026-09-02"], dossier_dir=tmp_path
    )
    assert blocco["status"] == "UNKNOWN"
    assert blocco["missingness"] == ["earnings_calendar_no_credentials"]
    # la fonte Alpaca non e' la fonte earnings: non entra nei sources del blocco
    assert blocco["sources_succeeded"] == []
    assert blocco["streak_sedute_consecutive_unknown"] == 1


def test_blocco_calendario_earnings_osservato_con_fonte_fmp(tmp_path: Path):
    cal = {
        "events": [{"symbol": "NVDA", "event_type": "earnings"}],
        "sources_succeeded": ["FMP earnings-calendar", "Alpaca Corporate Actions API"],
        "complete": True,
        "missingness": [],
    }
    blocco = dossier._blocco_calendario_earnings(
        cal, sedute=["2026-08-26", "2026-08-27"], dossier_dir=tmp_path
    )
    assert blocco["status"] == "OBSERVED"
    assert blocco["sources_succeeded"] == ["FMP earnings-calendar"]
    assert blocco["streak_sedute_consecutive_unknown"] == 0


# --- simboli marcati, per la misura del residuo (#507 step 5) ----------------


def test_blocco_persiste_i_simboli_flaggati_osservati(tmp_path: Path):
    # step 5: la recall si conta sulle coppie (simbolo, seduta), quindi
    # l'insieme dei True dev'essere osservabile a livello seduta, non solo
    # sugli intenti (che coprono solo i simboli con un intento quel giorno)
    cal = {
        "events": [
            {"symbol": "NVDA", "event_type": "earnings"},
            {"symbol": "MSFT", "event_type": "dividend"},
        ],
        "sources_succeeded": ["FMP earnings-calendar"],
        "complete": True,
        "missingness": [],
    }
    blocco = dossier._blocco_calendario_earnings(
        cal, sedute=["2026-08-26"], dossier_dir=tmp_path
    )
    assert blocco["simboli_flaggati"] == ["NVDA"]


def test_blocco_simboli_flaggati_lista_vuota_se_osservato_senza_eventi(tmp_path: Path):
    # fonte risponde, nessun earnings watchlist: e' False onesto, non UNKNOWN
    blocco = dossier._blocco_calendario_earnings(
        {"events": [], "sources_succeeded": ["FMP earnings-calendar"], "missingness": []},
        sedute=["2026-09-02"],
        dossier_dir=tmp_path,
    )
    assert blocco["simboli_flaggati"] == []


def test_blocco_simboli_flaggati_none_se_unknown(tmp_path: Path):
    blocco = dossier._blocco_calendario_earnings(
        {"events": [], "missingness": ["earnings_calendar_no_credentials"]},
        sedute=["2026-09-02"],
        dossier_dir=tmp_path,
    )
    # None, non []: una seduta cieca non azzera i simboli marcati, li rende
    # non misurati (stesso contratto None/non-False di #335)
    assert blocco["simboli_flaggati"] is None


def test_blocco_calendario_earnings_senza_fetch_remoto(tmp_path: Path):
    blocco = dossier._blocco_calendario_earnings(
        None, sedute=["2026-08-19"], dossier_dir=tmp_path
    )
    assert blocco["status"] == "UNKNOWN"
    assert blocco["missingness"] == ["earnings_calendar_not_fetched"]