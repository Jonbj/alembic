"""Metriche del nostro book per il dossier.

Modulo puro: riceve trade e barre gia' caricati, non tocca rete ne' DB.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timezone
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

    `total=False` preserva i dict letterali dei dossier storici; i campi qui
    elencati sono strutturali nel wiring corrente.
    """

    symbol: str
    strategia: str
    ora_utc: str
    entry_price: float
    qty: float


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


class S4EntryIntent(TypedDict, total=False):
    """Intento S4 tradabile catturato dal ledger point-in-time #294."""

    intent_id: str
    signal_id: int | None
    symbol: str
    signal_at: str
    decision_at: str
    signal_score: float | None
    final_reason_code: str | None
    is_tradable: bool
    trade_id: int | None
    pnl_realizzato: float | None


class S4EntryIntentMetrics(S4EntryIntent):
    """Intento S4 arricchito senza usare il prezzo di fill."""

    prezzo_al_segnale: float | None
    prezzo_al_segnale_timestamp: str | None
    prezzo_al_segnale_fonte: str | None
    ritorno_sessione_al_segnale: float | None
    giorno_di_earnings: bool | None
    guardia_contraddizione_ombra: bool | None
    motivo_guardia_contraddizione: str | None
    missingness: dict[str, str]


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
        }
        if bar is not None:
            rng = bar["high"] - bar["low"]
            if rng > 0:
                row["entry_percentile"] = (trade["entry_price"] - bar["low"]) / rng
            row["mtm_eod"] = (bar["close"] - trade["entry_price"]) * trade["qty"]
            row["vs_apertura"] = (bar["close"] - bar["open"]) * trade["qty"]
            row.update(_quote_movimento(trade["entry_price"], bar))
        result.append(row)
    return result


def compute_s4_entry_intents(
    intents: list[S4EntryIntent],
    bars_by_symbol: dict[str, list[dict]],
    daily_bars: dict[str, DailyBar],
    *,
    earnings_symbols: set[str] | None = None,
    soglia_guardia: float = SOGLIA_GUARDIA_CONTRADDIZIONE,
) -> list[S4EntryIntentMetrics]:
    """Misura ogni intento S4 tradabile al timestamp point-in-time del segnale.

    Il prezzo e' l'open della prima barra 5Min con timestamp >= `signal_at`, lo
    stesso contratto PIT della timeline del dossier: una barra gia' iniziata
    contiene futuro rispetto al segnale e non puo' essere letta. Il fill non e'
    mai usato come proxy; per un intento non eseguito non esiste proprio.
    """
    result: list[S4EntryIntentMetrics] = []
    for intent in intents:
        row: S4EntryIntentMetrics = {
            **intent,
            "prezzo_al_segnale": None,
            "prezzo_al_segnale_timestamp": None,
            "prezzo_al_segnale_fonte": None,
            "ritorno_sessione_al_segnale": None,
            "giorno_di_earnings": None,
            "guardia_contraddizione_ombra": None,
            "motivo_guardia_contraddizione": None,
            "missingness": {},
        }
        symbol = str(intent.get("symbol") or "")
        if earnings_symbols is not None:
            row["giorno_di_earnings"] = symbol in earnings_symbols

        signal_at = _as_utc(intent.get("signal_at"))
        if signal_at is None:
            row["missingness"]["prezzo_al_segnale"] = "signal_timestamp_missing"
        else:
            for bar in sorted(
                bars_by_symbol.get(symbol, []),
                key=lambda item: _as_utc(item.get("timestamp")) or datetime.max.replace(
                    tzinfo=timezone.utc
                ),
            ):
                bar_at = _as_utc(bar.get("timestamp"))
                if bar_at is None or bar_at < signal_at:
                    continue
                price = _optional_float(bar.get("open"))
                if price is None or price <= 0:
                    continue
                row["prezzo_al_segnale"] = price
                row["prezzo_al_segnale_timestamp"] = bar_at.isoformat()
                row["prezzo_al_segnale_fonte"] = "alpaca_sip_5min.open"
                break
            if row["prezzo_al_segnale"] is None:
                row["missingness"]["prezzo_al_segnale"] = (
                    "no_observable_bar_at_or_after_signal"
                )

        close_prec = (daily_bars.get(symbol) or {}).get("close_prec")
        price = row["prezzo_al_segnale"]
        if price is not None and close_prec not in (None, 0):
            row["ritorno_sessione_al_segnale"] = (price - close_prec) / close_prec
        elif close_prec in (None, 0):
            row["missingness"]["ritorno_sessione_al_segnale"] = (
                "previous_close_missing"
            )

        guardia, motivo = _guardia_contraddizione(
            intent.get("signal_score"),
            row["ritorno_sessione_al_segnale"],
            soglia_guardia,
        )
        row["guardia_contraddizione_ombra"] = guardia
        row["motivo_guardia_contraddizione"] = motivo
        result.append(row)
    return result


def _as_utc(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _optional_float(value) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


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

    - None: score, prezzo PIT o close precedente mancanti -> non decidibile.
      Gli intenti restano visibili con missingness, non forzati a False.
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


def aggregate_contradiction_guard(intents: list[dict]) -> dict:
    """Conta gli intenti che la guardia avrebbe soppresso e il loro P&L reale.

    L'identita' arriva dal ledger #294 e l'esecuzione dal `trade_id` collegato:
    nessun matching FIFO e nessuna imputazione di un fill a un intento scartato.
    """
    n_valutabili = 0
    n_soppressi = 0
    n_soppressi_eseguiti = 0
    n_soppressi_non_eseguiti = 0
    n_soppressi_con_pnl = 0
    n_soppressi_senza_pnl = 0
    somma_pnl = 0.0
    for intent in intents:
        guardia = intent.get("guardia_contraddizione_ombra")
        if guardia is None:
            continue
        n_valutabili += 1
        if guardia is not True:
            continue
        n_soppressi += 1
        if intent.get("trade_id") is None:
            n_soppressi_non_eseguiti += 1
            continue
        n_soppressi_eseguiti += 1
        pnl = _optional_float(intent.get("pnl_realizzato"))
        if pnl is None:
            n_soppressi_senza_pnl += 1
        else:
            somma_pnl += pnl
            n_soppressi_con_pnl += 1

    return {
        "n_intenti": len(intents),
        "n_valutabili": n_valutabili,
        "n_soppressi": n_soppressi,
        "n_soppressi_eseguiti": n_soppressi_eseguiti,
        "n_soppressi_non_eseguiti": n_soppressi_non_eseguiti,
        "n_soppressi_con_pnl": n_soppressi_con_pnl,
        "n_soppressi_senza_pnl": n_soppressi_senza_pnl,
        "somma_pnl_realizzato_soppressi": round(somma_pnl, 6),
        "matching": "s4_intent_events.intent_id -> trades nel decision_slot",
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
