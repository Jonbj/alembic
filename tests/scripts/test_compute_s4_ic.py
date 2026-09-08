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
"""

from __future__ import annotations

from datetime import datetime

from scripts.compute_s4_ic import QUERY, parse_righe, riduci_a_simbolo_giorno
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
