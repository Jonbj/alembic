#!/usr/bin/env python3
"""Costruisce la diagnostica dei segnali e i controlli negativi (#283) dai dossier
deterministici gia' scritti da ``scripts/alpha_miner_dossier.py``.

Orchestratore SOTTILE: fa solo I/O in LETTURA sui dossier
(``docs/evidence/dossier/*.json``), su ``config/trading.yaml`` (mappa settoriale,
read-only), sul DB Postgres (arricchimento model_id/extraction_method/
ensemble_std/source per signal_id) e sulle barre Alpaca (forward return PIT).
Ogni calcolo vive nel modulo puro ``src/analysis/dossier/signal_diagnostics.py``:
qui nessuna formula, solo assemblaggio delle righe arricchite che il pannello
mangia.

Perche' esiste (#283): la sola coda |return|>=3% e' selezionata ex post e non
misura falsi positivi; IC close-to-close su un segnale tardivo ha reverse
causality. Qui i forward return sono time-forward dal timestamp OSSERVABILE del
segnale (``stages.scored_at.bar_timestamp`` del dossier: prima barra SIP 5Min
allineata allo score), e i controlli matched sono ticker NON segnalati dello
stesso giorno, separati dal benchmark di libro (SPY/settore).

L'audit WRONG_SIGN (#328) usa gli stessi forward return PIT e separa
ensemble/fallback, articoli single/multi-ticker e la loro interazione. Score
neutri, return piatti e missing sono contati a parte: non entrano come errori di
segno e non viene applicato alcun gate o discount al percorso live.

Compatibile con il freeze #171: e' strumentazione/misura. Nessuna soglia/gate/
modello/fonte live viene scelta. La soglia mover arriva dal dossier
(``soglia_mover``, gia' dichiarata), la griglia di sweep e' una costante
dichiarata nel modulo puro, tutti gli output sono marcati ``descriptive_only``.
L'output e' un file derivato e rigenerabile (``docs/evidence/signal_diagnostics.json``):
NON e' evidenza primaria, e' uno strumento di misura sull'evidenza gia' congelata.

Limitazione onesta (pool): i controlli matched sono ticker NON segnalati
(candidati_miss senza ``segnali``) dello stesso giorno; il match e' sul return
del giorno (deterministico, nearest |return|). I forward return del pool non
sono calcolati (manca un anchor per signal comparable): il pannello riporta
missingness esplicita e il diff forward-return del matched pair e' None. Non e'
un buco nascosto, e' dichiarato nel pannello e nella PR.

Limitazione onesta (arricchimento DB): la PK reale di ``sentiment_signals`` e'
``id`` (001_initial.sql:38) e la JOIN e' via ``news_log_id`` (016_trade_
observability.sql). Se il DB non e' raggiungibile o mancano le env vars, il
fail-soft restituisce ``{}`` e gli split per source/model/extraction riportano
missingness (dichiarata nel pannello, NON silenziosa). Sull'arricchimento si
misura, non si sceglie.

Uso:
    uv run python scripts/build_signal_diagnostics.py
    uv run python scripts/build_signal_diagnostics.py --no-write   # solo stdout

I loader esterni (barre Alpaca, arricchimento DB) sono iniettabili: il test di
wiring li monkeypatcha con dati sintetici (nessun DB/rete richiesto).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import subprocess
from pathlib import Path

from src.analysis.dossier.decision_quality import SECTOR_BENCHMARK
from src.analysis.dossier.signal_diagnostics import (
    HORIZONS,
    SIGNAL_DIAGNOSTICS_SCHEMA_VERSION,
    assign_ensemble_std_buckets,
    build_signal_diagnostics_panel,
    build_signal_diagnostics_rollup,
    compute_forward_returns,
)

log = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parents[1]
DOSSIER_DIR = PROJECT_DIR / "docs" / "evidence" / "dossier"
TRADING_YAML = PROJECT_DIR / "config" / "trading.yaml"
OUT = PROJECT_DIR / "docs" / "evidence" / "signal_diagnostics.json"

# Benchmark di libro (SPY) + ETF di settore: letti una volta per giorno.
_BENCHMARK_SYMBOL = "SPY"


# ---------------------------------------------------------------------------
# Loader di default (reali): barre Alpaca + arricchimento DB. Iniettabili.
# ---------------------------------------------------------------------------


def _default_bar_loader(symbol: str, day: dt.date) -> dict:
    """Barre Alpaca SIP per (symbol, day): 5Min intraday della seduta + daily
    del giorno e dei 7 successivi (per T+1..T+5).

    Restituisce ``{"intraday": [{timestamp,open,high,low,close}, ...],
    "daily": [{date,open,high,low,close}, ...]}``. Fail-soft: se Alpaca non e'
    configurato o il symbol non ha barre, restituisce dict vuoto (il pannello
    riportera' missingness). Mai solleva: un ticker senza barre non deve uccidere
    il report intero.
    """
    chiave, segreto = os.environ.get("ALPACA_API_KEY"), os.environ.get("ALPACA_SECRET_KEY")
    if not chiave or not segreto:
        log.warning("ALPACA_API_KEY/SECRET mancanti: barre non caricate per %s@%s", symbol, day)
        return {"intraday": [], "daily": []}
    try:
        from alpaca.data.enums import Adjustment, DataFeed
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    except Exception as exc:  # alpaca-py non installato
        log.warning("alpaca-py non disponibile (%s): barre vuote per %s@%s", exc, symbol, day)
        return {"intraday": [], "daily": []}

    client = StockHistoricalDataClient(chiave, segreto)
    out: dict = {"intraday": [], "daily": []}

    # intraday 5Min: 04:00-20:00 New York del giorno (seduta + extended).
    ny = dt.timezone(dt.timedelta(hours=-4))
    start_intra = dt.datetime.combine(day, dt.time(4, 0), tzinfo=ny).astimezone(dt.timezone.utc)
    end_intra = dt.datetime.combine(day, dt.time(20, 0), tzinfo=ny).astimezone(dt.timezone.utc)
    end_intra = min(end_intra, dt.datetime.now(dt.timezone.utc))
    if end_intra > start_intra:
        req = StockBarsRequest(
            symbol_or_symbols=symbol, timeframe=TimeFrame(5, TimeFrameUnit.Minute),
            start=start_intra, end=end_intra, feed=DataFeed.SIP, adjustment=Adjustment.ALL,
        )
        df = getattr(client.get_stock_bars(req), "df", None)
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                ts = row.index[-1] if isinstance(row.name, tuple) else row.name
                if hasattr(ts, "to_pydatetime"):
                    ts = ts.to_pydatetime()
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=dt.timezone.utc)
                out["intraday"].append({
                    "timestamp": ts.astimezone(dt.timezone.utc).isoformat(),
                    "open": float(row["open"]), "high": float(row["high"]),
                    "low": float(row["low"]), "close": float(row["close"]),
                })

    # daily: giorno + 7 calendari successivi (copre T+5 anche su festivi).
    start_d = dt.datetime.combine(day, dt.time.min)
    end_d = dt.datetime.combine(day + dt.timedelta(days=8), dt.time.min)
    req = StockBarsRequest(
        symbol_or_symbols=symbol, timeframe=TimeFrame.Day,
        start=start_d, end=end_d, feed="sip", adjustment="all",
    )
    df = getattr(client.get_stock_bars(req), "df", None)
    if df is not None and not df.empty:
        for _, row in df.iterrows():
            idx = row.index[-1] if isinstance(row.name, tuple) else row.name
            d = idx.date() if hasattr(idx, "date") else idx
            out["daily"].append({
                "date": d.isoformat() if hasattr(d, "isoformat") else str(d),
                "open": float(row["open"]), "high": float(row["high"]),
                "low": float(row["low"]), "close": float(row["close"]),
            })
    return out


def _default_db_enricher(signal_ids: list[int]) -> dict[int, dict]:
    """Arricchisce i signal_id da Postgres: model_id, extraction_method,
    ensemble_std, source (fonte news), published_at, n_ticker_articolo
    (fan-out: quanti ticker condividono lo stesso articolo, #169).

    Via ``docker exec alembic-postgres-1 psql`` (pattern compute_s4_ic.py).
    Fail-soft: se il DB non e' raggiungibile restituisce {} (il pannello usa
    None e riporta missingness). Mai solleva.
    """
    if not signal_ids:
        return {}
    ids = ",".join(str(int(i)) for i in signal_ids)
    # NB: la PK di sentiment_signals e' ``id`` (001_initial.sql:38), non
    # ``signal_id``. Filtrare per una colonna inesistente fallisce su DB reale
    # e il fail-soft mascherava la rottura lasciando vuoti gli split per
    # source/model/extraction (rilievo bloccante review 2026-08-24).
    # n_ticker_articolo: stesso pattern di scripts/alpha_miner_dossier.py —
    # il vincolo uq_news_log_url_ticker rende count(*) per url esattamente il
    # numero di ticker distinti che condividono l'articolo.
    query = (
        "SELECT s.id, s.model_id, s.ensemble_std, "
        "n.extraction_method, n.source, n.published_at, "
        "CASE WHEN COALESCE(n.url,'') = '' THEN NULL ELSE "
        "  (SELECT count(*) FROM news_log n2 WHERE n2.url = n.url) END "
        "FROM sentiment_signals s LEFT JOIN news_log n ON n.id = s.news_log_id "
        f"WHERE s.id IN ({ids})"
    )
    try:
        res = subprocess.run(
            ["docker", "exec", "alembic-postgres-1", "psql", "-U", "trading",
             "-d", "trading", "-t", "-A", "-F", "|", "-c", query],
            capture_output=True, text=True, check=False, timeout=60,
        )
    except Exception as exc:
        log.warning("DB non raggiungibile per l'arricchimento (%s): None ovunque", exc)
        return {}
    if res.returncode != 0:
        log.warning("psql fallito: %s", res.stderr.strip()[:200])
        return {}
    out: dict[int, dict] = {}
    for line in res.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("|")
        if len(parts) < 7:
            continue
        sid, model_id, ensemble_std, extraction_method, source, published_at, n_ticker = parts[:7]
        out[int(sid)] = {
            "model_id": model_id if model_id else None,
            "ensemble_std": _maybe_float(ensemble_std),
            "extraction_method": extraction_method if extraction_method else None,
            "source": source if source else None,
            "published_at": published_at if published_at else None,
            "n_ticker_articolo": int(n_ticker) if n_ticker else None,
        }
    return out


def _maybe_float(v: str | None) -> float | None:
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def _sector_by_ticker() -> dict[str, str]:
    """Inverte la tassonomia settoriale di trading.yaml (read-only)."""
    import yaml
    with open(TRADING_YAML, encoding="utf-8") as f:
        sectors = yaml.safe_load(f).get("sectors") or {}
    return {
        str(symbol): str(sector)
        for sector, symbols in sectors.items()
        for symbol in (symbols or [])
    }


# ---------------------------------------------------------------------------
# Assemblaggio righe arricchite per il pannello.
# ---------------------------------------------------------------------------


def _anchor_ts(signal: dict) -> dt.datetime | None:
    """Timestamp OSSERVABILE del segnale: ``stages.scored_at.bar_timestamp``
    (prima barra SIP 5Min allineata allo score). None se assente."""
    scored = (signal.get("stages") or {}).get("scored_at") or {}
    ts = scored.get("bar_timestamp") or scored.get("timestamp")
    if not ts:
        return None
    try:
        return dt.datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None


def _benchmark_fwd(
    anchor: dt.datetime | None, bars: dict, horizon: str
) -> float | None:
    """Forward return del benchmark (SPY/ETF) allo stesso anchor del segnale."""
    if anchor is None or not bars.get("intraday") or not bars.get("daily"):
        return None
    fr = compute_forward_returns(anchor, bars["intraday"], bars["daily"])
    return (fr.get(horizon) or {}).get("return")


def _build_signal_rows(
    dossier: dict,
    sectors: dict[str, str],
    bar_loader,
    db_enricher,
) -> tuple[list[dict], list[dict], list[dict], list[str]]:
    """Costruisce signal_rows arricchite + pool_rows per un giorno.

    Restituisce ``(signal_rows, pool_rows, errors, signal_ids)``.
    """
    data = dossier["data"]
    soglia_mover = float(dossier.get("soglia_mover") or 0.03)
    rendimenti = (dossier.get("mercato") or {}).get("rendimenti") or {}

    signals = [t for t in dossier.get("timeline") or [] if t.get("kind") == "signal"]
    signal_ids = [s.get("signal_id") for s in signals if s.get("signal_id") is not None]
    enrich = db_enricher(signal_ids) if signal_ids else {}

    # pool: candidati_miss SENZA segnali (ticker non segnalati, movers non detenuti).
    pool_rows: list[dict] = []
    for c in dossier.get("candidati_miss") or []:
        if c.get("segnali"):  # ha segnali -> e' un signal row, non un control
            continue
        sym = c.get("symbol")
        pool_rows.append({
            "signal_id": None,
            "ticker": sym,
            "data": data,
            "score": None,
            "return": _maybe_float(c.get("return")),
            "is_mover": abs(_maybe_float(c.get("return")) or 0.0) >= soglia_mover,
            "sector": sectors.get(sym),
            "source": None, "model": None, "fallback": None,
            "extraction_method": None, "ensemble_std": None,
            "ensemble_std_bucket": "unknown",
            "n_ticker_articolo": None,
            "forward_returns": {},
            "benchmark_returns": {},
            "control_kind": "ticker_level_non_signaled",
        })

    # cache barre per (symbol, day) + benchmark di libro + ETF di settore.
    bar_cache: dict[str, dict] = {}

    def _bars(sym: str) -> dict:
        if sym not in bar_cache:
            try:
                bar_cache[sym] = bar_loader(sym, dt.date.fromisoformat(data))
            except Exception as exc:
                log.warning("bar_loader(%s@%s) fallito: %s", sym, data, exc)
                bar_cache[sym] = {"intraday": [], "daily": []}
        return bar_cache[sym]

    signal_rows: list[dict] = []
    errors: list[str] = []
    for s in signals:
        sym = s.get("symbol")
        sid = s.get("signal_id")
        anchor = _anchor_ts(s)
        e = enrich.get(sid, {}) if sid is not None else {}

        sym_bars = _bars(sym) if sym else {"intraday": [], "daily": []}
        fwd = compute_forward_returns(anchor, sym_bars["intraday"], sym_bars["daily"]) \
            if anchor else _empty_forward_returns()

        # benchmark di libro: SPY sempre; ETF di settore se settore noto.
        spy_bars = _bars(_BENCHMARK_SYMBOL)
        sector = sectors.get(sym)
        etf = SECTOR_BENCHMARK.get(sector) if sector else None
        etf_bars = _bars(etf) if etf else {"intraday": [], "daily": []}

        benchmark_returns: dict[str, dict] = {}
        for h in HORIZONS:
            benchmark_returns[h] = {
                "spy": _benchmark_fwd(anchor, spy_bars, h),
                "sector": _benchmark_fwd(anchor, etf_bars, h) if etf else None,
            }

        signal_rows.append({
            "signal_id": sid,
            "ticker": sym,
            "data": data,
            "score": _maybe_float(s.get("score")),
            "return": _maybe_float(rendimenti.get(sym)) if sym else None,
            "is_mover": bool(s.get("is_mover")),
            "sector": sector,
            "source": e.get("source"),
            "model": e.get("model_id"),
            "fallback": s.get("fallback"),
            "extraction_method": e.get("extraction_method"),
            "ensemble_std": e.get("ensemble_std"),
            "ensemble_std_bucket": "unknown",  # riassegnato dopo (terzile)
            "n_ticker_articolo": e.get("n_ticker_articolo"),
            "forward_returns": {
                h: (fwd.get(h) or {}).get("return") for h in HORIZONS
            },
            "benchmark_returns": benchmark_returns,
        })
        if anchor is None:
            errors.append(f"{sym}@{data}: anchor scored_at mancante")
        if not sym_bars.get("intraday"):
            errors.append(f"{sym}@{data}: barre intraday mancanti")

    # bucket ensemble_std a livello di giorno (terzile descrittivo).
    buckets, edges = assign_ensemble_std_buckets(signal_rows)
    for row, b in zip(signal_rows, buckets):
        row["ensemble_std_bucket"] = b

    return signal_rows, pool_rows, errors, list(edges) + [len(signal_rows), len(pool_rows)]


def _empty_forward_returns() -> dict:
    return {h: {"return": None, "missingness": "anchor_missing"} for h in HORIZONS}


# ---------------------------------------------------------------------------
# Entry point.
# ---------------------------------------------------------------------------


def costruisci(
    *,
    dossier_dir: Path = DOSSIER_DIR,
    bar_loader=_default_bar_loader,
    db_enricher=_default_db_enricher,
    sectors: dict[str, str] | None = None,
    out_path: Path = OUT,
    write: bool = True,
) -> dict:
    """Legge i dossier, arricchisce le righe, delega al modulo puro, restituisce
    il report (signal_diagnostics.json) e l'esito."""
    dossier_paths = sorted(dossier_dir.glob("*.json"))
    if not dossier_paths:
        raise SystemExit(f"Nessun dossier in {dossier_dir}.")

    sectors = sectors if sectors is not None else _sector_by_ticker()

    panels: list[dict] = []
    all_errors: list[str] = []
    n_signals = 0
    n_movers = 0
    n_pool = 0
    giorni: list[str] = []

    for path in dossier_paths:
        with open(path, encoding="utf-8") as f:
            dossier = json.load(f)
        data = dossier["data"]
        giorni.append(data)
        soglia_mover = float(dossier.get("soglia_mover") or 0.03)

        signal_rows, pool_rows, errors, _meta = _build_signal_rows(
            dossier, sectors, bar_loader, db_enricher,
        )
        panel = build_signal_diagnostics_panel(
            signal_rows, pool_rows=pool_rows, mover_threshold=soglia_mover,
        )
        panels.append(panel)
        n_signals += len(signal_rows)
        n_movers += sum(1 for r in signal_rows if r.get("is_mover"))
        n_pool += len(pool_rows)
        all_errors.extend(errors)

    rollup = build_signal_diagnostics_rollup(panels)

    report = {
        "schema_version": SIGNAL_DIAGNOSTICS_SCHEMA_VERSION,
        "generato_il": dt.datetime.now(dt.timezone.utc).isoformat(),
        "n_giorni": len(giorni),
        "giorni": giorni,
        "n_signals": n_signals,
        "n_movers": n_movers,
        "n_pool_controlli": n_pool,
        "panels": panels,
        "rollup": rollup,
        "errors": all_errors,
        "policy_output": "descriptive_only",
        "freeze": {
            "mode": "read_only_measurement",
            "live_thresholds_weights_flags_changed": False,
            "mover_threshold_source": "dossier.soglia_mover (declared, not tuned here)",
            "threshold_grid_is_predefined_and_descriptive": True,
            "anchor": "stages.scored_at.bar_timestamp (PIT, observable signal time)",
        },
        "provenance": {
            "dossier": "docs/evidence/dossier/*.json (read-only)",
            "sectors": "config/trading.yaml (read-only)",
            "enrichment": "Postgres sentiment_signals+news_log via docker exec psql (fail-soft)",
            "bars": "Alpaca SIP 5Min intraday + daily (fail-soft)",
            "note": (
                "File derivato e rigenerabile, NON evidenza primaria. Strumento di "
                "misura sull'evidenza congelata. Nessuna soglia/gate/modello/fonte "
                "live scelta. Pool (controlli matched) = candidati_miss senza "
                "segnali; match su return del giorno; forward-return del pool non "
                "calcolato (missingness dichiarata)."
            ),
        },
    }

    if write:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_suffix(out_path.suffix + ".tmp")
        tmp.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(out_path)
        log.info("scritto: %s", out_path)
    return report


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-write", action="store_true", help="non scrivere, solo stdout")
    ap.add_argument("--out", default=str(OUT), help="percorso del file di output")
    args = ap.parse_args()

    report = costruisci(write=not args.no_write, out_path=Path(args.out))
    log.info(
        "giorni %d | segnali %d | movers %d | controlli pool %d | errori %d",
        report["n_giorni"], report["n_signals"], report["n_movers"],
        report["n_pool_controlli"], len(report["errors"]),
    )
    for e in report["errors"][:20]:
        log.warning("  - %s", e)
    log.info("policy_output=%s freeze.mode=%s", report["policy_output"],
             report["freeze"]["mode"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
