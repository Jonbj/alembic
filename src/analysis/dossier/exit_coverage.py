"""Cecita' della copertura news sul lato uscita del libro (#324).

Il dossier misura la copertura sui **mover non in portafoglio**: `compute_miss_candidates`
scarta per costruzione i simboli gia' detenuti (`sym not in in_portafoglio`, in
`src/analysis/dossier/market.py`). La conseguenza e' un punto cieco misurabile: il
2026-08-19 GE (-5,03%), DELL (-6,64%) e WDC (-6,87%) — due dei tre peggiori mover della
seduta — non compaiono in nessuna riga del dossier, perche' erano in portafoglio. Le
loro zero righe di `news_log` non sono state contate da nulla, mentre le stesse zero
righe su un simbolo *non* detenuto producevano un candidato `NO_NEWS`.

L'assenza di notizia non impedisce solo l'ingresso: impedisce anche qualunque segnale di
uscita o riduzione su una posizione **gia' in perdita marcata**. Questo modulo misura
quel secondo effetto, che nessun conteggio esistente vedeva.

Modulo puro: riceve righe, conteggi e barre gia' caricati, non tocca rete ne' DB. Misura
read-only — nessuna decisione di trading legge questi campi, e nessuna soglia di
strategia e' toccata. Le due soglie qui sotto sono parametri di **misura** dichiarati,
non taratura: definiscono cosa chiamiamo "perdita marcata" e "ricorrenza", esattamente
come `SOGLIA_GUARDIA_CONTRADDIZIONE` per la guardia ombra (#335).
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence


EXIT_COVERAGE_SCHEMA_VERSION = "1.0"

# Perdita mark-to-close dall'ingresso oltre la quale una posizione ha qualcosa da
# decidere. -3% e' la stessa grandezza della soglia mover del dossier (#174).
SOGLIA_PERDITA_DA_INGRESSO = -0.03

# Sedute consecutive a zero righe richieste perche' la cecita' sia ricorrenza e non
# una giornata muta: un titolo puo' legittimamente non fare notizia per un giorno.
SEDUTE_MINIME_CIECHE = 2

DEFINIZIONE = (
    "posizione viva all'open RTH, in perdita mark-to-close >= |soglia| dall'ingresso, "
    "con zero righe news_log e zero sentiment_signals nella seduta e zero righe per "
    "almeno `sedute_minime` sedute consecutive. Dato insufficiente resta None (UNKNOWN), "
    "mai False per difetto."
)


def _float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _data_iso(value: object) -> str | None:
    """Prima parte ISO di un timestamp, senza inventare un fuso.

    Le date di seduta arrivano tutte da Alpaca in ora locale di New York, i timestamp
    dei trade sono UTC: il confronto e' fra date di calendario, e la conversione non
    cambierebbe l'esito su un ingresso avvenuto in seduta.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:10]


def _streak_senza_righe(
    sedute: Sequence[str],
    righe_per_seduta: Mapping[str, int],
    data_ingresso: str | None,
) -> tuple[int, str | None]:
    """Sedute consecutive a zero righe che finiscono nella seduta target.

    Il conteggio si ferma alla prima seduta con almeno una riga (troncamento None: lo
    streak e' completo), alla data di ingresso (una posizione aperta ieri non puo'
    essere cieca da una settimana) o all'inizio della finestra osservata. Nei due casi
    di troncamento lo streak vero puo' essere piu' lungo del numero riportato, e il
    campo lo dichiara invece di lasciarlo dedurre.
    """
    conteggio = 0
    for seduta in reversed(sedute):
        if data_ingresso is not None and seduta < data_ingresso:
            return conteggio, "ingresso"
        if int(righe_per_seduta.get(seduta, 0) or 0) > 0:
            return conteggio, None
        conteggio += 1
    return conteggio, "finestra"


def build_exit_coverage(
    posizioni: Sequence[Mapping[str, Any]],
    *,
    data: str,
    sedute: Sequence[str],
    righe_per_seduta: Mapping[str, Mapping[str, int]],
    fonti_finestra: Mapping[str, Sequence[str]],
    copertura_per_ticker: Mapping[str, Mapping[str, Any]],
    segnali_per_ticker: Mapping[str, int],
    barre: Mapping[str, Mapping[str, Any]],
    soglia_perdita: float = SOGLIA_PERDITA_DA_INGRESSO,
    sedute_minime: int = SEDUTE_MINIME_CIECHE,
) -> dict:
    """Misura il punto cieco lato uscita sulle posizioni vive all'open.

    Args:
        posizioni: posizioni vive all'open RTH (`_opening_positions` del dossier).
        data: seduta target in ISO.
        sedute: sedute di borsa della finestra, ordinate, ultima == `data`. Vuota
            quando il calendario non ha risposto: lo streak resta UNKNOWN, non zero.
        righe_per_seduta: {ticker: {seduta: righe news_log}}.
        fonti_finestra: {ticker: fonti che hanno prodotto almeno una riga}. Le fonti
            per-ticker vive interrogano l'intera watchlist, quindi una lista vuota
            significa zero **resa** del provider, non fonte non configurata (#324 §2).
        copertura_per_ticker: `copertura_articoli["per_ticker"]` della seduta (#279).
        segnali_per_ticker: {ticker: segnali di sentiment scritti nella seduta}.
        barre: barre giornaliere per il mark to close.
    """
    calendario_assente = not sedute
    righe: list[dict] = []

    for posizione in sorted(
        posizioni,
        key=lambda row: (
            str(row.get("symbol") or ""),
            row.get("trade_id") is None,
            row.get("trade_id") or 0,
        ),
    ):
        ticker = str(posizione.get("symbol") or "").strip().upper()
        missingness: list[str] = []

        qty = _float(posizione.get("qty"))
        if qty is None:
            missingness.append("qty_missing")
        entry_price = _float(posizione.get("entry_price"))
        if entry_price is None or entry_price == 0:
            missingness.append("entry_price_missing")
            entry_price = None
        barra = barre.get(ticker)
        close = _float(barra.get("close")) if barra else None
        if barra is None:
            missingness.append("daily_bar_missing")
        elif close is None:
            missingness.append("daily_close_missing")

        ritorno = (
            close / entry_price - 1.0
            if close is not None and entry_price is not None
            else None
        )
        perdita_marcata = ritorno <= soglia_perdita if ritorno is not None else None

        righe_ticker = righe_per_seduta.get(ticker) or {}
        righe_giorno = int(righe_ticker.get(data, 0) or 0)
        copertura = copertura_per_ticker.get(ticker) or {}
        articoli_unici = copertura.get("articoli_unici")
        effective = copertura.get("effective_timely_articles")
        segnali = int(segnali_per_ticker.get(ticker, 0) or 0)

        copertura_nulla = righe_giorno == 0 and segnali == 0
        # Articoli presenti ma nessuno issuer-specific tempestivo e' un difetto di
        # RILEVANZA (#279), non un buco di ingestione: si misura a parte e non
        # diventa cecita', altrimenti le due cause si sommerebbero indistinguibili.
        copertura_effettiva_nulla = (
            bool(effective == 0) if effective is not None else None
        )

        if calendario_assente:
            streak: int | None = None
            troncato: str | None = None
            missingness.append("calendario_sedute_non_disponibile")
        else:
            streak, troncato = _streak_senza_righe(
                sedute, righe_ticker, _data_iso(posizione.get("entry_time"))
            )

        if perdita_marcata is None or streak is None:
            cieco: bool | None = None
        else:
            cieco = bool(
                perdita_marcata and copertura_nulla and streak >= sedute_minime
            )

        trade_id = posizione.get("trade_id")
        cid = trade_id if trade_id is not None else f"{ticker}:{posizione.get('entry_time')}"
        righe.append({
            "schema_version": EXIT_COVERAGE_SCHEMA_VERSION,
            "data": data,
            "ticker": ticker,
            "trade_id": trade_id,
            "strategia": posizione.get("strategia"),
            "causal_event_id": f"exit-coverage:{cid}:{data}",
            "qty": qty,
            "entry_price": entry_price,
            "mark_close": close,
            "notional_usd": qty * close if qty is not None and close is not None else None,
            "ritorno_da_ingresso": ritorno,
            "perdita_marcata": perdita_marcata,
            "righe_news_log_giorno": righe_giorno,
            "articoli_unici_giorno": articoli_unici,
            "articoli_effective_timely_giorno": effective,
            "segnali_sentiment_giorno": segnali,
            "copertura_nulla": copertura_nulla,
            "copertura_effettiva_nulla": copertura_effettiva_nulla,
            "sedute_consecutive_senza_righe": streak,
            "streak_troncato_da": troncato,
            "fonti_osservate_finestra": sorted(fonti_finestra.get(ticker) or []),
            "uscita_nella_seduta": _data_iso(posizione.get("exit_time")) == data,
            "cieco_lato_uscita": cieco,
            "missingness": missingness,
        })

    cieche = [row for row in righe if row["cieco_lato_uscita"] is True]
    notional_cieco = [row["notional_usd"] for row in cieche]
    return {
        "schema_version": EXIT_COVERAGE_SCHEMA_VERSION,
        "data": data,
        "definizione": DEFINIZIONE,
        "soglia_perdita_da_ingresso": soglia_perdita,
        "sedute_minime": sedute_minime,
        "sedute_finestra": list(sedute),
        "posizioni": righe,
        "aggregato": {
            "n_posizioni": len(righe),
            "n_copertura_nulla": sum(1 for row in righe if row["copertura_nulla"]),
            "n_copertura_effettiva_nulla": sum(
                1 for row in righe if row["copertura_effettiva_nulla"] is True
            ),
            "n_perdita_marcata": sum(
                1 for row in righe if row["perdita_marcata"] is True
            ),
            "n_cieche_lato_uscita": len(cieche),
            "n_cieche_ancora_aperte": sum(
                1 for row in cieche if not row["uscita_nella_seduta"]
            ),
            "n_indeterminati": sum(
                1 for row in righe if row["cieco_lato_uscita"] is None
            ),
            "ticker_ciechi": sorted({row["ticker"] for row in cieche}),
            # Esposizione, NON un costo: nessun controfattuale dice che un'uscita
            # sarebbe stata migliore. La carta #171 distingue null da 0.0, quindi il
            # notional non stimabile resta contato a parte invece di valere zero.
            "notional_cieco_usd": sum(
                value for value in notional_cieco if value is not None
            ),
            "n_notional_non_stimato": sum(
                1 for value in notional_cieco if value is None
            ),
        },
    }
