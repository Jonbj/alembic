"""Regressione #467: la misura dell'IC deve applicare la regola del ranker.

`compute_s4_ic.py` riduceva a un'osservazione per simbolo-giorno tenendo
l'ULTIMO segnale per solo orario. Il ranker di produzione
(`_FETCH_SIGNALS_FOR_CYCLE`, `src/store/pg_store.py`) ordina invece per
`fallback_used ASC, generated_at DESC`: un fallback FinBERT arrivato dopo un
ensemble NON lo sovrascrive.

La differenza non e' cosmetica: `docs/evidence/s4_ic.json` e' l'artefatto su cui
si giudica se S4 abbia segnale, e con la riduzione ingenua descriveva una regola
che il sistema non applica (403/3190 simbolo-giorni divergenti, 12,6%).

Questi test sono la guardia che mancava sia alla #169 sia alla #467: legano la
misura alla funzione di produzione invece di ricontrollare a mano un ordinamento
riscritto due volte.

#601 aggiunge la guardia sul CONTEGGIO del criterio: `min_giorni` dichiara
sedute pulite (post-fix #467), quindi `n_corrente` deve contare solo la coda
dalla data registrata in `serie_valida_dal` nel criterio YAML — non la serie
intera, che al 2026-09-15 valeva 64 giorni di cui 60 prodotti da una riduzione
che il sistema non applica. I test puntano `_esito()` direttamente perche' e'
li' che la Decision of Done della #601 chiede la copertura.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from scripts import compute_s4_ic
from scripts.compute_s4_ic import QUERY, _esito, _sintesi, parse_righe, riduci_a_simbolo_giorno
from scripts.measure_169_dedup_rules import scelta_produzione


def _riga(
    giorno: str,
    symbol: str,
    score: float,
    fallback: bool,
    ora: str,
    fwd1: float = 0.01,
    fwd3: str | float = "",
    fwd5: str | float = "",
) -> str:
    """Una riga come la emette `psql -t -A -F '|'`."""
    epoch = datetime.fromisoformat(f"{giorno}T{ora}+00:00").timestamp()
    return "|".join(
        [giorno, symbol, str(score), "t" if fallback else "f", str(epoch),
         str(fwd1), str(fwd3), str(fwd5)]
    )


def test_un_fallback_piu_recente_non_sovrascrive_un_ensemble():
    """Il difetto della #467, nella sua forma minima."""
    stdout = "\n".join([
        _riga("2026-09-01", "AAPL", 0.42, fallback=False, ora="10:00:00"),
        _riga("2026-09-01", "AAPL", 0.05, fallback=True, ora="15:00:00"),
    ])

    ridotto = riduci_a_simbolo_giorno(parse_righe(stdout))

    scelto = ridotto[("2026-09-01", "AAPL")]
    assert scelto["score"] == 0.42, "ha vinto il fallback piu' recente: regola del ranker non applicata"
    assert scelto["fallback"] is False


def test_a_parita_di_stato_vince_il_piu_recente():
    """La preferenza ensemble non deve rovesciare il tie-break sulla recenza."""
    stdout = "\n".join([
        _riga("2026-09-01", "MSFT", 0.11, fallback=False, ora="09:30:00"),
        _riga("2026-09-01", "MSFT", 0.33, fallback=False, ora="14:00:00"),
    ])

    ridotto = riduci_a_simbolo_giorno(parse_righe(stdout))

    assert ridotto[("2026-09-01", "MSFT")]["score"] == 0.33


def test_il_forward_return_e_quello_del_segnale_scelto():
    """Punto 2 della #467: lo stesso difetto sul lato del target.

    Il rendimento futuro va letto sulla riga che il ranker sceglie, non su
    quella che arriva per ultima.
    """
    stdout = "\n".join([
        _riga("2026-09-01", "NVDA", 0.50, fallback=False, ora="10:00:00", fwd1=0.031),
        _riga("2026-09-01", "NVDA", 0.02, fallback=True, ora="16:00:00", fwd1=-0.019),
    ])

    scelto = riduci_a_simbolo_giorno(parse_righe(stdout))[("2026-09-01", "NVDA")]

    assert scelto[1] == 0.031


def test_la_riduzione_coincide_con_la_scelta_di_produzione():
    """L'invariante che lega la misura al ranker.

    Non riverifica l'ordinamento a mano: confronta con `scelta_produzione()`,
    la funzione gia' testata in PR #460 contro `_FETCH_SIGNALS_FOR_CYCLE`. Se un
    domani la regola di produzione cambia, e' questa asserzione a rompersi.
    """
    righe_raw = [
        _riga("2026-09-01", "TSLA", 0.40, fallback=True, ora="09:00:00"),
        _riga("2026-09-01", "TSLA", 0.10, fallback=False, ora="11:00:00"),
        _riga("2026-09-01", "TSLA", 0.90, fallback=True, ora="17:00:00"),
        _riga("2026-09-01", "AMD", 0.20, fallback=False, ora="09:00:00"),
        _riga("2026-09-01", "AMD", 0.60, fallback=False, ora="12:00:00"),
        _riga("2026-09-02", "TSLA", 0.15, fallback=True, ora="10:00:00"),
    ]
    righe = parse_righe("\n".join(righe_raw))

    ridotto = riduci_a_simbolo_giorno(righe)

    gruppi: dict[tuple[str, str], list[dict]] = {}
    for r in righe:
        gruppi.setdefault((r["giorno"], r["symbol"]), []).append(r)
    for chiave, gruppo in gruppi.items():
        assert ridotto[chiave]["score"] == scelta_produzione(gruppo)["score"]


def test_righe_senza_forward_return_a_1_giorno_sono_scartate():
    """Senza target la riga non e' un'osservazione: non deve entrare nel campione."""
    stdout = "\n".join([
        _riga("2026-09-01", "INTC", 0.31, fallback=False, ora="10:00:00", fwd1=""),
        _riga("2026-09-01", "GOOG", 0.22, fallback=False, ora="10:00:00", fwd1=0.004),
    ])

    ridotto = riduci_a_simbolo_giorno(parse_righe(stdout))

    assert ("2026-09-01", "INTC") not in ridotto
    assert ("2026-09-01", "GOOG") in ridotto


def test_gli_orizzonti_lunghi_mancanti_restano_none():
    """3g/5g assenti sono missing, non zero."""
    stdout = _riga("2026-09-01", "META", 0.28, fallback=False, ora="10:00:00",
                   fwd1=0.002, fwd3="", fwd5=0.007)

    scelto = riduci_a_simbolo_giorno(parse_righe(stdout))[("2026-09-01", "META")]

    assert scelto[3] is None
    assert scelto[5] == 0.007


def test_la_query_espone_generated_at():
    """La regola di produzione ha bisogno dell'orario: senza, non e' applicabile."""
    assert "generated_at" in QUERY
    assert "fallback_used" in QUERY


# ─── #601: il criterio conta le sedute pulite, non la serie intera ──────────

_PRE = ["2026-09-0%d" % g for g in range(1, 8)]  # 09-01 .. 09-07: prima del taglio
_POST = ["2026-09-08", "2026-09-09", "2026-09-10", "2026-09-11"]


def _serie(ics_per_giorno: dict[str, float]) -> list[tuple[str, float, int]]:
    """Serie giornaliera nello stesso formato di `_serie_ic`: (giorno, ic, n)."""
    return [(g, ic, 12) for g, ic in sorted(ics_per_giorno.items())]


@pytest.fixture
def criterio_registrato(tmp_path, monkeypatch):
    """Criterio minimo con la data di taglio del #467, come il file vero."""
    f = tmp_path / "s4_kill_criterion.yaml"
    f.write_text(
        "min_giorni: 213\n"
        'serie_valida_dal: "2026-09-08"\n'
        "significativo_a_t: 3.0\n"
        "max_ic_rilevabile_a_t: 0.05\n"
    )
    monkeypatch.setattr(compute_s4_ic, "CRITERION_FILE", f)
    return f


def test_serie_tutta_pre_taglio_conta_zero(criterio_registrato):
    """DoD 4: nessuna seduta valida -> INSUFFICIENT_N con n_corrente = 0.

    Sono pur sempre giorni pubblicati (n_giorni_totali), ma non concorrono al
    conteggio che autorizza una decisione.
    """
    serie = _serie({g: -0.30 for g in _PRE})

    esito = _esito({"tutti": {"1g": _sintesi(serie)}}, serie)

    assert esito["esito"] == "INSUFFICIENT_N"
    assert esito["n_corrente"] == 0
    assert esito["n_giorni_totali"] == len(_PRE)
    assert esito["serie_valida_dal"] == "2026-09-08"


def test_serie_mista_conta_solo_la_coda(criterio_registrato):
    """DoD 4: la coda post-taglio decide il conteggio, la serie intera resta pubblicata."""
    serie = _serie({**{g: -0.30 for g in _PRE}, **{g: 0.10 for g in _POST}})

    esito = _esito({"tutti": {"1g": _sintesi(serie)}}, serie)

    assert esito["n_corrente"] == len(_POST)
    assert esito["n_giorni_totali"] == len(_PRE) + len(_POST)
    # Le statistiche del blocco criterio sono quelle della coda, non della miscela.
    assert esito["ic_medio"] == pytest.approx(0.10)


def test_la_decisione_non_passa_mai_per_i_giorni_contaminati(tmp_path, monkeypatch):
    """Il caso che la #601 esiste per impedire.

    Soglia bassa (3 sedute) e una serie pre-taglio cosi' negativa che, contata
    tutta, il criterio emetterebbe FAIL. Contando solo la coda pulita non c'e'
    campione: nessuna decisione puo' appoggiarsi sulle sedute pre-#467.
    """
    f = tmp_path / "s4_kill_criterion.yaml"
    f.write_text(
        "min_giorni: 3\n"
        'serie_valida_dal: "2026-09-08"\n'
        "significativo_a_t: 2.0\n"
    )
    monkeypatch.setattr(compute_s4_ic, "CRITERION_FILE", f)

    solo_pre = _serie({g: -0.30 for g in _PRE})
    esito_pre = _esito({"tutti": {"1g": _sintesi(solo_pre)}}, solo_pre)
    assert esito_pre["esito"] == "INSUFFICIENT_N"
    assert esito_pre["n_corrente"] == 0

    mista = _serie({**{g: -0.30 for g in _PRE},
                    **{"2026-09-08": 0.10, "2026-09-09": 0.12,
                       "2026-09-10": 0.08, "2026-09-11": 0.10}})
    esito_misto = _esito({"tutti": {"1g": _sintesi(mista)}}, mista)
    # 4 sedute valide >= 3 richieste, coda coerente e positiva: decisione PASS
    # letta SOLO sulla coda (ic_medio 0.10, non la media contaminata con i -0.30).
    assert esito_misto["esito"] == "PASS"
    assert esito_misto["n_corrente"] == 4
    assert esito_misto["ic_medio"] == pytest.approx(0.10)


def test_senza_data_di_taglio_il_criterio_non_e_valutabile(tmp_path, monkeypatch):
    """La chiave obbligatoria manca -> NO_CRITERION, mai il conteggio sulla serie intera.

    Cadere silenziosamente indietro alla definizione vecchia (n = giorni totali)
    e' esattamente il difetto che la #601 corregge: deve essere visibile.
    """
    f = tmp_path / "s4_kill_criterion.yaml"
    f.write_text("min_giorni: 213\nsignificativo_a_t: 3.0\n")
    monkeypatch.setattr(compute_s4_ic, "CRITERION_FILE", f)

    serie = _serie({g: 0.10 for g in _PRE})

    esito = _esito({"tutti": {"1g": _sintesi(serie)}}, serie)

    assert esito["esito"] == "NO_CRITERION"
    assert esito["criterio_registrato"] is False
    assert esito["serie_valida_dal"] is None


def test_la_data_non_quotata_fa_lo_stesso_conteggio(tmp_path, monkeypatch):
    """yaml.safe_load parse' `2026-09-08` nudo come date, quotata come str.

    Il criterio accetta entrambe: chi registra il file non deve dipendere
    dalla sintassi della data perche' il conteggio cambi.
    """
    f = tmp_path / "s4_kill_criterion.yaml"
    f.write_text("min_giorni: 213\nserie_valida_dal: 2026-09-08\n")
    monkeypatch.setattr(compute_s4_ic, "CRITERION_FILE", f)

    serie = _serie({**{g: -0.30 for g in _PRE}, **{g: 0.10 for g in _POST}})

    esito = _esito({"tutti": {"1g": _sintesi(serie)}}, serie)

    assert esito["serie_valida_dal"] == "2026-09-08"
    assert esito["n_corrente"] == len(_POST)


def test_la_config_reale_dichiara_la_data_di_taglio():
    """Guardia sulla serie pubblicata: senza `serie_valida_dal` il cron di domani
    pubblicherebbe di nuovo `n_corrente` = serie intera, cambiando definizione
    in silenzio (il pattern che la carta di osservazione vieta)."""
    criterio = compute_s4_ic._leggi_criterio()

    assert criterio is not None, (
        "config/s4_kill_criterion.yaml non e' piu' valutabile: manca min_giorni "
        "o serie_valida_dal"
    )
    dal = date.fromisoformat(criterio["serie_valida_dal"])
    assert dal <= date.today(), (
        "serie_valida_dal e' nel futuro: azzererebbe il conteggio senza che "
        "nessuna seduta pulita sia mai contata"
    )
