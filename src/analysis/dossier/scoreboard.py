"""Scoreboard delle due domande di uscita della carta (#278, M3).

Modulo puro: riceve il risultato del P&L economico (``economic_pnl``) e le righe
del ledger di mercato (``market_daily.jsonl``), restituisce il blocco
descrittivo che la carta vuole vedere a meta' e fine finestra. Non decide nulla:
espone numeratore e denominatore di ogni domanda, e i segmenti di discontinuita'
#185/#191 come tratti separati (la carta impone di non mediare le deroghe
sull'intera finestra).

DOMANDE PRE-REGISTRATE (docs/evidence/OBSERVATION_CHARTER.md):

1. Esiste alpha nella news editoriale? Falsificazione: NO_NEWS dominante in
   >=60% dei giorni **e** P&L economico S4 dentro +-200$ -> no.
2. S1 ha un edge? Criterio: P&L economico S1 vs SPY, realizzato ignorato.

BENCHMARK SPY: SPY e' un rendimento (frazione), S1 e' dollari. Per confrontarli
senza una scelta di capitale arbitraria, lo scoreboard converte SPY in dollari
sulla **base di capitale che S1 aveva al mark del primo giorno** (capital_base
S1 = somma di mark_from*qty delle posizioni S1). E' una conversione deterministica
di un benchmark pubblico alla base di capitale reale di S1: strumentazione, non
taratura. Il rendimento SPY grezzo resta esposto accanto, cosi' l'operatore puo'
giudicare anche senza la conversione.

Allineamento del primo giorno: il P&L economico di S1 vale 0 a ``window_start``
per definizione (mark dal close del primo giorno); il rendimento cumulato SPY
parte quindi dal giorno *successivo* a ``window_start`` (intervallo aperto a
sinistra), cosi' la serie SPY in dollari parte dallo stesso livello (zero) di
S1. Includere il rendimento di ``window_start`` significherebbe confrontare
"variazione dal close precedente" (SPY) con "variazione dal close di
window_start" (S1) -- due baseline diverse, off-by-one temporale.

DISCONTINUITA' #185 / #191 (charter, sezione "Discontinuita' nella serie
osservata"):

* #185 -- PR #188 (rebalance_frequency) merged 2026-08-07 10:42 CEST, prima
  dell'apertura US (15:30 CEST): il 2026-08-07 e' il **primo giorno post** per
  S1. pre = giorni < 2026-08-07, post = giorni >= 2026-08-07.
* #191 -- la carta dice "dal 2026-08-03 al 2026-08-07 provengono da un gate
  salito fino a 0,45": il 2026-08-07 e' **l'ultimo giorno pre** per S4 (lo
  stopgap Redis e' dello stesso giorno). pre = giorni <= 2026-08-07,
  post = giorni > 2026-08-07.

Il 2026-08-07 cade quindi in segmenti opposti per le due strategie (post-#185
per S1, pre-#191 per S4): e' un fatto, non un'incoerenza, e ``nota_08_07`` lo
ricorda perche' fra sette settimane nessuno se ne ricorderebbe.
"""

from __future__ import annotations

from datetime import date

from src.analysis.dossier.economic_pnl import CONTAMINAZIONE


def _to_date(v) -> date:
    """Normalizza la data di una riga del ledger: str ISO o date -> date."""
    return v if isinstance(v, date) else date.fromisoformat(v)

# Confine #185: primo giorno post = 2026-08-07 (deploy PR #188 pre US-open).
DEPLOY_185 = date(2026, 8, 7)
# Confine #191: ultimo giorno pre = 2026-08-07 (charter: gate a 0,45 fino al 07).
STOPGAP_191 = date(2026, 8, 7)

SOGLIA_S4 = 200.0          # dollari, carta domanda 1
SOGLIA_NO_NEWS = 0.60      # frazione di giorni, carta domanda 1
FINESTRA_MINIMA_GIORNI = 40       # giorni di borsa, carta "Durata"


def dominant_miss(miss: dict[str, int]) -> str | None:
    """La causa di miss con piu' occorrenze, oppure None se vuota o in pareggio.

    Diversa da ``miss_cause.dominant_cause``: lavora sulla tassonomia del ledger
    di mercato (NO_NEWS, THIN_NEUTRAL, WRONG_SIGN, FILTERED, OUT_OF_STRATEGY_SCOPE)
    che contiene cause non nella CAUSE_ORDER del classificatore. Nessuna
    forzatura in caso di pareggio: la carta del 2026-08-05 mostra che capita, e
    scegliere a caso e' proprio il difetto che la pre-registrazione evita.
    """
    if not miss:
        return None
    massimo = max(miss.values())
    if massimo == 0:
        return None
    vincitori = [k for k, v in miss.items() if v == massimo]
    return vincitori[0] if len(vincitori) == 1 else None


def spy_cumulative_return(
    market_rows: list[dict], window_start: date, as_of: date
) -> float:
    """Rendimento cumulato composto di SPY sulla finestra.

    Allineamento con S1: il P&L economico di S1 vale 0 a ``window_start`` per
    definizione (mark dal close del primo giorno); il rendimento cumulato SPY
    parte quindi dal giorno *successivo* a ``window_start`` (intervallo aperto a
    sinistra). Anche le righe anteriori a ``window_start`` (es. 2026-07-31) non
    contano, come dice la nota della carta. Restituisce 0.0 se nessun giorno
    *strettamente successivo* a ``window_start`` rientra nella finestra.
    """
    rendimenti = [
        float(r["spy"])
        for r in market_rows
        if window_start < _to_date(r["data"]) <= as_of
    ]
    cum = 1.0
    for r in rendimenti:
        cum *= 1.0 + r
    return cum - 1.0


def _giorni_osservati(market_rows: list[dict], window_start: date, as_of: date) -> list[date]:
    return sorted(
        _to_date(r["data"])
        for r in market_rows
        if window_start <= _to_date(r["data"]) <= as_of
    )


def _segmento(
    cumulato: dict[date, float], pre_giorni: list[date], post_giorni: list[date]
) -> dict:
    """P&L economico guadagnato dentro ogni tratto.

    ``delta_cum`` pre = cumulata all'ultimo giorno del pre (la finestra parte da
    zero); ``delta_cum`` post = cumulata all'ultimo giorno del post meno cumulata
    all'ultimo giorno del pre, cioe' il tratto effettivamente guadagnato dopo il
    confine. Nessuna interpolazione: se un tratto non ha giorni, delta 0.
    """
    pre_delta = cumulato[pre_giorni[-1]] if pre_giorni else 0.0
    base_post = cumulato[pre_giorni[-1]] if pre_giorni else 0.0
    post_delta = (cumulato[post_giorni[-1]] - base_post) if post_giorni else 0.0
    return {
        "pre": {"giorni": pre_giorni, "delta_cum": pre_delta},
        "post": {"giorni": post_giorni, "delta_cum": post_delta},
    }


def compute_scoreboard(
    economic: dict,
    market_rows: list[dict],
    window_start: date,
    as_of: date,
) -> dict:
    """Assembla lo scoreboard descrittivo delle due domande di uscita.

    Args:
        economic: output di ``economic_pnl.compute_economic_pnl``.
        market_rows: righe di ``market_daily.jsonl`` (dict con data/spy/miss).
        window_start: primo giorno della finestra.
        as_of: giorno di valutazione (ultimo osservato).

    Returns:
        dict con giorno, no_news_dominant, s4_vs_200, s1_vs_spy, book,
        contaminazione, segmenti (#185/#191), numerosita, missingness.
    """
    cumulato = economic["cumulato"]
    osservati = _giorni_osservati(market_rows, window_start, as_of)

    # --- domanda 1: NO_NEWS dominante -------------------------------------
    no_news_giorni = []
    for r in market_rows:
        d = _to_date(r["data"])
        if not (window_start <= d <= as_of):
            continue
        if dominant_miss(r.get("miss") or {}) == "NO_NEWS":
            no_news_giorni.append(d)
    no_news_giorni.sort()

    # --- domanda 1: S4 vs +-200 -------------------------------------------
    s4_cum = cumulato["S4"].get(as_of, 0.0)

    # --- domanda 2: S1 vs SPY ---------------------------------------------
    s1_cum = cumulato["S1"].get(as_of, 0.0)
    spy_ret = spy_cumulative_return(market_rows, window_start, as_of)
    cap_s1 = float(economic["capital_base"].get("S1", 0.0))
    spy_benchmark = spy_ret * cap_s1

    # --- segmenti di discontinuita' ---------------------------------------
    # #185 (S1): 08-07 primo giorno post
    s1_pre = [d for d in cumulato["S1"] if d < DEPLOY_185 and d <= as_of]
    s1_post = [d for d in cumulato["S1"] if d >= DEPLOY_185 and d <= as_of]
    # #191 (S4): 08-07 ultimo giorno pre
    s4_pre = [d for d in cumulato["S4"] if d <= STOPGAP_191 and d <= as_of]
    s4_post = [d for d in cumulato["S4"] if d > STOPGAP_191 and d <= as_of]
    s1_pre.sort(); s1_post.sort(); s4_pre.sort(); s4_post.sort()

    seg_185 = _segmento(cumulato["S1"], s1_pre, s1_post)
    seg_191 = _segmento(cumulato["S4"], s4_pre, s4_post)

    return {
        "finestra": {"inizio": window_start, "as_of": as_of, "minimo_giorni": FINESTRA_MINIMA_GIORNI},
        "giorno": {
            "n": len(osservati),
            "denominatore": FINESTRA_MINIMA_GIORNI,
            "osservati": osservati,
        },
        "no_news_dominant": {
            "numerator": len(no_news_giorni),
            "denominator": len(osservati),
            "giorni": no_news_giorni,
            "soglia_carta": SOGLIA_NO_NEWS,
            "superata_soglia": (
                len(no_news_giorni) / len(osservati) >= SOGLIA_NO_NEWS
                if osservati else False
            ),
        },
        "s4_vs_200": {
            "cumulato": s4_cum,
            "soglia": SOGLIA_S4,
            "within": abs(s4_cum) <= SOGLIA_S4,
        },
        "s1_vs_spy": {
            "s1_cumulato": s1_cum,
            "spy_cum_return": spy_ret,
            "spy_benchmark_usd": spy_benchmark,
            "delta_vs_spy": s1_cum - spy_benchmark,
            "capital_base": cap_s1,
        },
        "book": {"cumulato": cumulato["BOOK"].get(as_of, 0.0)},
        "contaminazione": {
            "cumulato": cumulato[CONTAMINAZIONE].get(as_of, 0.0),
            "numerosita": economic["numerosita"].get(CONTAMINAZIONE, 0),
        },
        "segmenti": {
            "#185": {
                "strategia": "S1", "confine": DEPLOY_185,
                "nota": "PR #188 deployata 2026-08-07 pre US-open: 08-07 primo giorno post (S1 mensile)",
                **seg_185,
            },
            "#191": {
                "strategia": "S4", "confine": STOPGAP_191,
                "nota": "stopgap Redis 2026-08-07: 08-07 ultimo giorno pre (gate 0,45)",
                **seg_191,
            },
            "nota_08_07": (
                "2026-08-07 e' post-#185 (S1 rispetta MONTHLY) ma pre-#191 "
                "(S4 gate ancora 0,45 fino allo stopgap): cade in segmenti "
                "opposti per le due strategie."
            ),
        },
        "numerosita": dict(economic["numerosita"]),
        "esclusi": economic["esclusi"],
        "missingness": dict(economic["missing"]),
    }