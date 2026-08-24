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
import statistics
import subprocess
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from src.analysis.dossier.book import (
    aggregate_by_entry_hour,
    compute_entries,
    compute_exits,
)
from src.analysis.dossier.decision_quality import (
    build_decision_quality_panel,
    build_opening_snapshot,
)
from src.analysis.dossier.article_coverage import build_article_coverage
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
INIZIO_OSSERVAZIONE = date(2026, 8, 3)
DOSSIER_SCHEMA_VERSION = "2.2"
NEW_YORK = ZoneInfo("America/New_York")

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
    """Barre giornaliere del giorno richiesto e del precedente.

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
        start=datetime.combine(giorno - timedelta(days=10), datetime.min.time()),
        # mai oltre oggi: il SIP rifiuta le richieste che toccano gli ultimi 15
        # minuti, e il rifiuto uccide l'intera chiamata, non la sola ultima barra.
        end=datetime.combine(min(giorno + timedelta(days=1), date.today()), datetime.min.time()),
        feed="sip",
        adjustment="all",
    )
    df = client.get_stock_bars(req).df
    if df is None or df.empty:
        raise SystemExit(f"Nessuna barra per il {giorno}: data non di borsa o dati assenti.")

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
        out[sym] = {
            "open": float(r["open"]), "high": float(r["high"]),
            "low": float(r["low"]), "close": float(r["close"]),
            "close_prec": float(righe[precedenti[-1]]["close"]) if precedenti else None,
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
        })
    for bars in out.values():
        bars.sort(key=lambda bar: bar["timestamp"])
    return dict(out), cutoff


def _timestamp(value: str) -> datetime | None:
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


def _opening_positions(giorno: date) -> list[dict]:
    """Posizioni vive all'apertura RTH, lette senza modificare il book."""
    session_open, _session_close = _regular_session_bounds(giorno)
    open_iso = session_open.isoformat()
    rows = _psql(
        f"SELECT id::text, symbol, "
        f"CASE WHEN stop_strategy IS NOT NULL THEN stop_strategy "
        f"WHEN signal_id IS NOT NULL THEN 'S4' ELSE 'CONTAMINAZIONE' END, "
        f"qty::text, entry_price::text, entry_time::text, "
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


def _e_giorno_di_borsa(barre: dict) -> bool:
    """Se nemmeno un simbolo della watchlist ha una barra, non era giorno di borsa."""
    return len(barre) > 0


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


def costruisci_dossier(giorno: date, simboli: list[str]) -> dict:
    g = giorno.isoformat()
    barre = _barre(simboli, giorno)
    if not _e_giorno_di_borsa(barre):
        raise SystemExit(f"{g}: nessuna barra per l'intera watchlist — non e' un giorno di borsa.")

    # --- mercato -----------------------------------------------------------
    closes = {s: (b["close_prec"], b["close"]) for s, b in barre.items()}
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
    copertura_articoli = build_article_coverage(
        _article_coverage_rows(giorno),
        universe=simboli,
        sector_by_ticker=_sector_by_ticker(),
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
    mover_symbols = {
        symbol
        for symbol, rendimento in mercato["rendimenti"].items()
        if abs(rendimento) >= SOGLIA_MOVER
    }
    simboli_timeline = sorted(mover_symbols | {e["symbol"] for e in eventi})
    timestamps_eventi = [
        e[stage]
        for e in eventi
        for stage in ("published_at", "first_seen_at", "ingested_at", "scored_at")
        if e.get(stage) is not None
    ]
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

    ingressi = compute_entries(ingressi_grezzi, barre_ohlc)
    chiusure = compute_exits(chiusure_grezze, chiusure_close)

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
        sector_by_ticker=_sector_by_ticker(),
    )
    guard_decisions = _guard_decisions(giorno)
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
        }
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
            },
            "metriche": {
                "first_price": "open della prima barra 5Min con timestamp >= stadio",
                "mfe_mae": "high/low successivi allo stadio fino al cutoff, long-side",
                "quote": "non clampate; valori <0 o >1 espongono reversal/overshoot",
                "effective_timely_coverage": (
                    "articolo canonicale ISSUER_SPECIFIC pubblicato entro il close RTH; "
                    "UNKNOWN non entra nel numeratore"
                ),
            },
            "decision_quality": {
                "snapshot_apertura": "trades vivi all'open RTH + barre Alpaca SIP",
                "guard_counterfactual": (
                    "execution_decisions.counterfactual_return_1h/overnight; "
                    "notional USD solo SKIP_PYRAMIDING post-2026-08-19 con NAV osservata"
                ),
                "freeze": "misura read-only; nessuna taratura live emessa",
            },
        },
        "soglia_mover": SOGLIA_MOVER,
        "mercato": mercato,
        "candidati_miss": candidati_classificati,
        "soglia_gate_usata": soglia_gate,
        "ingressi": ingressi,
        "chiusure": chiusure,
        "snapshot_apertura": snapshot_apertura,
        "guard_decisions": guard_decisions,
        "decision_quality_assumptions": decision_quality_assumptions,
        "decision_quality": decision_quality,
        "timeline": timeline,
        "copertura_articoli": copertura_articoli,
        "aggregati": {
            "per_ora_ingresso": aggregate_by_entry_hour(chiusi_storici),
            "miss_cumulati": _miss_cumulati(),
            "mediane_mobili_20g": _mediane_mobili(ingressi, chiusure),
            "cause_del_giorno": cause_del_giorno(candidati_classificati),
        },
    }


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


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("data", nargs="?", help="giorno da analizzare (YYYY-MM-DD)")
    ap.add_argument("--backfill-da", help="ricalcola da questa data a ieri")
    args = ap.parse_args()

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

    scritti = 0
    for g in giorni:
        try:
            d = costruisci_dossier(g, simboli)
        except SystemExit as exc:
            log.info("%s saltato: %s", g, exc)
            continue
        p = scrivi(d)
        scritti += 1
        m = d["mercato"]
        log.info("%s -> %s | mover %d (up %d, down %d) | zero-news %d | ingressi %d | chiusure %d",
                 g, p.name, m["mover_3pct"], m["up"], m["down"], m["watchlist_zero_news"],
                 len(d["ingressi"]), len(d["chiusure"]))
    log.info("dossier scritti: %d", scritti)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
