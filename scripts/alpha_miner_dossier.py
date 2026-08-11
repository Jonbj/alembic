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
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

from src.analysis.dossier.book import (
    aggregate_by_entry_hour,
    compute_entries,
    compute_exits,
)
from src.analysis.dossier.market import compute_market, compute_miss_candidates
from src.analysis.dossier.miss_cause import (
    DEFAULT_SOGLIA_GATE,
    cause_del_giorno,
    classify_miss_candidates,
)

log = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_DIR / "docs" / "evidence" / "dossier"
SOGLIA_MOVER = 0.03
FINESTRA_MEDIANE = 20  # giorni, per le mediane mobili
INIZIO_OSSERVAZIONE = date(2026, 8, 3)


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


def _e_giorno_di_borsa(barre: dict) -> bool:
    """Se nemmeno un simbolo della watchlist ha una barra, non era giorno di borsa."""
    return len(barre) > 0


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
    segnali: dict[str, list[dict]] = defaultdict(list)
    for r in _psql(
        f"SELECT symbol, to_char(generated_at,'HH24:MI'), score, fallback_used "
        f"FROM sentiment_signals WHERE generated_at >= '{g}' "
        f"AND generated_at < '{g}'::date + 1 ORDER BY generated_at;"):
        segnali[r[0]].append({"ora": r[1], "score": float(r[2]), "fallback": r[3] == "t"})

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

    barre_ohlc = {s: {k: b[k] for k in ("open", "high", "low", "close")} for s, b in barre.items()}
    chiusure_close = {s: b["close"] for s, b in barre.items()}

    ingressi = compute_entries(ingressi_grezzi, barre_ohlc)
    chiusure = compute_exits(chiusure_grezze, chiusure_close)

    # --- aggregazioni ------------------------------------------------------
    chiusi_storici = [
        {"ora_ingresso": int(r[0]), "pnl_net": float(r[1])}
        for r in _psql(
            "SELECT EXTRACT(hour FROM entry_time)::int, net_pnl FROM trades "
            "WHERE exit_time IS NOT NULL AND net_pnl IS NOT NULL;")]

    return {
        "data": g,
        "generato_il": datetime.now(timezone.utc).isoformat(),
        "fonte_prezzi": "Alpaca SIP, adjustment=all",
        "soglia_mover": SOGLIA_MOVER,
        "mercato": mercato,
        "candidati_miss": candidati_classificati,
        "soglia_gate_usata": soglia_gate,
        "ingressi": ingressi,
        "chiusure": chiusure,
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
