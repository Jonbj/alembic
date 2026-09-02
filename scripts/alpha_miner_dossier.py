#!/usr/bin/env python3
"""Dossier deterministico per il report alpha-miner (#174).

Orchestratore SOTTILE: fa l'I/O (Alpaca, Postgres) e delega OGNI calcolo ai
moduli puri in `src/analysis/dossier/`. Nessuna formula vive qui.

Perche' esiste: il report alpha-miner e' generato da una sessione LLM che finora
ri-derivava ogni numero da capo ogni mattina. Due conseguenze misurate — la
soglia mover e' stata motivata in modo diverso in report diversi, e il confronto
con i giorni precedenti era prosa a memoria (un report ha dichiarato di non aver
riletto gli altri). Qui i numeri si calcolano una volta, in modo riproducibile, e
la sessione li interpreta invece di rifarli.

Sola lettura su Postgres e Alpaca. Non tocca MAI findings.json: quello e' scritto
solo dalle sessioni, con il protocollo del ledger.

Uso:
    set -a; source .env; set +a
    uv run python scripts/alpha_miner_dossier.py 2026-08-04
    uv run python scripts/alpha_miner_dossier.py --backfill-da 2026-08-03
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import statistics
import subprocess
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

import yaml

from src.analysis.dossier.book import (
    SOGLIA_GUARDIA_CONTRADDIZIONE,
    aggregate_by_entry_hour,
    aggregate_contradiction_guard,
    compute_entries,
    compute_exits,
    compute_s4_entry_intents,
)
from src.analysis.dossier.decision_signal_id_coverage import (
    build_signal_id_coverage as build_signal_id_coverage_panel,
)
from src.analysis.dossier.decision_quality import (
    build_decision_quality_panel,
    build_opening_snapshot,
)
from src.analysis.dossier.article_coverage import build_article_coverage
from src.analysis.dossier.article_coverage import canonical_article_id
from src.analysis.dossier.exit_coverage import build_exit_coverage
from src.analysis.dossier.event_context import (
    CONTEXT_VERSION,
    SECTOR_ETF_BY_SECTOR,
    build_event_market_context,
)
from src.analysis.dossier.market import compute_market, compute_miss_candidates
from src.analysis.dossier.miss_cause import (
    DEFAULT_SOGLIA_GATE,
    cause_del_giorno,
    classify_miss_candidates,
)
from src.analysis.dossier.opportunity import ESTIMATOR_VERSION, compute_opportunity
from src.analysis.dossier.timeline import build_timeline

log = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_DIR / "docs" / "evidence" / "dossier"
SOGLIA_MOVER = 0.03
FINESTRA_MEDIANE = 20  # giorni, per le mediane mobili
# Sedute su cui si misura lo streak di copertura nulla lato uscita (#324).
# Dieci sedute bastano a distinguere una giornata muta da un buco strutturale
# senza far crescere la query oltre un indice su (ticker, fetched_at).
FINESTRA_SEDUTE_COPERTURA = 10
INIZIO_OSSERVAZIONE = date(2026, 8, 3)
DOSSIER_SCHEMA_VERSION = "2.6"
NEW_YORK = ZoneInfo("America/New_York")


class GiornoNonBorsa(SystemExit):
    """Giorno saltato legittimamente: il calendario conferma il mercato chiuso.

    Distingue lo skip benigno dal fallimento di query (#396): ``main()`` la tratta
    come giorno non lavorabile, mentre una ``SystemExit`` generica (es.
    "Query fallita: ...") e' un errore reale che deve far uscire il cron non-zero.
    Resta sottoclasse di ``SystemExit`` per compatibilita' con i chiamanti che
    catturavano gia' ``SystemExit`` come skip di giornata.
    """


# Size plausibile di uno slot S4 per lo stimatore v2 (#280): fixed-slot sizing
# = bucket_pct(0.10) / n_top(5) = 2% di NAV. ~$2.200 sul conto paper da ~$110k
# (la stessa base del prompt alpha-miner). La size e' un'assunzione congetturale
# (nessun trade reale su un miss) ed e' dichiarata nella stima; la NAV dinamica
# reale e' wiring post-freeze. Costante versionata, non una taratura.
SLOT_FRACTION_S4 = 0.10 / 5  # bucket_pct / n_top (src/strategies/s4/config.py)
SLOT_USD_DEFAULT = 2200.0

# Cicli da 15 minuti in cui il motore puo' agire: il beat di `portfolio-cycle`
# gira a :07/:22/:37/:52 fra le 14 e le 21 UTC (src/workers/celery_app.py).
# Il primo istante in cui il motore avrebbe POTUTO comprare qualcosa e' 14:07 UTC.
CICLI_MINUTI_UTC = (7, 22, 37, 52)
CICLI_ORE_UTC = range(14, 22)
PRIMO_CICLO_SEDUTA_UTC = time(14, 7)

# Tre fonti dichiarate per il ciclo eleggibile, mai fuse fra loro: sono tre
# popolazioni diverse e vanno lette come tali (#246).
ELIGIBLE_SOURCE_DECISION = "execution_decisions.tick_time"      # decisione osservata
ELIGIBLE_SOURCE_SEGNALE = "primo_ciclo_dopo_segnale"            # segnale, nessuna decisione
ELIGIBLE_SOURCE_SESSION_OPEN = "session_open"                   # nessun segnale (NO_NEWS)
ELIGIBLE_SOURCE_NESSUN_CICLO = "nessun_ciclo_dopo_il_segnale"   # segnale a seduta finita


def _psql(query: str) -> list[list[str]]:
    """Query read-only su Postgres. Righe come liste di stringhe."""
    res = subprocess.run(
        ["docker", "exec", "alembic-postgres-1", "psql", "-U", "trading", "-d",
         "trading", "-t", "-A", "-F", "|", "-c", query],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        raise SystemExit(f"Query fallita: {res.stderr.strip()[:300]}")
    return [r.split("|") for r in res.stdout.strip().split("\n") if r.strip()]


def _watchlist() -> list[str]:
    with open(PROJECT_DIR / "config" / "trading.yaml") as f:
        return list(yaml.safe_load(f)["symbols"]["watchlist"])


def _sector_by_ticker() -> dict[str, str]:
    """Inverte la tassonomia settoriale gia' dichiarata in trading.yaml."""
    with open(PROJECT_DIR / "config" / "trading.yaml") as f:
        sectors = yaml.safe_load(f).get("sectors") or {}
    return {
        str(symbol): str(sector)
        for sector, symbols in sectors.items()
        for symbol in (symbols or [])
    }


def _soglia_gate_s4() -> float:
    """Legge la soglia feedback di S4 da Redis con fallback al baseline (#208).

    Il dossier osserva le evidenze, non comanda il gate: usa la STESSA fonte
    del gate runtime (`feedback:entry_threshold:S4`, con fallback alla chiave
    legacy) e lo stesso fallback al baseline (0.30). Se Redis e' irraggiungibile,
    logga e usa il baseline: meglio un dossier sulla soglia baseline che un
    crash che blocca il cron.

    NON legge `threshold_ratchet_enabled` (#191): quella flag riguarda solo
    l'innalzamento automatico della leva; il dossier deve sempre vedere il
    valore EFFETTIVO del giorno, anche quando il ratchet e' bloccato.
    """
    try:
        from redis import Redis as _R
        _r = _R.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
                         decode_responses=True)
        try:
            raw = _r.get("feedback:entry_threshold:S4")
            if raw is None:
                raw = _r.get("feedback:entry_threshold")
            if raw is not None:
                return float(raw)
        finally:
            _r.close()
    except Exception as exc:
        log.warning("Redis non raggiungibile per la soglia S4 (%s) — uso baseline %.2f",
                    exc, DEFAULT_SOGLIA_GATE)
    return DEFAULT_SOGLIA_GATE


def _barre(simboli: list[str], giorno: date) -> dict[str, dict]:
    """Barre giornaliere, precedente e ADV20 per universo e soli benchmark.

    Feed SIP: e' la consolidata che copre il 100% del volume. IEX e' un singolo
    mercato e su storico lungo ha giorni interi mancanti (misurato su SPY: manca
    il 2019, 111 barre nel 2020). Per il periodo di osservazione i due
    coinciderebbero, ma usare la consolidata evita di dover cambiare fonte se un
    giorno il dossier viene ricalcolato all'indietro.
    """
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    chiave, segreto = os.environ.get("ALPACA_API_KEY"), os.environ.get("ALPACA_SECRET_KEY")
    if not chiave or not segreto:
        raise SystemExit("ALPACA_API_KEY / ALPACA_SECRET_KEY mancanti (.env non caricato?)")

    client = StockHistoricalDataClient(chiave, segreto)
    req = StockBarsRequest(
        symbol_or_symbols=simboli,
        timeframe=TimeFrame.Day,
        # 45 giorni di calendario coprono almeno 20 sedute anche attorno alle
        # festivita'. L'ADV resta None se il feed non ne fornisce comunque 20.
        start=datetime.combine(giorno - timedelta(days=45), datetime.min.time()),
        # mai oltre oggi: il SIP rifiuta le richieste che toccano gli ultimi 15
        # minuti, e il rifiuto uccide l'intera chiamata, non la sola ultima barra.
        end=datetime.combine(min(giorno + timedelta(days=1), date.today()), datetime.min.time()),
        feed="sip",
        adjustment="all",
    )
    df = client.get_stock_bars(req).df
    if df is None or df.empty:
        # Un feed vuoto non prova che il mercato fosse chiuso: puo' essere un
        # guasto o un buco dati. La classificazione autorevole viene fatta da
        # ``costruisci_dossier`` contro il calendario Alpaca (#396).
        return {}

    out: dict[str, dict] = {}
    for sym in simboli:
        try:
            serie = df.loc[sym]
        except KeyError:
            continue
        righe = {i.date(): r for i, r in serie.iterrows()}
        if giorno not in righe:
            continue
        precedenti = sorted(d for d in righe if d < giorno)
        r = righe[giorno]
        volumi_precedenti = [
            float(righe[d]["volume"])
            for d in precedenti[-20:]
            if righe[d].get("volume") is not None
        ]
        out[sym] = {
            "open": float(r["open"]), "high": float(r["high"]),
            "low": float(r["low"]), "close": float(r["close"]),
            "close_prec": float(righe[precedenti[-1]]["close"]) if precedenti else None,
            "volume": int(r["volume"]) if r.get("volume") is not None else None,
            "adv_20d": (
                statistics.fmean(volumi_precedenti)
                if len(volumi_precedenti) == 20
                else None
            ),
            "adv_20d_observations": len(volumi_precedenti),
        }
    return out


def _barre_intraday(
    simboli: list[str], giorno: date, primo_evento: datetime | None = None
) -> tuple[dict[str, list[dict]], datetime]:
    """Barre SIP a 5 minuti dal primo evento (o dalle 04:00) alle 20:00 New York.

    Il cutoff e' il minore fra fine after-market e l'istante corrente: anche
    una esecuzione accidentale sul giorno in corso non puo' leggere il futuro.
    Anticipare l'inizio al primo evento conserva il vero primo prezzo per una
    notizia pubblicata nella seduta precedente.
    """
    inizio_sessione = datetime.combine(giorno, time(4, 0), tzinfo=NEW_YORK).astimezone(
        timezone.utc
    )
    inizio = min(inizio_sessione, primo_evento) if primo_evento else inizio_sessione
    fine_sessione = datetime.combine(giorno, time(20, 0), tzinfo=NEW_YORK).astimezone(
        timezone.utc
    )
    cutoff = min(fine_sessione, datetime.now(timezone.utc))
    if not simboli or cutoff <= inizio:
        return {}, cutoff

    from alpaca.data.enums import Adjustment, DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    chiave, segreto = os.environ.get("ALPACA_API_KEY"), os.environ.get("ALPACA_SECRET_KEY")
    if not chiave or not segreto:
        raise SystemExit("ALPACA_API_KEY / ALPACA_SECRET_KEY mancanti (.env non caricato?)")

    client = StockHistoricalDataClient(chiave, segreto)
    req = StockBarsRequest(
        symbol_or_symbols=simboli,
        timeframe=TimeFrame(5, TimeFrameUnit.Minute),
        start=inizio,
        end=cutoff,
        feed=DataFeed.SIP,
        adjustment=Adjustment.ALL,
    )
    df = getattr(client.get_stock_bars(req), "df", None)
    if df is None or df.empty:
        return {}, cutoff

    out: dict[str, list[dict]] = defaultdict(list)
    unico = simboli[0] if len(simboli) == 1 else None
    for indice, row in df.iterrows():
        if isinstance(indice, tuple):
            symbol, timestamp = str(indice[0]), indice[-1]
        elif unico is not None:
            symbol, timestamp = unico, indice
        else:
            continue
        if hasattr(timestamp, "to_pydatetime"):
            timestamp = timestamp.to_pydatetime()
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        out[symbol].append({
            "timestamp": timestamp.astimezone(timezone.utc),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": int(row["volume"]) if row.get("volume") is not None else None,
        })
    for bars in out.values():
        bars.sort(key=lambda bar: bar["timestamp"])
    return dict(out), cutoff


def _timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _regular_session_bounds(giorno: date) -> tuple[datetime, datetime]:
    """Apertura/chiusura regular session NY, convertite in UTC.

    La conversione via ZoneInfo conserva automaticamente EDT/EST. I dossier
    vengono prodotti solo dopo che `_barre` ha verificato il giorno di borsa;
    nella finestra #171 non cadono sedute half-day.
    """
    open_ny = datetime.combine(giorno, time(9, 30), tzinfo=NEW_YORK)
    close_ny = datetime.combine(giorno, time(16, 0), tzinfo=NEW_YORK)
    return open_ny.astimezone(timezone.utc), close_ny.astimezone(timezone.utc)


def _sedute_di_borsa(giorno: date, n: int) -> list[str]:
    """Ultime `n` sedute di borsa che finiscono nel `giorno`, dal calendario Alpaca.

    Serve allo streak di copertura nulla (#324): contare giorni di calendario
    conterebbe i weekend come sedute mute. `Calendar.date` e' gia' una data di
    calendario di borsa (New York), non un timestamp da convertire (#372).

    Fallisce APERTO: se il calendario non risponde restituisce la lista vuota, e il
    modulo puro lascia lo streak a None (UNKNOWN). Un dossier senza streak vale piu'
    di un cron che si ferma.
    """
    try:
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import GetCalendarRequest

        chiave = os.environ.get("ALPACA_API_KEY")
        segreto = os.environ.get("ALPACA_SECRET_KEY")
        if not chiave or not segreto:
            raise RuntimeError("ALPACA_API_KEY / ALPACA_SECRET_KEY mancanti")
        # Il calendario di borsa e' identico su paper e live: si segue comunque la
        # modalita' dichiarata, per non aprire una sessione live da uno strumento
        # di sola misura.
        paper = os.environ.get("ALPACA_PAPER_MODE", "true").lower() == "true"
        client = TradingClient(chiave, segreto, paper=paper)
        # 3n giorni di calendario coprono n sedute anche con una settimana di feste.
        righe = client.get_calendar(
            GetCalendarRequest(start=giorno - timedelta(days=3 * n), end=giorno)
        )
        sedute = sorted(
            riga.date.isoformat() for riga in righe if not isinstance(riga, str)
        )
        return sedute[-n:]
    except Exception as exc:
        log.warning("Calendario di borsa non disponibile (%s) — streak copertura UNKNOWN", exc)
        return []


def _righe_news_per_seduta(
    tickers: Sequence[str], sedute: Sequence[str]
) -> tuple[dict[str, dict[str, int]], dict[str, list[str]]]:
    """Righe `news_log` per (ticker, seduta) e fonti che hanno prodotto qualcosa.

    `fetched_at` e' l'istante di ingestione, non di pubblicazione: e' la stessa colonna
    del conteggio giornaliero che alimenta `mercato.watchlist_zero_news`, quindi le due
    misure restano confrontabili. L'ingestione gira 14:00-21:00 UTC (10:00-17:00 New
    York), percio' bucket UTC e data di seduta NY coincidono su ogni riga reale;
    `AT TIME ZONE 'UTC'` lo rende indipendente dal fuso della sessione psql.

    Le fonti servono a distinguere *zero resa del provider* da *fonte non configurata*
    (#324 §2): i connettori per-ticker vivi interrogano l'INTERA watchlist, quindi una
    lista vuota qui e' una resa nulla, non un buco di configurazione.
    """
    if not tickers or not sedute:
        return {}, {}
    lista = ",".join("'" + t.replace("'", "''") + "'" for t in sorted(set(tickers)))
    righe: dict[str, dict[str, int]] = defaultdict(dict)
    fonti: dict[str, set[str]] = defaultdict(set)
    for row in _psql(
        f"SELECT ticker, (fetched_at AT TIME ZONE 'UTC')::date::text, source, "
        f"count(*)::text FROM news_log WHERE ticker IN ({lista}) "
        f"AND fetched_at >= '{sedute[0]}' "
        f"AND fetched_at < '{sedute[-1]}'::date + 1 GROUP BY 1,2,3;"
    ):
        ticker, seduta, fonte, conteggio = row[0], row[1], row[2], int(row[3])
        righe[ticker][seduta] = righe[ticker].get(seduta, 0) + conteggio
        fonti[ticker].add(fonte)
    return dict(righe), {t: sorted(v) for t, v in fonti.items()}


def _opening_positions(giorno: date) -> list[dict]:
    """Posizioni vive all'apertura RTH, lette senza modificare il book."""
    session_open, _session_close = _regular_session_bounds(giorno)
    open_iso = session_open.isoformat()
    rows = _psql(
        f"SELECT id::text, symbol, "
        f"CASE WHEN stop_strategy IS NOT NULL THEN stop_strategy "
        f"WHEN signal_id IS NOT NULL THEN 'S4' ELSE 'CONTAMINAZIONE' END, "
        # #397: per le righe ancora aperte usa la quantita' viva
        # (quantity_remaining, ricalcolata dai fill SELL broker) non quella
        # d'ingresso mai decrementata (firma fantasma 74x). Per le righe gia'
        # chiuse oggi mantiene qty (= quantita' fill di uscita): COALESCE qui
        # renderebbe 0 e cancellerebbe la posizione dal book MTM della giornata.
        f"CASE WHEN exit_time IS NULL THEN COALESCE(quantity_remaining, qty) "
        f"ELSE qty END::text, "
        f"entry_price::text, entry_time::text, "
        f"COALESCE(exit_time::text,''), COALESCE(exit_price::text,''), "
        f"COALESCE(array_to_string(COALESCE(exit_order_ids, "
        f"CASE WHEN exit_order_id IS NULL THEN ARRAY[]::text[] "
        f"ELSE ARRAY[exit_order_id] END), chr(31)),'') "
        f"FROM trades WHERE entry_time < '{open_iso}' "
        f"AND (exit_time IS NULL OR exit_time >= '{open_iso}') ORDER BY id;"
    )
    return [
        {
            "trade_id": int(row[0]),
            "symbol": row[1],
            "strategia": row[2],
            "qty": float(row[3]) if row[3] else None,
            "entry_price": float(row[4]) if row[4] else None,
            "entry_time": row[5] or None,
            "exit_time": row[6] or None,
            "exit_price": float(row[7]) if row[7] else None,
            "exit_order_ids": [value for value in row[8].split(chr(31)) if value],
        }
        for row in rows
    ]


def _guard_decisions(giorno: date) -> list[dict]:
    """Controfattuali osservati dei guard, con missingness del notional onesta.

    Solo SKIP_PYRAMIDING dal 19/08 porta in ``score`` la frazione di NAV
    effettivamente bloccata (#315 e carta #171). Per le altre righe il return e'
    misurabile ma il notional non lo e': resta NULL, mai sostituito da una size
    inventata. Lo snapshot NAV e' il piu' recente entro dieci minuti dal guard.
    """
    g = giorno.isoformat()
    rows = _psql(
        f"SELECT ed.id::text, ed.tick_time::text, ed.symbol, "
        f"COALESCE(ed.signal_id::text,''), ed.decision, "
        f"COALESCE(ed.counterfactual_return_1h::text,''), "
        f"COALESCE(ed.counterfactual_return_overnight::text,''), "
        f"COALESCE(ed.counterfactual_skip_reason,''), "
        f"COALESCE(ed.counterfactual_computed_at::text,''), "
        f"COALESCE(CASE WHEN ed.decision = 'SKIP_PYRAMIDING' "
        f"AND ed.tick_time::date >= DATE '2026-08-19' AND snap.nav IS NOT NULL "
        f"THEN ABS(ed.score) * snap.nav END::text,'') "
        f"FROM execution_decisions ed "
        f"LEFT JOIN LATERAL (SELECT nav FROM portfolio_monitor_snapshots "
        f"WHERE as_of <= ed.tick_time AND as_of >= ed.tick_time - INTERVAL '10 minutes' "
        f"AND nav IS NOT NULL ORDER BY as_of DESC LIMIT 1) snap ON true "
        f"WHERE ed.tick_time >= '{g}' AND ed.tick_time < '{g}'::date + 1 "
        f"AND ed.decision IN ('SKIP_THRESHOLD','SKIP_EMA','SKIP_CAP','SKIP_PYRAMIDING') "
        f"ORDER BY ed.tick_time, ed.id;"
    )
    return [
        {
            "decision_id": int(row[0]),
            "tick_time": row[1],
            "symbol": row[2],
            "signal_id": int(row[3]) if row[3] else None,
            "decision": row[4],
            "counterfactual_return_1h": float(row[5]) if row[5] else None,
            "counterfactual_return_overnight": float(row[6]) if row[6] else None,
            "counterfactual_skip_reason": row[7] or None,
            "counterfactual_computed_at": row[8] or None,
            "intended_notional_usd": float(row[9]) if row[9] else None,
        }
        for row in rows
    ]


def _execution_decisions_signal_id_rows(giorno: date) -> list[dict]:
    """#406 — tutte le righe di execution_decisions nella seduta, con solo i
    due campi che il panel ``build_signal_id_coverage`` consuma. Nessun join,
    nessun aggregato: il panel aggrega localmente, cosi' la stessa query serve
    sia il dossier live sia i test del modulo senza dipendere dal DB.

    Carichiamo TUTTE le reason_code (non solo i guard) perche' il difetto
    principale — il 100% di SELL con signal_id NULL — era proprio su una riga
    che ``_guard_decisions`` non include.
    """
    g = giorno.isoformat()
    rows = _psql(
        f"SELECT ed.decision, ed.signal_id::text "
        f"FROM execution_decisions ed "
        f"WHERE ed.tick_time >= '{g}' AND ed.tick_time < '{g}'::date + 1"
    )
    return [
        {
            "reason_code": row[0],
            "signal_id": int(row[1]) if row[1] else None,
        }
        for row in rows
    ]


def _news_label_columns() -> set[str]:
    """Colonne disponibili: il DB live puo' precedere migration 046.

    Sul vecchio schema ogni URL ha una sola label umana; sul nuovo schema le
    annotazioni sono due e solo la riga adjudicated e' ground truth. Il reader
    deve capire entrambe le forme senza applicare migrazioni o scrivere dati.
    """
    return {
        row[0]
        for row in _psql(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'news_labels';"
        )
    }


def _article_coverage_rows(giorno: date) -> list[dict]:
    """Righe articolo+ticker e tutti i segnali del giorno per #279.

    Il FULL JOIN include sia news ingerite ma mai scorate, sia segnali collegati
    ad articoli ingeriti prima della giornata. Sullo schema multi-annotatore le
    label entrano solo dopo adjudication; lo schema legacy aveva invece una
    singola label finale per URL.
    """
    g = giorno.isoformat()
    label_columns = _news_label_columns()
    if "adjudicated" in label_columns:
        news_log_match = (
            "l.news_log_id = nl.id OR (l.news_log_id IS NULL AND l.url = nl.url)"
            if "news_log_id" in label_columns
            else "l.url = nl.url"
        )
        label_lateral = (
            "LEFT JOIN LATERAL ("
            "  SELECT l.gt_relevance, l.gt_tickers FROM news_labels l "
            "  WHERE l.status = 'labeled' AND l.adjudicated "
            f"    AND ({news_log_match}) "
            "  ORDER BY l.label_date DESC NULLS LAST, l.label_id DESC LIMIT 1"
            ") lbl ON true "
        )
    elif {"gt_relevance", "gt_tickers", "url"} <= label_columns:
        # Schema 029: UNIQUE(url), un solo annotatore. Questa e' gia' la label
        # finale; `adjudicated` non esiste ancora.
        label_lateral = (
            "LEFT JOIN LATERAL ("
            "  SELECT l.gt_relevance, l.gt_tickers FROM news_labels l "
            "  WHERE l.status = 'labeled' AND l.url = nl.url "
            "  ORDER BY l.label_date DESC NULLS LAST, l.label_id DESC LIMIT 1"
            ") lbl ON true "
        )
    else:
        label_lateral = (
            "LEFT JOIN LATERAL (SELECT NULL::text AS gt_relevance, "
            "NULL::text[] AS gt_tickers WHERE false) lbl ON true "
        )
    rows = _psql(
        f"/* article_coverage_279 */ SELECT COALESCE(nl.id::text,''), COALESCE(ss.id::text,''), "
        f"COALESCE(ss.symbol,nl.ticker,''), "
        f"translate(COALESCE(nl.title,''), '|' || chr(10) || chr(13), '   '), "
        f"translate(COALESCE(nl.body_snippet,''), '|' || chr(10) || chr(13), '   '), "
        f"translate(COALESCE(nl.url,''), '|' || chr(10) || chr(13), '   '), "
        f"COALESCE(nl.source,''), COALESCE(nl.published_at::text,''), "
        f"COALESCE(nl.raw_ingested_at::text,''), COALESCE(nl.content_hash,''), "
        f"COALESCE(nl.extraction_method,''), COALESCE(ss.score::text,''), "
        f"COALESCE(lbl.gt_relevance,''), "
        f"COALESCE(array_to_string(lbl.gt_tickers, ','),''), "
        f"COALESCE(issuer.terms,'') "
        f"FROM news_log nl "
        f"FULL JOIN sentiment_signals ss ON ss.news_log_id = nl.id "
        f"AND ss.generated_at >= '{g}' AND ss.generated_at < '{g}'::date + 1 "
        f"{label_lateral}"
        f"LEFT JOIN LATERAL ("
        f"  SELECT string_agg(concat_ws(chr(31), t.company_name, "
        f"         array_to_string(t.aliases, chr(31))), chr(31) ORDER BY t.company_name) terms "
        f"  FROM ticker_lookup t WHERE t.ticker = COALESCE(ss.symbol,nl.ticker)"
        f") issuer ON true "
        f"WHERE (nl.fetched_at >= '{g}' AND nl.fetched_at < '{g}'::date + 1) "
        f"OR (ss.generated_at >= '{g}' AND ss.generated_at < '{g}'::date + 1) "
        f"ORDER BY COALESCE(nl.id,0), COALESCE(ss.id,0);"
    )
    out: list[dict] = []
    for row in rows:
        out.append({
            "news_log_id": int(row[0]) if row[0] else None,
            "signal_id": int(row[1]) if row[1] else None,
            "ticker": row[2],
            "title": row[3],
            "body_snippet": row[4],
            "url": row[5],
            "source": row[6],
            "published_at": _timestamp(row[7]),
            "first_seen_at": _timestamp(row[8]),
            "content_hash": row[9],
            "extraction_method": row[10],
            "score": float(row[11]) if row[11] else None,
            "ground_truth_relevance": row[12] or None,
            "ground_truth_tickers": [v for v in row[13].split(",") if v],
            "issuer_terms": [v for v in row[14].split(chr(31)) if v],
        })
    return out


def _context_articles(rows: list[dict], coverage: dict) -> list[dict]:
    """Proietta le righe #279 nel contratto evento senza riclassificarle."""
    relevance: dict[tuple[str, str], str] = {}
    for article in coverage.get("articoli") or []:
        canonical_id = str(article["canonical_article_id"])
        for ticker, category in (article.get("relevance_by_ticker") or {}).items():
            relevance[(canonical_id, str(ticker).upper())] = str(category)

    return [
        {
            "ticker": str(row.get("ticker") or "").upper(),
            "title": row.get("title") or "",
            "canonical_article_id": canonical_article_id(row),
            "relevance": relevance.get(
                (canonical_article_id(row), str(row.get("ticker") or "").upper()),
                "UNKNOWN",
            ),
            "source": row.get("source") or "UNKNOWN",
        }
        for row in rows
        if row.get("ticker")
    ]


def _regime_observations(giorno: date) -> list[dict]:
    """Moltiplicatori realmente osservati nei cicli del giorno, sola lettura."""
    g = giorno.isoformat()
    return [
        {
            "observed_at": _timestamp(row[0]),
            "multiplier": float(row[1]),
            "source": "execution_decisions.regime_mult",
        }
        for row in _psql(
            f"SELECT tick_time::text, regime_mult::text FROM execution_decisions "
            f"WHERE tick_time >= '{g}' AND tick_time < '{g}'::date + 1 "
            f"AND regime_mult IS NOT NULL ORDER BY tick_time, id;"
        )
    ]


def _vix_observation(giorno: date) -> dict | None:
    """Ultimo VIX FRED disponibile non successivo al giorno analizzato."""
    import httpx

    inizio = (giorno - timedelta(days=7)).isoformat()
    fine = giorno.isoformat()
    api_key = os.environ.get("FRED_API_KEY", "")
    try:
        if api_key:
            response = httpx.get(
                "https://api.stlouisfed.org/fred/series/observations",
                params={
                    "series_id": "VIXCLS",
                    "api_key": api_key,
                    "file_type": "json",
                    "observation_start": inizio,
                    "observation_end": fine,
                    "sort_order": "desc",
                    "limit": 10,
                },
                timeout=10.0,
            )
            response.raise_for_status()
            observations = response.json().get("observations") or []
            valid = [row for row in observations if row.get("value") not in (None, ".")]
            if not valid:
                return None
            row = valid[0]
            return {
                "value": float(row["value"]),
                "observed_on": row["date"],
                "source": "FRED:VIXCLS",
            }

        response = httpx.get(
            "https://fred.stlouisfed.org/graph/fredgraph.csv",
            params={"id": "VIXCLS", "cosd": inizio, "coed": fine},
            timeout=10.0,
        )
        response.raise_for_status()
        valid_rows = []
        for line in response.text.strip().splitlines()[1:]:
            parts = line.split(",", 1)
            if len(parts) == 2 and parts[1] not in ("", "."):
                valid_rows.append(parts)
        if not valid_rows:
            return None
        observed_on, value = valid_rows[-1]
        return {"value": float(value), "observed_on": observed_on, "source": "FRED:VIXCLS"}
    except Exception as exc:
        log.warning("VIX FRED non disponibile per %s: %s", giorno, exc)
        return None


def _corporate_calendar(giorno: date, simboli: list[str]) -> dict:
    """Calendario earnings FMP + corporate actions Alpaca, senza scritture."""
    events: list[dict] = []
    successful_sources: list[str] = []
    missingness: list[str] = []
    universe = {str(symbol).upper() for symbol in simboli}

    fmp_key = os.environ.get("FMP_API_KEY", "")
    if fmp_key:
        try:
            import httpx

            response = httpx.get(
                "https://financialmodelingprep.com/stable/earnings-calendar",
                params={"from": giorno.isoformat(), "to": giorno.isoformat(), "apikey": fmp_key},
                timeout=15.0,
            )
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, list):
                successful_sources.append("FMP earnings-calendar")
                for row in payload:
                    symbol = str(row.get("symbol") or "").upper()
                    if symbol in universe:
                        events.append({
                            "symbol": symbol,
                            "event_type": "earnings",
                            "event_date": str(row.get("date") or giorno.isoformat()),
                            "time": row.get("time"),
                            "source": "FMP earnings-calendar",
                        })
            else:
                missingness.append("earnings_calendar_invalid_response")
        except Exception as exc:
            log.warning("Calendario earnings FMP non disponibile per %s: %s", giorno, exc)
            missingness.append("earnings_calendar_unavailable")
    else:
        missingness.append("earnings_calendar_unavailable")

    alpaca_key = os.environ.get("ALPACA_API_KEY", "")
    alpaca_secret = os.environ.get("ALPACA_SECRET_KEY", "")
    if alpaca_key and alpaca_secret:
        try:
            from alpaca.data.historical.corporate_actions import CorporateActionsClient
            from alpaca.data.requests import CorporateActionsRequest

            client = CorporateActionsClient(alpaca_key, alpaca_secret)
            result = client.get_corporate_actions(CorporateActionsRequest(
                symbols=sorted(universe), start=giorno, end=giorno
            ))
            successful_sources.append("Alpaca Corporate Actions API")
            for action_type, actions in (getattr(result, "data", {}) or {}).items():
                for action in actions:
                    symbol = next(
                        (
                            str(getattr(action, field)).upper()
                            for field in ("symbol", "source_symbol", "old_symbol", "new_symbol")
                            if getattr(action, field, None)
                        ),
                        "",
                    )
                    if symbol not in universe:
                        continue
                    event_date = next(
                        (
                            getattr(action, field)
                            for field in ("process_date", "ex_date", "payable_date", "record_date")
                            if getattr(action, field, None)
                        ),
                        giorno,
                    )
                    normalised = str(action_type).casefold()
                    if "merger" in normalised:
                        event_type = "merger"
                    elif "split" in normalised:
                        event_type = "split"
                    elif "dividend" in normalised:
                        event_type = "dividend"
                    elif "spin" in normalised:
                        event_type = "spinoff"
                    else:
                        event_type = "corporate_action"
                    events.append({
                        "symbol": symbol,
                        "event_type": event_type,
                        "event_date": event_date.isoformat() if hasattr(event_date, "isoformat") else str(event_date),
                        "action_type": action_type,
                        "source": "Alpaca Corporate Actions API",
                    })
        except Exception as exc:
            log.warning("Corporate actions Alpaca non disponibili per %s: %s", giorno, exc)
            missingness.append("corporate_actions_calendar_unavailable")
    else:
        missingness.append("corporate_actions_calendar_unavailable")

    unique = {
        (row["symbol"], row["event_type"], row["event_date"], row["source"]): row
        for row in events
    }
    required = {"FMP earnings-calendar", "Alpaca Corporate Actions API"}
    return {
        "events": [unique[key] for key in sorted(unique)],
        "sources_succeeded": successful_sources,
        "complete": required <= set(successful_sources),
        "missingness": missingness,
    }


def _halt_events(articles: list[dict]) -> list[dict]:
    """Soli halt affermati da una fonte; l'assenza resta UNKNOWN a valle."""
    pattern = re.compile(r"\b(trading halt(?:ed)?|halted trading|trading resumes?)\b", re.I)
    return [
        {
            "symbol": article["ticker"],
            "event_type": "halt_news_evidence",
            "canonical_article_id": article.get("canonical_article_id"),
            "source": article.get("source") or "UNKNOWN",
        }
        for article in articles
        if pattern.search(str(article.get("title") or ""))
    ]


def _nbbo_at_cycles(cycles: dict[str, dict], cutoff: datetime) -> dict[str, dict]:
    """Prima quota SIP dopo il ciclo eleggibile, una finestra di cinque minuti."""
    if not cycles:
        return {}
    from alpaca.data.enums import DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockQuotesRequest

    key = os.environ.get("ALPACA_API_KEY", "")
    secret = os.environ.get("ALPACA_SECRET_KEY", "")
    if not key or not secret:
        return {}
    client = StockHistoricalDataClient(key, secret)
    out: dict[str, dict] = {}
    for symbol, cycle in sorted(cycles.items()):
        at = cycle.get("at")
        if at is None or at >= cutoff:
            continue
        try:
            response = client.get_stock_quotes(StockQuotesRequest(
                symbol_or_symbols=symbol,
                start=at,
                end=min(at + timedelta(minutes=5), cutoff),
                limit=1,
                feed=DataFeed.SIP,
            ))
            frame = getattr(response, "df", None)
            if frame is None or frame.empty:
                continue
            row = frame.iloc[0]
            index = frame.index[0]
            timestamp = index[-1] if isinstance(index, tuple) else index
            if hasattr(timestamp, "to_pydatetime"):
                timestamp = timestamp.to_pydatetime()
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            out[symbol] = {
                "timestamp": timestamp.astimezone(timezone.utc),
                "bid_price": float(row["bid_price"]),
                "ask_price": float(row["ask_price"]),
                "bid_size": float(row["bid_size"]) if row.get("bid_size") is not None else None,
                "ask_size": float(row["ask_size"]) if row.get("ask_size") is not None else None,
                "source": "Alpaca Market Data API / SIP quotes",
            }
        except Exception as exc:
            log.warning("NBBO %s non disponibile al ciclo %s: %s", symbol, at, exc)
    return out


def _timeline_eventi(giorno: date) -> list[dict]:
    """Join PIT articolo -> segnale -> prima decisione collegata -> trade."""
    g = giorno.isoformat()
    rows = _psql(
        f"SELECT ss.id, ss.symbol, ss.news_log_id, ss.score, ss.fallback_used, "
        f"nl.published_at, nl.raw_ingested_at, nl.fetched_at, ss.generated_at, "
        f"ed.id, ed.tick_time, COALESCE(od.order_id, t.entry_order_id), t.id "
        f"FROM sentiment_signals ss "
        f"LEFT JOIN news_log nl ON nl.id = ss.news_log_id "
        f"LEFT JOIN LATERAL ("
        f"  SELECT id, tick_time, order_id FROM execution_decisions "
        f"  WHERE signal_id = ss.id AND tick_time >= ss.generated_at "
        f"    AND tick_time < '{g}'::date + 1 "
        f"  ORDER BY tick_time LIMIT 1"
        f") ed ON true "
        f"LEFT JOIN LATERAL ("
        f"  SELECT id, order_id FROM execution_decisions "
        f"  WHERE signal_id = ss.id AND tick_time >= ss.generated_at "
        f"    AND tick_time < '{g}'::date + 1 AND order_id IS NOT NULL "
        f"  ORDER BY tick_time LIMIT 1"
        f") od ON true "
        f"LEFT JOIN LATERAL ("
        f"  SELECT id, entry_order_id FROM trades "
        f"  WHERE signal_id = ss.id AND entry_time >= ss.generated_at "
        f"    AND entry_time < '{g}'::date + 1 "
        f"  ORDER BY entry_time LIMIT 1"
        f") t ON true "
        f"WHERE ss.generated_at >= '{g}' "
        f"AND ss.generated_at < '{g}'::date + 1 "
        f"ORDER BY ss.symbol, ss.generated_at;"
    )
    return [{
        "signal_id": int(r[0]),
        "symbol": r[1],
        "news_log_id": int(r[2]) if r[2] else None,
        "score": float(r[3]),
        "fallback": r[4] == "t",
        "published_at": _timestamp(r[5]),
        # raw_ingested_at e' l'istante in cui il connettore ha visto/scaricato
        # l'articolo; fetched_at e' l'inserimento in news_log (migration 027/033).
        "first_seen_at": _timestamp(r[6]),
        "ingested_at": _timestamp(r[7]),
        "scored_at": _timestamp(r[8]),
        "eligible_cycle_at": _timestamp(r[10]),
        "order_id": r[11] or None,
        "trade_id": int(r[12]) if r[12] else None,
    } for r in rows]


def _s4_entry_intents(giorno: date) -> list[dict]:
    """Tutti i candidate intent S4 #294, inclusi scarti e mancati fill.

    Il join al trade e' confinato allo stesso decision slot da 15 minuti. In
    questo modo un segnale ri-osservato in cicli successivi non eredita il fill
    di un altro intento. `net_pnl` resta None sia per un intento non eseguito
    sia per un trade ancora aperto; `trade_id` distingue i due casi.
    """
    g = giorno.isoformat()
    rows = _psql(
        f"SELECT intent.intent_id::text, COALESCE(intent.signal_id::text,''), "
        f"intent.symbol, intent.model_generated_at::text, intent.decision_at::text, "
        f"COALESCE(intent.snapshot->>'score',''), "
        f"COALESCE(disposition.reason_code,''), "
        f"disposition.is_tradable, "
        f"COALESCE(trade.id::text,''), COALESCE(trade.net_pnl::text,'') "
        f"FROM s4_candidate_population intent "
        f"LEFT JOIN s4_intent_events disposition "
        f"  ON disposition.intent_id = intent.intent_id "
        f" AND disposition.event_type = 'disposition' "
        f"LEFT JOIN LATERAL ("
        f"  SELECT id, net_pnl FROM trades "
        f"  WHERE signal_id = intent.signal_id "
        f"    AND entry_time >= intent.decision_slot "
        f"    AND entry_time < intent.decision_slot + INTERVAL '15 minutes' "
        f"  ORDER BY entry_time, id LIMIT 1"
        f") trade ON true "
        f"WHERE intent.decision_at >= '{g}' "
        f"AND intent.decision_at < '{g}'::date + 1 "
        f"ORDER BY intent.decision_at, intent.intent_id;"
    )
    return [
        {
            "intent_id": row[0],
            "signal_id": int(row[1]) if row[1] else None,
            "symbol": row[2],
            "signal_at": row[3],
            "decision_at": row[4],
            "signal_score": float(row[5]) if row[5] else None,
            "final_reason_code": row[6] or None,
            "is_tradable": row[7] == "t" if row[7] else None,
            "trade_id": int(row[8]) if row[8] else None,
            "pnl_realizzato": float(row[9]) if row[9] else None,
        }
        for row in rows
    ]


def _s4_rank_invariante_ranks(giorno: date) -> list[dict]:
    """#401: post-hoc check sul ledger #294.

    Per ogni ``decision_slot`` della seduta, verifica che il ``rank`` registrato
    nelle disposition sia una funzione strettamente decrescente del
    ``ranking_score`` persistito nel candidate snapshot. Una violazione indica
    che il ledger e' corrotto: non e' piu' possibile ricostruire la selezione
    che ha prodotto un certo insieme di ordini (#294 + #401).

    Restituisce una lista (vuota quando tutto e' coerente) di violazioni con:
    ``decision_slot, signal_id, symbol, rank, ranking_score`` — una per ogni
    coppia (i, j) nello stesso slot tale che ``rank_i < rank_j`` ma
    ``ranking_score_i < ranking_score_j`` (la violazione del #401 originale).

    Il ranking_score puo' essere NULL per i candidate catturati prima del fix
    #401 o quando Redis era down al momento della cattura: in quel caso la
    coppia viene esclusa dal check (la sua assenza e' dichiarata in
    ``missingness``). La presenza massiccia di NULL e' essa stessa un segnale
    che il candidato e' stato scritto dal codice pre-#401.
    """
    g = giorno.isoformat()
    rows = _psql(
        f"SELECT disposition.decision_slot::text, "
        f"COALESCE(disposition.signal_id::text,''), "
        f"disposition.symbol, "
        f"COALESCE(disposition.rank::text,''), "
        f"COALESCE(candidate.snapshot->>'ranking_score',''), "
        f"COALESCE(candidate.snapshot->>'score','') "
        f"FROM s4_intent_events disposition "
        f"JOIN s4_intent_events candidate "
        f"  ON candidate.intent_id = disposition.intent_id "
        f" AND candidate.event_type = 'candidate' "
        f"WHERE disposition.event_type = 'disposition' "
        f"  AND disposition.rank IS NOT NULL "
        f"  AND candidate.snapshot ? 'ranking_score' "
        f"  AND disposition.decision_at >= '{g}' "
        f"  AND disposition.decision_at < '{g}'::date + 1 "
        f"ORDER BY disposition.decision_slot, disposition.rank;"
    )
    return [
        {
            "decision_slot": row[0],
            "signal_id": int(row[1]) if row[1] else None,
            "symbol": row[2],
            "rank": int(row[3]) if row[3] else None,
            "ranking_score": float(row[4]) if row[4] else None,
            "raw_score": float(row[5]) if row[5] else None,
        }
        for row in rows
    ]


def _invariante_rank_in_ranking_score(rows: list[dict]) -> list[dict]:
    """#401: per ogni ``decision_slot``, controlla che ``rank`` sia strettamente
    decrescente in ``ranking_score``.

    La regola "strettamente decrescente" ammette i pareggi (due simboli con lo
    stesso ranking_score possono avere rank diversi senza violare l'invariante).
    Una coppia (i, j) viola se ``rank_i < rank_j`` AND ``ranking_score_i <
    ranking_score_j`` (entrambe le diseguaglianze strette: se i punteggi sono
    uguali e i rank sono diversi, e' un pareggio consentito dal ranker).

    Restituisce la lista delle violazioni, una per coppia, ordinate per slot e
    poi per (rank_i, rank_j). Lista vuota == invariante rispettato.
    """
    by_slot: dict[str, list[dict]] = {}
    for row in rows:
        slot = row.get("decision_slot")
        ranking_score = row.get("ranking_score")
        rank = row.get("rank")
        if slot is None or ranking_score is None or rank is None:
            continue
        by_slot.setdefault(slot, []).append({**row, "_score": float(ranking_score), "_rank": int(rank)})
    violations: list[dict] = []
    for slot, entries in by_slot.items():
        entries.sort(key=lambda r: r["_rank"])
        for i, outer in enumerate(entries):
            for inner in entries[i + 1:]:
                if inner["_score"] > outer["_score"]:
                    violations.append({
                        "decision_slot": slot,
                        "rank_a": outer["_rank"],
                        "symbol_a": outer.get("symbol"),
                        "signal_id_a": outer.get("signal_id"),
                        "ranking_score_a": outer["_score"],
                        "rank_b": inner["_rank"],
                        "symbol_b": inner.get("symbol"),
                        "signal_id_b": inner.get("signal_id"),
                        "ranking_score_b": inner["_score"],
                    })
    return violations


def _dettagli_ordini(order_ids: list[str]) -> dict[str, dict]:
    """Timestamp submission/fill reali dal broker, con errore per-order esplicito."""
    if not order_ids:
        return {}

    from alpaca.trading.client import TradingClient
    from src.config import config

    if not config.ALPACA_API_KEY or not config.ALPACA_SECRET_KEY:
        return {
            order_id: {
                "submitted_at": None,
                "filled_at": None,
                "filled_avg_price": None,
                "filled_qty": None,
                "lookup_error": "alpaca_credentials_missing",
            }
            for order_id in order_ids
        }

    client = TradingClient(
        config.ALPACA_API_KEY,
        config.ALPACA_SECRET_KEY,
        paper=config.ALPACA_PAPER_MODE,
    )
    result: dict[str, dict] = {}
    for order_id in sorted(set(order_ids)):
        try:
            order = client.get_order_by_id(order_id)
            filled_avg = getattr(order, "filled_avg_price", None)
            filled_qty = getattr(order, "filled_qty", None)
            result[order_id] = {
                "submitted_at": getattr(order, "submitted_at", None),
                "filled_at": getattr(order, "filled_at", None),
                "filled_avg_price": float(filled_avg) if filled_avg is not None else None,
                "filled_qty": float(filled_qty) if filled_qty is not None else None,
                "lookup_error": None,
            }
        except Exception as exc:
            result[order_id] = {
                "submitted_at": None,
                "filled_at": None,
                "filled_avg_price": None,
                "filled_qty": None,
                "lookup_error": f"{type(exc).__name__}: {str(exc)[:160]}",
            }
    return result


def _e_giorno_di_borsa(giorno: date) -> bool:
    """Verifica una data contro il calendario di mercato autorevole di Alpaca.

    Questa verifica e' stretta: se il calendario non e' disponibile non possiamo
    qualificare l'assenza di barre come skip benigno, quindi il dossier deve
    fallire ad alta voce anziche' uscire 0 (#396).
    """
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import GetCalendarRequest

    chiave = os.environ.get("ALPACA_API_KEY")
    segreto = os.environ.get("ALPACA_SECRET_KEY")
    if not chiave or not segreto:
        raise SystemExit("ALPACA_API_KEY / ALPACA_SECRET_KEY mancanti (.env non caricato?)")

    paper = os.environ.get("ALPACA_PAPER_MODE", "true").lower() == "true"
    try:
        righe = TradingClient(chiave, segreto, paper=paper).get_calendar(
            GetCalendarRequest(start=giorno, end=giorno)
        )
    except Exception as exc:
        raise SystemExit(f"Calendario di borsa non disponibile per il {giorno}: {exc}") from exc

    if any(isinstance(riga, str) for riga in righe):
        raise SystemExit(f"Calendario di borsa non valido per il {giorno}: {righe}")
    return any(getattr(riga, "date", None) == giorno for riga in righe)


def _cutoff_giorno(giorno: date) -> str:
    """Bound point-in-time per l'exit: chiusura sessione regolare US (16:00 ET).

    Nella finestra di osservazione (2026-08-03 -> 2026-09-28) l'ET e' EDT
    (UTC-4), quindi 16:00 ET = 20:00 UTC. Deterministico e documentato: l'exit
    policy dichiarata e' EOD_close, e il prezzo di exit e' il close daily.
    """
    return f"{giorno.isoformat()}T20:00:00+00:00"


def _cicli_eleggibili(eventi: list[dict], giorno: date) -> dict[str, dict]:
    """Primo ciclo realmente eleggibile per simbolo, con la fonte dichiarata.

    Due fonti, mai confuse fra loro:
    - `execution_decisions.tick_time`: il ciclo in cui il motore ha davvero
      valutato quel segnale. E' il dato misurato.
    - `primo_ciclo_dopo_segnale`: il candidato ha un punteggio ma nessuna
      decisione registrata. Il ciclo e' il primo :07/:22/:37/:52 successivo al
      primo punteggio: prima di quello il motore non aveva niente da valutare.
    - `session_open`: il primo ciclo da 15 minuti della seduta (14:07 UTC), per i
      candidati senza nessun punteggio — i NO_NEWS. Non e' una decisione
      osservata ma un bound superiore sull'accessibilita': "anche volendo
      comprare appena possibile, non prima di qui".

    Il `source` distinto tiene le tre popolazioni separate in analisi: mediarle
    produrrebbe un numero che non descrive nessuna delle tre.
    """
    per_symbol: dict[str, dict] = {}
    for evento in eventi:
        istante = evento.get("eligible_cycle_at")
        if istante is None:
            continue
        precedente = per_symbol.get(evento["symbol"])
        if precedente is None or istante < precedente["at"]:
            per_symbol[evento["symbol"]] = {
                "at": istante,
                "source": ELIGIBLE_SOURCE_DECISION,
            }
    return per_symbol


def _ciclo_apertura(giorno: date) -> dict:
    """Fallback dichiarato: primo ciclo da 15 minuti della seduta.

    Vale per i candidati che non hanno NESSUN punteggio — i NO_NEWS. Non e' una
    decisione osservata ma un bound: "anche comprando appena possibile, non
    prima di qui".
    """
    return {
        "at": datetime.combine(giorno, PRIMO_CICLO_SEDUTA_UTC, tzinfo=timezone.utc),
        "source": ELIGIBLE_SOURCE_SESSION_OPEN,
    }


def _primo_ciclo_utile(giorno: date, istante: datetime) -> datetime | None:
    """Primo ciclo :07/:22/:37/:52 non anteriore a `istante`. None a seduta finita."""
    for ora in CICLI_ORE_UTC:
        for minuto in CICLI_MINUTI_UTC:
            ciclo = datetime.combine(giorno, time(ora, minuto), tzinfo=timezone.utc)
            if ciclo >= istante:
                return ciclo
    return None


def _ciclo_dal_segnale(candidato: dict, giorno: date) -> dict | None:
    """Ciclo eleggibile ricostruito dal primo punteggio del candidato.

    Serve ai candidati che hanno un punteggio ma nessuna riga in
    `execution_decisions` — hanno notizie e segnali, semplicemente nessuna
    decisione e' stata registrata contro di essi. Per questi il motore NON
    avrebbe potuto agire all'apertura: prima delle 16:30 il segnale su ORCL non
    esisteva. Usare `session_open` qui gonfierebbe la quota accessibile
    esattamente nel modo che #246 contesta (55,63 $ invece di ~7 $).

    None se il candidato non ha segnali: quel caso ricade su `session_open`.
    """
    ore = [s.get("ora") for s in (candidato.get("segnali") or []) if s.get("ora")]
    if not ore:
        return None
    ora, minuto = (int(x) for x in min(ore).split(":")[:2])
    primo_segnale = datetime.combine(giorno, time(ora, minuto), tzinfo=timezone.utc)
    ciclo = _primo_ciclo_utile(giorno, primo_segnale)
    if ciclo is None:
        # Punteggio arrivato dopo l'ultimo ciclo della seduta: non c'era nessun
        # momento per agirci. Dichiararlo e' l'unica risposta onesta.
        return {"at": None, "source": ELIGIBLE_SOURCE_NESSUN_CICLO}
    return {"at": ciclo, "source": ELIGIBLE_SOURCE_SEGNALE}


def _opportunity_v2(
    candidato: dict,
    barre: dict[str, dict],
    giorno: date,
    barre_intraday: dict[str, list[dict]] | None = None,
    cicli: dict[str, dict] | None = None,
) -> dict:
    """Stima v2 parallela di opportunita' per un candidato miss (#280, #246).

    Deterministica e versionata; NON tocca la serie legacy (costo_usd del prompt
    alpha-miner e findings.json restano intatti): la stima v2 si affianca, il
    conteggio legacy resta come traccia dentro il blocco `legacy` della stima.

    Cablata alle barre intraday (#246 Q1). Le tre strade:
    - ribasso non detenuto in book long-only -> accessible/net = 0.0 verificato;
    - rialzo non detenuto -> entry prezzata sull'apertura del primo bar 5Min
      successivo al primo ciclo eleggibile, exit al close: e' la porzione
      davvero catturabile da un motore RTH. ORCL il 12/08 vale 117,95 $
      close-to-close e ~6,82 $ su questa gamba: la differenza non e' un
      dettaglio, e' la misura;
    - barre o ciclo mancanti -> accessible resta None con missingness esplicita,
      mai confuso con gross e mai inventato.

    Difensivo: un candidato che fallisce non blocca il dossier.
    """
    sym = candidato["symbol"]
    daily = barre.get(sym)
    if daily is None:
        return {"estimator_version": ESTIMATOR_VERSION, "symbol": sym,
                "error": "daily_bar_missing"}
    # Tre fonti in cascata, ognuna marcata: decisione osservata -> primo ciclo
    # dopo il punteggio -> primo ciclo della seduta (solo per chi non ha segnali).
    ciclo = (
        (cicli or {}).get(sym)
        or _ciclo_dal_segnale(candidato, giorno)
        or _ciclo_apertura(giorno)
    )
    # Le barre arrivano da _barre_intraday con timestamp datetime; lo stimatore
    # e' puro e il dossier viene serializzato in JSON: passiamo ISO 8601.
    intraday = [
        {**bar, "timestamp": bar["timestamp"].isoformat()}
        for bar in (barre_intraday or {}).get(sym, [])
    ]
    try:
        return compute_opportunity(
            {
                "symbol": sym,
                "book_side": "long",
                "held": bool(candidato.get("in_portafoglio", False)),
                "daily": {k: daily[k] for k in ("open", "high", "low", "close", "close_prec")},
                "size_usd": SLOT_USD_DEFAULT,
                "slot_fraction": SLOT_FRACTION_S4,
                "size_source": "S4 fixed slot = bucket_pct(0.10)/n_top(5) = 2% NAV ~$110k",
                "eligible_cycle_at": ciclo["at"].isoformat() if ciclo["at"] else None,
                "eligible_cycle_source": ciclo["source"],
                "intraday_bars": intraday,
                "cost": None,  # roundtrip reale: wiring TradeCostCalculator, fuori da #246
                "cutoff": _cutoff_giorno(giorno),
                "exit_policy": "EOD_close",
                "confidenza": "congetturale",
            }
        )
    except Exception as exc:  # pragma: no cover - difensivo
        log.warning("opportunity_v2 %s fallita: %s", sym, exc)
        return {"estimator_version": ESTIMATOR_VERSION, "symbol": sym, "error": str(exc)}


def costruisci_dossier(
    giorno: date,
    simboli: list[str],
    *,
    fetch_remote_context: bool = False,
) -> dict:
    g = giorno.isoformat()
    sector_by_ticker = _sector_by_ticker()
    benchmark_symbols = {"SPY", *SECTOR_ETF_BY_SECTOR.values()}
    barre = _barre(sorted(set(simboli) | benchmark_symbols), giorno)
    if not any(symbol in barre for symbol in simboli):
        # Una barra benchmark dimostra gia' che la seduta era aperta. Se manca
        # anche quella, il calendario distingue mercato chiuso da missing data:
        # solo il primo caso puo' restare uno skip con exit 0 (#396).
        seduta_aperta = any(symbol in barre for symbol in benchmark_symbols)
        if not seduta_aperta:
            seduta_aperta = _e_giorno_di_borsa(giorno)
        if seduta_aperta:
            raise SystemExit(
                f"{g}: seduta di borsa senza barre per l'intera watchlist."
            )
        raise GiornoNonBorsa(f"{g}: il calendario conferma che non e' un giorno di borsa.")

    # --- mercato -----------------------------------------------------------
    closes = {
        s: (barre[s]["close_prec"], barre[s]["close"])
        for s in simboli
        if s in barre
    }
    news = {r[0]: int(r[1]) for r in _psql(
        f"SELECT ticker, count(*) FROM news_log "
        f"WHERE fetched_at >= '{g}' AND fetched_at < '{g}'::date + 1 GROUP BY 1;")}
    mercato = compute_market(closes=closes, news_counts=news, soglia_mover=SOGLIA_MOVER)

    # --- candidati miss ----------------------------------------------------
    # #244: ogni riga scorata porta anche la propria PROVENIENZA, altrimenti la
    # partizione di THIN_NEUTRAL in tre bucket non e' decidibile a valle. Il
    # join su news_log e' LEFT: i segnali senza `news_log_id` (fallback FinBERT,
    # righe pre-#030) restano senza `extraction_method` e ricadono sul
    # comportamento pre-#244, che e' esattamente cio' che vogliamo.
    #   testo_scorato    — il titolo. Per org_lookup/gdelt_doc il connettore
    #                      costruisce l'item con `body = title`
    #                      (src/connectors/gdelt_gkg.py:208), quindi il titolo
    #                      E' il testo scorato; per source_metadata e' solo lo
    #                      snippet troncato, e il classificatore infatti non
    #                      lo usa per decidere.
    #   n_ticker_articolo — fan-out: quanti ticker condividono lo stesso
    #                      articolo. Il vincolo uq_news_log_url_ticker rende
    #                      `count(*) per url` esattamente il numero di ticker
    #                      distinti. Metrica propria (#169), MAI un input di
    #                      OFF_TOPIC.
    # I titoli passano per translate(): `_psql` splitta su '|' e '\n', e un
    # titolo tipo «Stocks | Reuters» sfaserebbe le colonne di tutta la riga.
    segnali: dict[str, list[dict]] = defaultdict(list)
    for r in _psql(
        f"SELECT ss.symbol, to_char(ss.generated_at,'HH24:MI'), ss.score, ss.fallback_used, "
        f"COALESCE(nl.extraction_method,''), "
        f"translate(COALESCE(nl.title,''), '|' || chr(10) || chr(13), '   '), "
        f"CASE WHEN COALESCE(nl.url,'') = '' THEN '' ELSE "
        f"  (SELECT count(*)::text FROM news_log n2 WHERE n2.url = nl.url) END, "
        f"ss.id::text "
        f"FROM sentiment_signals ss LEFT JOIN news_log nl ON nl.id = ss.news_log_id "
        f"WHERE ss.generated_at >= '{g}' "
        f"AND ss.generated_at < '{g}'::date + 1 ORDER BY ss.generated_at;"):
        segnale = {"ora": r[1], "score": float(r[2]), "fallback": r[3] == "t"}
        # Chiavi presenti solo se il dato esiste: assente != vuoto, e il
        # classificatore distingue i due casi (senza_provenienza -> THIN_NEUTRAL).
        if r[4]:
            segnale["extraction_method"] = r[4]
        if r[5]:
            segnale["testo_scorato"] = r[5]
        if r[6]:
            segnale["n_ticker_articolo"] = int(r[6])
        if len(r) > 7 and r[7]:
            segnale["signal_id"] = int(r[7])
        segnali[r[0]].append(segnale)

    in_portafoglio = {r[0] for r in _psql(
        f"SELECT DISTINCT symbol FROM trades "
        f"WHERE entry_time < '{g}'::date + 1 AND (exit_time IS NULL OR exit_time >= '{g}');")}

    candidati = compute_miss_candidates(
        rendimenti=mercato["rendimenti"], news_counts=news, segnali=dict(segnali),
        in_portafoglio=in_portafoglio, soglia_mover=SOGLIA_MOVER)

    # Causa deterministica per ogni candidato (#208): news_count, segnali,
    # in_portafoglio sono gia' tutti nei candidati, il classificatore aggiunge
    # solo il campo `causa`. La soglia e' letta da Redis (feedback:entry_threshold:S4,
    # con fallback al baseline) perche' tra il 07-31 e il 08-07 il ratchet (#191)
    # aveva spinto il gate fino a 0.40-0.45: con il default fisso 0.30, i candidati
    # con score in [0.30, soglia_effettiva) sarebbero stati classificati come
    # NON_CLASSIFICATO invece di BELOW_GATE — proprio nei giorni che il dossier
    # deve spiegare.
    soglia_gate = _soglia_gate_s4()
    candidati_classificati = classify_miss_candidates(
        candidati, soglia_gate=soglia_gate
    )

    # --- copertura articolo-centrica (#279) ------------------------------
    session_open, session_close = _regular_session_bounds(giorno)
    article_rows = _article_coverage_rows(giorno)
    copertura_articoli = build_article_coverage(
        article_rows,
        universe=simboli,
        sector_by_ticker=sector_by_ticker,
        session_open=session_open,
        session_close=session_close,
    )
    attribution_by_signal = {
        row["signal_id"]: row for row in copertura_articoli["segnali"]
    }
    for candidato in candidati_classificati:
        metriche_ticker = copertura_articoli["per_ticker"].get(candidato["symbol"], {})
        candidato["max_score_own"] = metriche_ticker.get("max_score_own")
        candidato["max_score_fanout"] = metriche_ticker.get("max_score_fanout")
        for segnale in candidato.get("segnali") or []:
            attribution = attribution_by_signal.get(segnale.get("signal_id"))
            if attribution is None:
                continue
            for campo in (
                "canonical_article_id",
                "source",
                "subject_ticker",
                "relevance",
                "timing",
                "attribution",
            ):
                segnale[campo] = attribution[campo]
            # I due massimi sono metriche per ticker, ripetute accanto al
            # segnale per rendere l'attribution leggibile senza join esterni.
            segnale["max_score_own"] = metriche_ticker.get("max_score_own")
            segnale["max_score_fanout"] = metriche_ticker.get("max_score_fanout")

    # --- timeline e barre intraday (#277) --------------------------------
    eventi = _timeline_eventi(giorno)
    intenti_s4_grezzi = _s4_entry_intents(giorno)
    mover_symbols = {
        symbol
        for symbol, rendimento in mercato["rendimenti"].items()
        if abs(rendimento) >= SOGLIA_MOVER
    }
    simboli_timeline = sorted(
        mover_symbols
        | {e["symbol"] for e in eventi}
        | {intent["symbol"] for intent in intenti_s4_grezzi}
    )
    timestamps_eventi = [
        e[stage]
        for e in eventi
        for stage in ("published_at", "first_seen_at", "ingested_at", "scored_at")
        if e.get(stage) is not None
    ]
    timestamps_eventi.extend(
        timestamp
        for intent in intenti_s4_grezzi
        if (timestamp := _timestamp(intent.get("signal_at"))) is not None
    )
    primo_evento = min(timestamps_eventi) if timestamps_eventi else None
    barre_intraday, cutoff_intraday = _barre_intraday(
        simboli_timeline, giorno, primo_evento
    )
    dettagli_ordini = _dettagli_ordini(
        [e["order_id"] for e in eventi if e.get("order_id")]
    )
    eventi_arricchiti = []
    for evento in eventi:
        row = dict(evento)
        order_id = evento.get("order_id")
        ordine = dettagli_ordini.get(order_id, {}) if order_id else {}
        row.update({
            "order_submitted_at": ordine.get("submitted_at"),
            "filled_at": ordine.get("filled_at"),
            "fill_price": ordine.get("filled_avg_price"),
            "order_lookup_error": ordine.get("lookup_error"),
        })
        eventi_arricchiti.append(row)
    timeline = build_timeline(
        eventi_arricchiti,
        mover_symbols,
        barre_intraday,
        barre,
        cutoff_intraday,
    )

    # Stima v2 parallela di opportunita' per ogni candidato (#280): deterministica,
    # versionata, serie legacy intatta. Le barre intraday e i cicli eleggibili
    # sono gia' stati caricati sopra proprio per questo (#246 Q1): l'ordine del
    # blocco timeline non e' cosmetico, la stima accessible dipende da entrambi.
    cicli_eleggibili = _cicli_eleggibili(eventi, giorno)
    for c in candidati_classificati:
        c["opportunity_v2"] = _opportunity_v2(
            c, barre, giorno, barre_intraday, cicli_eleggibili
        )

    # --- contesto evento/mercato/microstruttura (#285) -------------------
    # Le chiamate remote sono attive nel CLI, ma disaccoppiate dal costruttore
    # puro usato dai test. Un fallimento lascia null/missingness, non impedisce
    # la produzione del dossier e non viene imputato come zero.
    context_articles = _context_articles(article_rows, copertura_articoli)
    regime_observations = _regime_observations(giorno)
    vix_observation = _vix_observation(giorno) if fetch_remote_context else None
    corporate_calendar = (
        _corporate_calendar(giorno, simboli) if fetch_remote_context else None
    )
    context_cycles = dict(cicli_eleggibili)
    for candidate in candidati_classificati:
        symbol = candidate["symbol"]
        if symbol not in context_cycles:
            context_cycles[symbol] = (
                _ciclo_dal_segnale(candidate, giorno) or _ciclo_apertura(giorno)
            )
    nbbo_quotes = (
        _nbbo_at_cycles(context_cycles, cutoff_intraday)
        if fetch_remote_context
        else {}
    )
    event_market_context = build_event_market_context(
        data=g,
        candidates=candidati_classificati,
        daily_bars=barre,
        sector_by_ticker=sector_by_ticker,
        articles=context_articles,
        corporate_events=corporate_calendar,
        regime_observations=regime_observations,
        vix_observation=vix_observation,
        intraday_bars=barre_intraday,
        nbbo_quotes=nbbo_quotes,
        halt_events=_halt_events(context_articles),
    )

    # --- book: ingressi e chiusure ----------------------------------------
    ingressi_grezzi = [
        {"symbol": r[0], "strategia": r[1], "ora_utc": r[2],
         "entry_price": float(r[3]), "qty": float(r[4])}
        for r in _psql(
            f"SELECT symbol, COALESCE(stop_strategy, CASE WHEN signal_id IS NOT NULL "
            f"THEN 'S4' ELSE 'S1' END), to_char(entry_time,'HH24:MI'), entry_price, qty "
            f"FROM trades WHERE entry_time >= '{g}' AND entry_time < '{g}'::date + 1 "
            f"AND entry_price IS NOT NULL AND qty IS NOT NULL ORDER BY entry_time;")]

    chiusure_grezze = [
        {"symbol": r[0], "strategia": r[1], "exit_price": float(r[2]), "qty": float(r[3]),
         "pnl_net": float(r[4]), "exit_reason": r[5] or "", "ore_tenuta": float(r[6])}
        for r in _psql(
            f"SELECT symbol, COALESCE(stop_strategy, CASE WHEN signal_id IS NOT NULL "
            f"THEN 'S4' ELSE 'S1' END), exit_price, qty, net_pnl, exit_reason, "
            f"EXTRACT(epoch FROM (exit_time-entry_time))/3600 "
            f"FROM trades WHERE exit_time >= '{g}' AND exit_time < '{g}'::date + 1 "
            f"AND exit_price IS NOT NULL AND qty IS NOT NULL AND net_pnl IS NOT NULL "
            f"ORDER BY exit_time;")]

    # close_prec entra nelle barre del book perche' `quota_nel_gap` misura il
    # salto di apertura contro la chiusura precedente (#246 Q4).
    barre_ohlc = {
        s: {k: b[k] for k in ("open", "high", "low", "close", "close_prec")}
        for s, b in barre.items()
    }
    chiusure_close = {s: b["close"] for s, b in barre.items()}

    # #335 step 1: simboli con un rilascio earnings datato la seduta, derivati
    # dal calendario corporate gia' caricato per l'event_market_context. None
    # quando il calendario non era disponibile (fetch remote off / fonte
    # earnings down): `giorno_di_earnings` resta UNKNOWN, non False per difetto.
    earnings_symbols = _earnings_symbols_from_calendar(corporate_calendar)

    soglia_guardia = _soglia_guardia_contraddizione()
    ingressi = compute_entries(
        ingressi_grezzi,
        barre_ohlc,
    )
    chiusure = compute_exits(chiusure_grezze, chiusure_close)

    # #335: la popolazione e' il ledger degli intenti tradabili #294, non la
    # tabella trades. Il prezzo e' PIT al segnale; gli intenti non eseguiti
    # restano quindi misurabili senza inventare un fill.
    intenti_ingresso_s4 = compute_s4_entry_intents(
        intenti_s4_grezzi,
        barre_intraday,
        barre_ohlc,
        earnings_symbols=earnings_symbols,
        soglia_guardia=soglia_guardia,
    )

    # #335 step 2: aggregato ombra giornaliero + sweep sulla finestra di
    # osservazione. Misura read-only: nessun ordine cambiato.
    guardia_giorno = aggregate_contradiction_guard(intenti_ingresso_s4)
    _avvisa_partizione_tradabilita_unilaterale(guardia_giorno, giorno)
    guardia_giorno["soglia"] = soglia_guardia
    guardia_finestra = _guardia_contraddizione_finestra(
        intenti_ingresso_s4, giorno
    )

    # #401: post-hoc check sul ledger #294. Per ogni decision_slot della seduta,
    # verifica che il rank registrato sia strettamente decrescente nel
    # ranking_score persistito. Lista vuota == invariante rispettato.
    invariante_ranks = _s4_rank_invariante_ranks(giorno)
    invariante_violazioni = _invariante_rank_in_ranking_score(invariante_ranks)
    if invariante_violazioni:
        log.warning(
            "#401: rilevate %d violazioni rank/ranking_score il %s "
            "(prime 3: %s)",
            len(invariante_violazioni),
            giorno.isoformat(),
            invariante_violazioni[:3],
        )

    # --- qualita' decisionale read-only (#284) ----------------------------
    # Lo snapshot e' prospettico/parallelo: i dossier storici restano intatti.
    # Nessun valore qui entra nel runtime; size e holding sono solo descritti.
    posizioni_apertura = _opening_positions(giorno)
    exit_order_details = _dettagli_ordini(
        [
            order_id
            for posizione in posizioni_apertura
            for order_id in posizione.get("exit_order_ids") or []
        ]
    )
    for posizione in posizioni_apertura:
        posizione["exit_fills"] = [
            {"order_id": order_id, **exit_order_details.get(order_id, {})}
            for order_id in posizione.get("exit_order_ids") or []
        ]
    snapshot_apertura = build_opening_snapshot(
        posizioni_apertura,
        barre,
        data=g,
        sector_by_ticker=sector_by_ticker,
    )
    guard_decisions = _guard_decisions(giorno)
    decision_signal_id_coverage = build_signal_id_coverage_panel(
        _execution_decisions_signal_id_rows(giorno)
    )
    decision_quality_assumptions = {
        "sizing_reference_usd": SLOT_USD_DEFAULT,
        "sizing_reference_source": (
            "S4 fixed slot osservato: bucket_pct(0.10)/n_top(5), solo controfattuale read-only"
        ),
    }
    decision_quality = build_decision_quality_panel(
        {
            "data": g,
            "snapshot_apertura": snapshot_apertura,
            "decision_quality_assumptions": decision_quality_assumptions,
            "ingressi": ingressi,
            "chiusure": chiusure,
            "guard_decisions": guard_decisions,
            "decision_signal_id_coverage": decision_signal_id_coverage,
        }
    )

    # --- copertura news lato uscita (#324) --------------------------------
    # I candidati miss escludono per costruzione i simboli in portafoglio, quindi una
    # posizione detenuta a zero righe news_log non era contata da nessuna parte. Qui
    # la stessa assenza viene misurata sul libro, non sui soli mover non detenuti.
    sedute_copertura = _sedute_di_borsa(giorno, FINESTRA_SEDUTE_COPERTURA)
    righe_news_finestra, fonti_news_finestra = _righe_news_per_seduta(
        [posizione["symbol"] for posizione in posizioni_apertura], sedute_copertura
    )
    copertura_uscita = build_exit_coverage(
        posizioni_apertura,
        data=g,
        sedute=sedute_copertura,
        righe_per_seduta=righe_news_finestra,
        fonti_finestra=fonti_news_finestra,
        copertura_per_ticker=copertura_articoli.get("per_ticker") or {},
        segnali_per_ticker={
            symbol: len(righe) for symbol, righe in segnali.items()
        },
        barre=barre,
    )

    # --- aggregazioni ------------------------------------------------------
    # stop_strategy GREZZA, senza COALESCE su S1/S4: la coorte legacy (F-002,
    # stop_strategy NULL) deve restare riconoscibile nel bucket orario, non
    # essere assorbita in una sleeve che non l'ha prodotta (#246 Q3).
    chiusi_storici = [
        {"ora_ingresso": int(r[0]), "pnl_net": float(r[1]),
         "stop_strategy": r[2] or None}
        for r in _psql(
            "SELECT EXTRACT(hour FROM entry_time)::int, net_pnl, "
            "COALESCE(stop_strategy, '') FROM trades "
            "WHERE exit_time IS NOT NULL AND net_pnl IS NOT NULL;")]

    return {
        "schema_version": DOSSIER_SCHEMA_VERSION,
        "data": g,
        "generato_il": datetime.now(timezone.utc).isoformat(),
        "fonte_prezzi": "Alpaca SIP, adjustment=all",
        "provenienza_dati": {
            "daily": {
                "source": "Alpaca Market Data API",
                "feed": "SIP",
                "timeframe": "1Day",
                "adjustment": "all",
            },
            "intraday": {
                "source": "Alpaca Market Data API",
                "feed": "SIP",
                "timeframe": "5Min",
                "adjustment": "all",
                "sessioni": "04:00-20:00 America/New_York",
                "cutoff": cutoff_intraday.isoformat(),
            },
            "timeline": {
                "published_at": "news_log.published_at",
                "first_seen_at": "news_log.raw_ingested_at",
                "ingested_at": "news_log.fetched_at",
                "scored_at": "sentiment_signals.generated_at",
                "eligible_cycle_at": "execution_decisions.tick_time (primo per signal_id)",
                "opportunity_v2.eligible_cycle": (
                    "execution_decisions.tick_time se il candidato ha una decisione "
                    "collegata; altrimenti primo_ciclo_dopo_segnale (:07/:22/:37/:52 dal "
                    "primo punteggio); altrimenti session_open = 14:07 UTC per i candidati "
                    "senza segnali. Il source e' dichiarato nel blocco entry."
                ),
                "order_submitted_at": "Alpaca Trading API order.submitted_at",
                "filled_at": "Alpaca Trading API order.filled_at",
                "fill_price": "Alpaca Trading API order.filled_avg_price",
                "latenze_secondi": (
                    "differenze signed fra timestamp persistiti; None se una tappa manca"
                ),
            },
            "metriche": {
                "first_price": "open della prima barra 5Min con timestamp >= stadio",
                "mfe_mae": "high/low successivi allo stadio fino al cutoff, long-side",
                "quote": "non clampate; valori <0 o >1 espongono reversal/overshoot",
                "effective_timely_coverage": (
                    "articolo canonicale ISSUER_SPECIFIC pubblicato entro il close RTH; "
                    "UNKNOWN non entra nel numeratore"
                ),
                "ritorno_sessione_al_segnale": (
                    "(prezzo_al_segnale - close_prec) / close_prec per ogni "
                    "candidate intent del ledger #294. prezzo_al_segnale e' "
                    "l'open della prima barra Alpaca SIP 5Min con timestamp >= "
                    "s4_intent_events.model_generated_at: mai il fill e mai "
                    "OHLC della barra in corso (#335)"
                ),
                "giorno_di_earnings": (
                    "simbolo con evento event_type=earnings nel calendario "
                    "FMP/Alpaca della seduta, per ogni intento S4; None se il "
                    "calendario non era disponibile (UNKNOWN, non False per "
                    "difetto) (#335)"
                ),
                "guardia_contraddizione_ombra": (
                    "ombra read-only sull'intera s4_candidate_population: "
                    "True se snapshot.score > 0 e ritorno_sessione_al_segnale "
                    "<= -soglia; l'aggregato 'soppressi' include solo gli intenti "
                    "con disposition.is_tradable=true, anche se non eseguiti. "
                    "None se score, prezzo PIT o close_prec mancanti. Non blocca "
                    "ordini (#335)"
                ),
                "motivo_guardia_contraddizione": (
                    "stringa esplicativa quando la guardia ombra (#335) fa firing "
                    "(score e ritorno); None negli altri casi"
                ),
            },
            "copertura_uscita": {
                "posizioni": "trades vivi all'open RTH (stesse righe di snapshot_apertura)",
                "righe_news": "news_log.fetched_at bucket UTC, per (ticker, seduta)",
                "segnali": "sentiment_signals.generated_at nella seduta",
                "sedute": (
                    f"Alpaca GetCalendarRequest, ultime {FINESTRA_SEDUTE_COPERTURA} "
                    "sedute fino al giorno"
                ),
                "mark": (
                    "close daily Alpaca SIP. ritorno_da_ingresso = close/entry_price - 1 "
                    "(la grandezza che una decisione d'uscita guarda); ritorno_seduta = "
                    "close/close_prec - 1 (quella citata dai report alpha-miss). Sono due "
                    "misure diverse e non vanno confuse"
                ),
                "cecita": (
                    "perdita marcata + zero righe + zero segnali + streak >= sedute_minime; "
                    "None quando barra, prezzo d'ingresso o calendario mancano"
                ),
                "notional_cieco_usd": (
                    "esposizione a rischio, NON un costo: nessun controfattuale dice "
                    "che un'uscita sarebbe stata migliore"
                ),
                "freeze": "misura read-only; nessuna soglia di strategia toccata",
            },
            "decision_quality": {
                "snapshot_apertura": "trades vivi all'open RTH + barre Alpaca SIP",
                "guard_counterfactual": (
                    "execution_decisions.counterfactual_return_1h/overnight; "
                    "notional USD solo SKIP_PYRAMIDING post-2026-08-19 con NAV osservata"
                ),
                "freeze": "misura read-only; nessuna taratura live emessa",
            },
            "event_market_context": {
                "version": CONTEXT_VERSION,
                "sector_map": "config/trading.yaml sectors",
                "sector_etf_map": "SECTOR_ETF_BY_SECTOR (dichiarativo, benchmark-only)",
                "returns": "beta_1_arithmetic_v1: r_symbol - r_benchmark",
                "corporate_calendar": "FMP earnings-calendar + Alpaca Corporate Actions API",
                "regime": "execution_decisions.regime_mult; ultima osservazione del giorno",
                "vix": "FRED VIXCLS, ultima osservazione non successiva alla data",
                "bar_microstructure": "Alpaca SIP 5Min + ADV su 20 barre daily complete precedenti",
                "nbbo": "Alpaca SIP quotes, prima quota entro 5 minuti dal ciclo eleggibile",
                "halt": (
                    "solo evidenza positiva da articoli; senza feed halt storico autorevole "
                    "lo stato resta UNKNOWN"
                ),
                "remote_context_loaded": fetch_remote_context,
            },
        },
        "soglia_mover": SOGLIA_MOVER,
        "mercato": mercato,
        "candidati_miss": candidati_classificati,
        "soglia_gate_usata": soglia_gate,
        "ingressi": ingressi,
        "intenti_ingresso_s4": intenti_ingresso_s4,
        "chiusure": chiusure,
        "snapshot_apertura": snapshot_apertura,
        "guard_decisions": guard_decisions,
        "copertura_uscita": copertura_uscita,
        "decision_quality_assumptions": decision_quality_assumptions,
        "decision_quality": decision_quality,
        "decision_signal_id_coverage": decision_signal_id_coverage,
        "timeline": timeline,
        "copertura_articoli": copertura_articoli,
        "event_market_context": event_market_context,
        "aggregati": {
            "per_ora_ingresso": aggregate_by_entry_hour(chiusi_storici),
            "miss_cumulati": _miss_cumulati(),
            "mediane_mobili_20g": _mediane_mobili(ingressi, chiusure),
            "cause_del_giorno": cause_del_giorno(candidati_classificati),
            "copertura_uscita": copertura_uscita["aggregato"],
            "guardia_contraddizione": {
                "giorno": guardia_giorno,
                "finestra_osservazione": guardia_finestra,
            },
            "invariante_rank_ranking_score": {
                "n_righe_esaminate": len(invariante_ranks),
                "n_violazioni": len(invariante_violazioni),
                "violazioni": invariante_violazioni,
                "freeze": "strumento di misura read-only #401; nessun ordine toccato",
            },
        },
    }


def _earnings_symbols_from_calendar(corporate_calendar: dict | list | None) -> set[str] | None:
    """Simboli con evento earnings nella seduta, dal calendario corporate.

    Tollerante sulla forma come `build_event_market_context`: il calendario reale
    e' un dict `{"events": [...], "missingness": [...], ...}`, ma i test possono
    passare una lista nuda di eventi. Restituisce None (UNKNOWN) quando la fonte
    earnings specifica e' assente o fallita, cosi' `giorno_di_earnings` non viene
    forzato a False per difetto di fonte.
    """
    if corporate_calendar is None:
        return None
    if isinstance(corporate_calendar, dict):
        eventi = corporate_calendar.get("events") or []
        missingness = corporate_calendar.get("missingness") or []
        if any("earnings_calendar" in str(m) for m in missingness):
            return None
    else:
        eventi = corporate_calendar
    return {
        str(ev.get("symbol") or "").upper()
        for ev in eventi
        if str(ev.get("event_type") or "").casefold() == "earnings"
    }


def _soglia_guardia_contraddizione() -> float:
    """Soglia della guardia ombra (#335): strumento di MISURA, non taratura di
    strategia. Default `SOGLIA_GUARDIA_CONTRADDIZIONE` (-4%); overridable via
    env `SOGLIA_GUARDIA_CONTRADDIZIONE` per analisi di sensibilita' senza
    toccare il codice. Non entra in nessuna decisione di trading."""
    raw = os.environ.get("SOGLIA_GUARDIA_CONTRADDIZIONE", "")
    if not raw:
        return SOGLIA_GUARDIA_CONTRADDIZIONE
    try:
        valore = float(raw)
        return abs(valore) if valore < 0 else valore
    except ValueError:
        log.warning("SOGLIA_GUARDIA_CONTRADDIZIONE=%r non valido, uso il default", raw)
        return SOGLIA_GUARDIA_CONTRADDIZIONE


def _avvisa_partizione_tradabilita_unilaterale(
    aggregato: Mapping[str, Any], giorno: date
) -> None:
    """Segnala una seduta in cui ogni disposition risulta non tradabile."""
    n_intenti = int(aggregato.get("n_intenti") or 0)
    n_tradabili = int(aggregato.get("n_intenti_tradabili") or 0)
    n_non_tradabili = int(aggregato.get("n_intenti_non_tradabili") or 0)
    if n_intenti > 0 and n_tradabili == 0 and n_non_tradabili == n_intenti:
        log.warning(
            "Guardia contraddizione %s: partizione is_tradable unilaterale, "
            "%d intenti non tradabili su %d; verificare query e parser",
            giorno.isoformat(),
            n_non_tradabili,
            n_intenti,
        )


def _guardia_contraddizione_finestra(
    intenti_giorno: Sequence[Mapping[str, Any]], giorno: date
) -> dict:
    """Ricalcola il cumulato #335 dagli intenti PIT conservati nei dossier.

    Il P&L dei trade eseguiti viene riletto per `trade_id`: un intento ancora
    aperto nel dossier del giorno d'ingresso acquisisce il P&L realizzato appena
    il trade chiude, senza riscrivere il dossier storico e senza matching FIFO.
    I dossier pre-schema 2.5 non hanno la popolazione #294 e restano fuori con
    copertura esplicita.
    """
    intenti_finestra = list(intenti_giorno)
    giorni_coperti = {giorno.isoformat()}
    oggi_iso = giorno.isoformat()
    for f in sorted(OUT_DIR.glob("*.json")):
        if f.stem == oggi_iso:
            continue
        if f.stem < INIZIO_OSSERVAZIONE.isoformat() or f.stem > oggi_iso:
            continue
        try:
            d = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        intenti = d.get("intenti_ingresso_s4")
        if isinstance(intenti, list):
            intenti_finestra.extend(intenti)
            giorni_coperti.add(f.stem)

    trade_ids = sorted({
        int(intent["trade_id"])
        for intent in intenti_finestra
        if intent.get("trade_id") is not None
    })
    pnl_per_trade: dict[int, float | None] = {}
    if trade_ids:
        id_sql = ",".join(str(trade_id) for trade_id in trade_ids)
        for db_row in _psql(
            f"SELECT id::text, COALESCE(net_pnl::text,'') FROM trades "
            f"WHERE id IN ({id_sql}) ORDER BY id;"
        ):
            pnl_per_trade[int(db_row[0])] = (
                float(db_row[1]) if db_row[1] else None
            )

    aggiornati = []
    for intent in intenti_finestra:
        intent_row = dict(intent)
        trade_id = intent_row.get("trade_id")
        if trade_id is not None and int(trade_id) in pnl_per_trade:
            intent_row["pnl_realizzato"] = pnl_per_trade[int(trade_id)]
        aggiornati.append(intent_row)

    aggregato = aggregate_contradiction_guard(aggiornati)
    aggregato.update({
        "n_giorni_coperti": len(giorni_coperti),
        "copertura": "da schema 2.5 in avanti; dossier pre-ledger esclusi",
        "pnl_refresh": "trades.net_pnl riletto per trade_id alla generazione",
    })
    return aggregato


def _miss_cumulati() -> dict[str, int]:
    """Somma delle cause di miss dal ledger di mercato, non ri-derivata a prosa."""
    p = PROJECT_DIR / "docs" / "evidence" / "market_daily.jsonl"
    tot: dict[str, int] = defaultdict(int)
    if not p.exists():
        return {}
    for riga in p.read_text().splitlines():
        if not riga.strip():
            continue
        for causa, n in (json.loads(riga).get("miss") or {}).items():
            tot[causa] += int(n or 0)
    return dict(tot)


def _mediane_mobili(ingressi: list[dict], chiusure: list[dict]) -> dict:
    """Mediane su questo giorno più i dossier precedenti già scritti.

    Non esiste una metrica unica di "capture ratio": un rapporto fra P&L ottenuto
    e movimento disponibile richiede un denominatore arbitrario e diventa
    instabile quando tende a zero. Queste due mediane misurano le due meta' del
    problema — inseguiamo in ingresso, usciamo troppo presto — senza inventare un
    rapporto fragile.
    """
    percentili = [i["entry_percentile"] for i in ingressi if i.get("entry_percentile") is not None]
    drift = [c["drift_post_uscita"] for c in chiusure if c.get("drift_post_uscita") is not None]

    for f in sorted(OUT_DIR.glob("*.json"), reverse=True)[:FINESTRA_MEDIANE]:
        try:
            d = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        percentili += [i["entry_percentile"] for i in d.get("ingressi", [])
                       if i.get("entry_percentile") is not None]
        drift += [c["drift_post_uscita"] for c in d.get("chiusure", [])
                  if c.get("drift_post_uscita") is not None]

    return {
        "entry_percentile": statistics.median(percentili) if percentili else None,
        "drift_post_uscita": statistics.median(drift) if drift else None,
        "n_ingressi": len(percentili),
        "n_chiusure": len(drift),
    }


def scrivi(dossier: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{dossier['data']}.json"
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(dossier, indent=2, ensure_ascii=False))
    tmp.replace(out)  # atomica: mai un file mezzo scritto
    return out


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("data", nargs="?", help="giorno da analizzare (YYYY-MM-DD)")
    ap.add_argument("--backfill-da", help="ricalcola da questa data a ieri")
    args = ap.parse_args(argv)

    simboli = _watchlist()

    if args.backfill_da:
        inizio = date.fromisoformat(args.backfill_da)
        if inizio < INIZIO_OSSERVAZIONE:
            raise SystemExit(
                f"Il backfill non puo' precedere l'inizio dell'osservazione "
                f"({INIZIO_OSSERVAZIONE}): prima di quella data il periodo non era attivo."
            )
        giorni, g = [], inizio
        while g < date.today():
            giorni.append(g)
            g += timedelta(days=1)
    elif args.data:
        giorni = [date.fromisoformat(args.data)]
    else:
        raise SystemExit("Serve una data o --backfill-da.")

    # #396: un giorno saltato per errore di query NON e' uno skip benigno. Prima
    # della qualifica di decision_at, il parse error veniva catturato qui come
    # SystemExit, degenerato a ``INFO ... saltato`` e lo script usciva 0: il cron
    # non vedeva il fallimento e il dossier moriva in silenzio per 3 sedute.
    # ``GiornoNonBorsa`` e' lo skip legittimo (non e' una seduta); ogni altra
    # ``SystemExit`` (query fallita, credenziali, ...) e' un fallimento reale: si
    # continua a provare gli altri giorni del batch, ma il cron esce non-zero.
    scritti = 0
    saltati = 0
    falliti = 0
    for g in giorni:
        try:
            d = costruisci_dossier(g, simboli, fetch_remote_context=True)
        except GiornoNonBorsa as exc:
            log.info("%s saltato: %s", g, exc)
            saltati += 1
            continue
        except SystemExit as exc:
            log.error("%s FALLITO (non e' un giorno non di borsa): %s", g, exc)
            falliti += 1
            continue
        p = scrivi(d)
        scritti += 1
        m = d["mercato"]
        log.info("%s -> %s | mover %d (up %d, down %d) | zero-news %d | ingressi %d | chiusure %d",
                 g, p.name, m["mover_3pct"], m["up"], m["down"], m["watchlist_zero_news"],
                 len(d["ingressi"]), len(d["chiusure"]))
    log.info("dossier scritti: %d (saltati non-borsa: %d, falliti: %d)",
             scritti, saltati, falliti)
    if falliti:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
