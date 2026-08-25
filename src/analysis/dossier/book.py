"""Metriche del nostro book per il dossier.

Modulo puro: riceve trade e barre gia' caricati, non tocca rete ne' DB.
"""

from __future__ import annotations

import statistics
from typing import TypedDict

# Soglia DICHIARATA sotto la quale la gamba intraday (close - open) e' troppo
# piccola perche' una quota su quel denominatore significhi qualcosa: 0,5% del
# prezzo di apertura. Non e' una taratura di strategia (freeze #171): non entra
# in nessuna decisione di trading, marca solo la misura come non leggibile —
# come il 2026-08-12, quando la gamba intraday era piatta su 7 mover su 9 e la
# quota (a) andava dichiarata degenere invece che riportata (#246).
SOGLIA_DENOMINATORE_DEGENERE = 0.005

# Soglia della guardia ombra contraddizione (#335): segna (NON blocca) un BUY
# lungo il cui score e' positivo mentre il titolo e' gia' sceso oltre questo
# delta nella seduta. E' uno strumento di MISURA, non una taratura di strategia:
# non entra in nessuna decisione di trading e non e' congelato dal freeze #171.
# Configurabile via `soglia_guardia` per analisi di sensibilita'.
SOGLIA_GUARDIA_CONTRADDIZIONE = 0.04


class EntryTrade(TypedDict, total=False):
    """Campi di un ingresso necessari alle metriche del dossier.

    `total=False` perche' `signal_score` e' facoltativo: i trade legacy (F-002)
    e i dossier senza la colonna non lo portano, e la guardia ombra resta None.
    I campi strutturali (symbol, strategia, ora_utc, entry_price, qty) restano
    di fatto sempre presenti ma non vengono marcati required per non rompere i
    dict letterali dei dossier storici.
    """

    symbol: str
    strategia: str
    ora_utc: str
    entry_price: float
    qty: float
    signal_score: float | None


class DailyBar(TypedDict, total=False):
    """Barra giornaliera OHLC usata per misurare un ingresso.

    `close_prec` (chiusura del giorno precedente) e' opzionale: senza, la quota
    nel gap non e' calcolabile e resta None — mai sostituita da un'altra misura.
    """

    open: float
    high: float
    low: float
    close: float
    close_prec: float | None


class EntryMetrics(EntryTrade):
    """Ingresso arricchito con metriche provvisorie di fine giornata.

    `quota_movimento_precedente_al_segnale` e `quota_nel_gap` sono DUE misure
    diverse dello stesso fenomeno (#246): la prima sulla gamba intraday, la
    seconda sul salto di apertura. Non vanno mediate, sommate, ne' messe nella
    stessa serie: hanno denominatori diversi e si degradano in modi diversi.
    """

    entry_percentile: float | None
    mtm_eod: float | None
    vs_apertura: float | None
    quota_movimento_precedente_al_segnale: float | None
    denominatore_degenere: bool
    quota_nel_gap: float | None
    # #335: strumentazione entry-gate. Misura read-only: nessuno di questi
    # campi entra in una decisione di trading.
    # `ritorno_sessione_al_segnale` e' il delta del prezzo sulla chiusura del
    # giorno precedente al momento dell'ingresso: il "down X% on the session"
    # che un entry gate dovrebbe vedere. E' GAP-INCLUSIVO di proposito: WMT
    # 2026-08-20 scese ~9% sulla seduta, ma solo ~2% dentro l'RTH — il resto
    # fu nel gap di apertura (quota_nel_gap=0.757). Una misura vs-open
    # vedrebbe -2% e lascerebbe passare il BUY a +0.318 nel crash reale.
    ritorno_sessione_al_segnale: float | None
    # True/False se il calendario earnings era disponibile, None se non lo era
    # (UNKNOWN): il dossier non imputa False per difetto di fonte.
    giorno_di_earnings: bool | None
    # Guardia ombra (#335 step 2): True se score positivo e titolo gia' sceso
    # oltre la soglia nella seduta. None se score o ritorno mancanti (non
    # decidibile). `motivo_guardia_contraddizione` spiega il firing, None altrimenti.
    guardia_contraddizione_ombra: bool | None
    motivo_guardia_contraddizione: str | None


class ExitTrade(TypedDict):
    """Campi di una chiusura necessari alle metriche del dossier."""

    symbol: str
    strategia: str
    exit_price: float
    qty: float
    pnl_net: float
    exit_reason: str
    ore_tenuta: float


class ExitMetrics(ExitTrade):
    """Chiusura arricchita con il drift successivo all'uscita."""

    drift_post_uscita: float | None


class ClosedTradeForHour(TypedDict, total=False):
    """Campi minimi per aggregare il P&L per ora di ingresso.

    `stop_strategy` e' il campo GREZZO del trade: None per la coorte legacy
    (F-002), che NON va rimappata su S1/S4 con un COALESCE. Rimapparla e'
    esattamente il modo in cui 87 trade del 07-10 sono finiti dentro un t-stat
    (#246).
    """

    ora_ingresso: int
    pnl_net: float
    stop_strategy: str | None


class SleeveAggregate(TypedDict):
    """Sotto-aggregato per `stop_strategy` dentro un'ora di ingresso.

    `stop_strategy` None e' la coorte legacy: riportata separatamente, mai
    eliminata in silenzio ne' fusa con le sleeve attribuite.
    """

    stop_strategy: str | None
    n: int
    win: int
    somma_pnl: float
    media: float


class EntryHourAggregate(TypedDict):
    """Statistiche descrittive dei trade entrati nella stessa ora UTC.

    `t_stat_is_test` e' sempre False: il campo `t_stat` esiste per ordinare le
    ipotesi, non per dichiararle vere (vedi il docstring di
    aggregate_by_entry_hour). Il flag lo rende leggibile da una macchina, non
    solo da chi legge la prosa.
    """

    ora: int
    n: int
    win: int
    somma_pnl: float
    media: float
    dev_std: float | None
    t_stat: float | None
    t_stat_is_test: bool
    n_legacy: int
    per_stop_strategy: list[SleeveAggregate]


def compute_entries(
    trades: list[EntryTrade],
    bars: dict[str, DailyBar],
    *,
    earnings_symbols: set[str] | None = None,
    soglia_guardia: float = SOGLIA_GUARDIA_CONTRADDIZIONE,
) -> list[EntryMetrics]:
    """Metriche degli ingressi del giorno, con esito PROVVISORIO di fine giornata.

    Attenzione a come si legge: su un book dove la posizione media dura 14 giorni,
    il mark-to-market di fine giornata NON e' un giudizio sulla decisione. Serve a
    rendere visibile un pattern aggregato, non a condannare il singolo trade.

    entry_percentile e' la misura dell'inseguimento: 0 = comprato sul minimo del
    giorno, 1 = sul massimo. None se il range e' degenere o la barra manca.

    Due campi distinti misurano "quanto movimento era gia' avvenuto" (#246), e
    restano distinti per costruzione:

    - `quota_movimento_precedente_al_segnale` = (entry - open) / (close - open):
      la frazione della GAMBA INTRADAY gia' percorsa al momento dell'ingresso.
      Non e' clampata: >1 significa che al nostro ingresso il prezzo aveva gia'
      superato il livello di chiusura (ORCL 110,8%, NOK 121,1% il 08-11).
      Accompagnata da `denominatore_degenere`, vera quando |close - open| / open
      sta sotto SOGLIA_DENOMINATORE_DEGENERE: la quota c'e' ancora, ma su un
      denominatore che non regge il peso di una lettura.
    - `quota_nel_gap` = (open - close_prec) / (close - close_prec): quanto del
      movimento close-to-close sta nel SALTO DI APERTURA, prima che il motore
      RTH esista. Denominatore diverso, fenomeno diverso.

    Non calcolare mai una media, una somma o una serie unica fra i due: il
    08-12 la prima era degenere e la seconda valeva 99% mediano — fonderle
    avrebbe prodotto un numero che non descrive niente.

    #335 (strumentazione entry-gate, misura read-only): `ritorno_sessione_al_segnale`
    e' il delta vs chiusura precedente (gap-incluso) al momento dell'ingresso;
    `giorno_di_earnings` riporta se il simbolo aveva earnings nella seduta
    (None se il calendario non era disponibile); `guardia_contraddizione_ombra`
    segna un BUY lungo il cui score e' positivo mentre il titolo e' gia' sceso
    oltre `soglia_guardia` sulla seduta. Nessuno di questi tre entra in una
    decisione di trading.
    """
    result: list[EntryMetrics] = []
    for trade in trades:
        bar = bars.get(trade["symbol"])
        row: EntryMetrics = {
            "symbol": trade["symbol"],
            "strategia": trade["strategia"],
            "ora_utc": trade["ora_utc"],
            "entry_price": trade["entry_price"],
            "qty": trade["qty"],
            "entry_percentile": None,
            "mtm_eod": None,
            "vs_apertura": None,
            "quota_movimento_precedente_al_segnale": None,
            "denominatore_degenere": True,
            "quota_nel_gap": None,
            "ritorno_sessione_al_segnale": None,
            "giorno_di_earnings": None,
            "guardia_contraddizione_ombra": None,
            "motivo_guardia_contraddizione": None,
        }
        # `giorno_di_earnings` non dipende dalla barra, solo dal calendario:
        # None quando il calendario non era disponibile (UNKNOWN), mai False
        # imposto per difetto di fonte.
        if earnings_symbols is not None:
            row["giorno_di_earnings"] = trade["symbol"] in earnings_symbols
        if bar is not None:
            rng = bar["high"] - bar["low"]
            if rng > 0:
                row["entry_percentile"] = (trade["entry_price"] - bar["low"]) / rng
            row["mtm_eod"] = (bar["close"] - trade["entry_price"]) * trade["qty"]
            row["vs_apertura"] = (bar["close"] - bar["open"]) * trade["qty"]
            close_prec = bar.get("close_prec")
            row["ritorno_sessione_al_segnale"] = (
                (trade["entry_price"] - close_prec) / close_prec
                if close_prec
                else None
            )
            row.update(_quote_movimento(trade["entry_price"], bar))
        # La guardia ombra vive dopo il calcolo del ritorno: legge score e
        # ritorno gia' risolti (None su entrambi i lati se assenti).
        guardia, motivo = _guardia_contraddizione(
            trade.get("signal_score"), row["ritorno_sessione_al_segnale"], soglia_guardia
        )
        row["guardia_contraddizione_ombra"] = guardia
        row["motivo_guardia_contraddizione"] = motivo
        result.append(row)
    return result


def _quote_movimento(entry_price: float, bar: DailyBar) -> dict:
    """I due campi di quota del movimento, calcolati separatamente (#246 Q4).

    Ritorna sempre entrambe le chiavi piu' il flag di degenerazione, cosi' che
    un consumatore non possa leggere la quota intraday senza vedere se il suo
    denominatore reggeva.
    """
    apertura, chiusura = bar.get("open"), bar.get("close")
    close_prec = bar.get("close_prec")

    gamba_intraday = (
        chiusura - apertura if apertura is not None and chiusura is not None else None
    )
    degenere = (
        True
        if gamba_intraday is None or not apertura
        else abs(gamba_intraday) / abs(apertura) < SOGLIA_DENOMINATORE_DEGENERE
    )
    quota_intraday = (
        (entry_price - apertura) / gamba_intraday
        if gamba_intraday not in (None, 0)
        else None
    )

    movimento_totale = (
        chiusura - close_prec
        if chiusura is not None and close_prec not in (None, 0)
        else None
    )
    quota_gap = (
        (apertura - close_prec) / movimento_totale
        if movimento_totale not in (None, 0) and apertura is not None
        else None
    )

    return {
        "quota_movimento_precedente_al_segnale": quota_intraday,
        "denominatore_degenere": degenere,
        "quota_nel_gap": quota_gap,
    }


def _guardia_contraddizione(
    signal_score: float | None,
    ritorno_sessione: float | None,
    soglia: float,
) -> tuple[bool | None, str | None]:
    """Guardia ombra: segna (NON blocca) un BUY lungo il cui score e' positivo
    mentre il titolo e' gia' sceso oltre `soglia` sulla seduta (#335).

    `ritorno_sessione` e' il delta vs chiusura precedente (gap-incluso): e'
    il "down X% on the session" che un entry gate dovrebbe consultare, non il
    solo delta sull'apertura RTH (che per WMT 2026-08-20 valeva -2% contro un
    -9% reale, con il resto nel gap di apertura).

    Tre stati, mai None confuso con False:

    - None: score o ritorno mancanti -> non decidibile. I trade legacy senza
      `signal_score` e gli ingressi senza close_prec restano qui, non forzati
      a False.
    - True: score > 0 e ritorno <= -soglia -> il segno dello score contraddice
      il movimento di prezzo gia' avvenuto. `motivo` spiega il firing.
    - False: score e ritorno presenti, nessuna contraddizione (score positivo su
      titolo su, oppure score non positivo).
    """
    if signal_score is None or ritorno_sessione is None:
        return None, None
    if signal_score > 0 and ritorno_sessione <= -soglia:
        motivo = (
            f"score=+{signal_score:.4g} positivo, ritorno_sessione="
            f"{ritorno_sessione:+.4g} <= -{soglia:.4g}"
        )
        return True, motivo
    return False, None


def aggregate_contradiction_guard(
    ingressi: list[dict], chiusure: list[dict]
) -> dict:
    """Conteggio ombra della guardia contraddizione su un set di ingressi (#335).

    Misura read-only: conta quanti ingressi la guardia avrebbe soppresso e
    somma il P&L che hanno realizzato. Il matching ingresso->chiusura e' per
    (symbol, strategia) in ordine FIFO: e' un'approssimazione STESSO TURNO,
    adeguata per S4 (tipicamente in/out nella stessa seduta, come WMT 16:37 ->
    17:37). Un ingresso il cui titolo resta aperto oltre il dossier del giorno
    non ha uscita qui, e resta tra gli `n_soppressi_aperti`: il suo P&L
    realizzato si raccoglie nel dossier del giorno di uscita.

    `n_valutabili` conta solo gli ingressi con guardia decidibile (non None):
    i trade legacy senza score o senza barra non entrano nel denominatore.
    """
    per_chiave: dict[tuple[str, str], list[float]] = {}
    for chiusura in chiusure:
        chiave = (str(chiusura.get("symbol") or ""), str(chiusura.get("strategia") or ""))
        per_chiave.setdefault(chiave, []).append(float(chiusura.get("pnl_net") or 0.0))

    n_valutabili = 0
    n_soppressi = 0
    n_soppressi_con_uscita = 0
    n_soppressi_aperti = 0
    somma_pnl = 0.0
    cursor: dict[tuple[str, str], int] = {k: 0 for k in per_chiave}
    for ingresso in ingressi:
        guardia = ingresso.get("guardia_contraddizione_ombra")
        if guardia is None:
            continue
        n_valutabili += 1
        if guardia is not True:
            continue
        n_soppressi += 1
        chiave = (str(ingresso.get("symbol") or ""), str(ingresso.get("strategia") or ""))
        coda = per_chiave.get(chiave)
        if coda and cursor.get(chiave, 0) < len(coda):
            pnl = coda[cursor[chiave]]
            cursor[chiave] = cursor.get(chiave, 0) + 1
            somma_pnl += pnl
            n_soppressi_con_uscita += 1
        else:
            n_soppressi_aperti += 1

    return {
        "n_valutabili": n_valutabili,
        "n_soppressi": n_soppressi,
        "n_soppressi_con_uscita": n_soppressi_con_uscita,
        "n_soppressi_aperti": n_soppressi_aperti,
        "somma_pnl_realizzato_soppressi": round(somma_pnl, 6),
        "matching": "symbol+strategia FIFO, stesso turno (approx)",
    }


def compute_exits(
    trades: list[ExitTrade], closes: dict[str, float]
) -> list[ExitMetrics]:
    """Metriche delle posizioni chiuse: qui il verdetto e' legittimo, l'esito e' completo.

    drift_post_uscita positivo = soldi lasciati sul tavolo (il titolo e' salito dopo
    che siamo usciti); negativo = perdita evitata. Se la mediana mobile e' stabilmente
    positiva, usciamo troppo presto — ed e' misurabile, a differenza di un miss.
    """
    result: list[ExitMetrics] = []
    for trade in trades:
        close = closes.get(trade["symbol"])
        result.append(
            {
                "symbol": trade["symbol"],
                "strategia": trade["strategia"],
                "exit_price": trade["exit_price"],
                "qty": trade["qty"],
                "pnl_net": trade["pnl_net"],
                "exit_reason": trade["exit_reason"],
                "ore_tenuta": trade["ore_tenuta"],
                "drift_post_uscita": (
                    None
                    if close is None
                    else (close - trade["exit_price"]) * trade["qty"]
                ),
            }
        )
    return result


def aggregate_by_entry_hour(
    chiusi: list[ClosedTradeForHour],
) -> list[EntryHourAggregate]:
    """Raggruppa i trade chiusi per ora UTC di ingresso.

    ATTENZIONE ALLA LETTURA: e' un'analisi post-hoc su molti bucket orari. Un t_stat
    marginale qui NON e' una scoperta: con ~8 bucket, una correzione per confronti
    multipli lo annulla. Il campo esiste per ordinare le ipotesi, non per dichiararle
    vere. Chi consuma questo dato deve riportare anche la numerosita'.

    Per questo ogni bucket porta `t_stat_is_test: False` (#246): il t dell'ora 14
    valeva -4,96 su 129 osservazioni che NON sono indipendenti — 87 sono la coorte
    legacy senza attribuzione di strategia (F-002, quasi tutte entrate il 07-10) e
    33 vengono da un solo giorno. Il flag rende la riserva leggibile da chi consuma
    il JSON, non solo da chi legge questo docstring.

    `n_legacy` conta i trade con `stop_strategy` NULL e `per_stop_strategy`
    scompone il bucket per sleeve. Cio' che resta dopo il ridimensionamento non e'
    nullo e deve restare visibile: S1 all'ora 14 fa 2 vincenti su 27. La coorte
    legacy e' riportata a parte, mai tolta di mezzo in silenzio.
    """
    per_ora: dict[int, list[ClosedTradeForHour]] = {}
    for trade in chiusi:
        per_ora.setdefault(trade["ora_ingresso"], []).append(trade)

    result: list[EntryHourAggregate] = []
    for ora in sorted(per_ora):
        trades = per_ora[ora]
        pnl_values = [t["pnl_net"] for t in trades]
        sample_size = len(pnl_values)
        mean = sum(pnl_values) / sample_size
        std_dev = statistics.stdev(pnl_values) if sample_size >= 2 else None
        t_stat = (mean / (std_dev / (sample_size**0.5))) if std_dev else None
        result.append(
            {
                "ora": ora,
                "n": sample_size,
                "win": sum(1 for pnl in pnl_values if pnl > 0),
                "somma_pnl": sum(pnl_values),
                "media": mean,
                "dev_std": std_dev,
                "t_stat": t_stat,
                # Non e' un test: osservazioni non indipendenti, bucket multipli,
                # coorte legacy dentro. Vedi il docstring.
                "t_stat_is_test": False,
                "n_legacy": sum(1 for t in trades if t.get("stop_strategy") is None),
                "per_stop_strategy": _per_sleeve(trades),
            }
        )
    return result


def _per_sleeve(trades: list[ClosedTradeForHour]) -> list[SleeveAggregate]:
    """Scompone un bucket orario per `stop_strategy`, coorte legacy inclusa.

    Ordine: sleeve attribuite in ordine alfabetico, poi la coorte legacy
    (stop_strategy None) in coda — separata e visibile, mai fusa.
    """
    per_sleeve: dict[str | None, list[float]] = {}
    for trade in trades:
        per_sleeve.setdefault(trade.get("stop_strategy"), []).append(trade["pnl_net"])

    attribuite = sorted(k for k in per_sleeve if k is not None)
    chiavi: list[str | None] = [*attribuite]
    if None in per_sleeve:
        chiavi.append(None)

    return [
        {
            "stop_strategy": chiave,
            "n": len(per_sleeve[chiave]),
            "win": sum(1 for pnl in per_sleeve[chiave] if pnl > 0),
            "somma_pnl": sum(per_sleeve[chiave]),
            "media": sum(per_sleeve[chiave]) / len(per_sleeve[chiave]),
        }
        for chiave in chiavi
    ]
