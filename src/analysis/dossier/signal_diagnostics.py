"""Diagnostica dei segnali e controlli negativi (#283).

Modulo puro: riceve segnali, forward return e benchmark gia' caricati (dalle
barre Alpaca) e restituisce metriche descrittive. Niente I/O, DB, rete. Lo schema
e' versionato (``SIGNAL_DIAGNOSTICS_SCHEMA_VERSION``) e ogni metrica porta ``n``
e missingness esplicita: un buco di dato non si confonde mai con zero, e una
cella con pochi osservazioni non si spaccia per stima solida.

Cosa misura (tutto time-forward, PIT dal timestamp osservabile del segnale):

* **rank IC** Spearman fra score e forward return, per orizzonte
  (30m/60m/EOD/T+1/T+3/T+5), con ``n`` e CI bootstrap. La IC e' **residualizzata**
  vs SPY e vs settore (beta=1 proxy: ``signal_fwd - benchmark_fwd`` sulla stessa
  finestra): la IC close-to-close rispetto a un segnale tardivo ha reverse
  causality (#283, ``Perche'``), qui si usa il rendimento successivo al timestamp
  osservabile.
* **hit rate / precision / recall** dei mover azionabili. La soglia mover arriva
  dal dossier (gia' dichiarata, ``soglia_mover``): non e' una nuova taratura.
* **quintili** per score -> forward return medio per bucket.
* **splits** per source/model/fallback/extraction/ensemble_std, con ``n`` per
  cella.
* **falsi positivi** (score alto, rendimento avverso).
* **controlli matched** riproducibili (stesso giorno/settore, matching
  deterministico nearest-by-return, senza random) — separati dal benchmark di
  libro (SPY/settore): il matched control e' un ticker non segnalato, il book
  benchmark e' il fattore sistematico. Due controlli distinti, mai fusi.
* **score stability** (ICIR della serie di IC per giorno).
* **shadow curves** descrittive (serie + cumulati cross-day).

Freeze (#171): solo misura. ``policy_output = "descriptive_only"``. La griglia di
sweep sulle soglie e' una costante dichiarata (``DEFAULT_THRESHOLD_GRID``) e
nessuna soglia viene scelta qui: si riporta precision/recall a OGNI soglia. La
moltiplcita' (orizzonti x splits x soglie) e' dichiarata (``n_trials``) e la
significativita' e' riportata col Deflated Sharpe Ratio di
``src/backtest/metrics/signal_quality`` (Bailey & Lopez de Prado 2014), marcata
descrittiva.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np

from src.backtest.metrics.signal_quality import (
    ic_pvalue,
    icir_from_series,
    information_coefficient,
)

SIGNAL_DIAGNOSTICS_SCHEMA_VERSION = "1.0"

# Orizzonti richiesti dalla issue (#283), dal piu' breve al piu' lungo. Tutti
# ancorati allo stesso entry price PIT (prezzo al timestamp del segnale).
HORIZONS = ("30m", "60m", "EOD", "T+1", "T+3", "T+5")

# Minuti dopo il segnale per gli orizzonti intraday.
_HORIZON_MINUTES = {"30m": 30, "60m": 60}

# Griglia di sweep PREDEFINITA e fissa: dichiarata, non ottimizzata. Si riportano
# precision/recall a ciascuna soglia senza sceglierne alcuna. 0.30 e' il gate S4
# dichiarato (config/trading.yaml) incluso come riferimento, non come scelta.
DEFAULT_THRESHOLD_GRID = (0.10, 0.20, 0.30, 0.40, 0.50, 0.60)

UTC = timezone.utc


def _as_utc(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def compute_forward_returns(
    signal_ts: str | datetime,
    intraday_bars: list[dict],
    daily_bars: list[dict],
    *,
    session_open: str | datetime | None = None,
    session_close: str | datetime | None = None,
    horizons: tuple[str, ...] = HORIZONS,
) -> dict[str, Any]:
    """Forward return time-forward per ogni orizzonte, PIT dal timestamp del segnale.

    Puro: niente I/O. ``intraday_bars`` e' una lista di barre 5Min (o qualsiasi
    granularita') ciascuna con ``timestamp`` (ISO UTC), ``open`` e ``close``;
    ``daily_bars`` e' una lista di barre giornaliere ciascuna con ``date`` (ISO)
    e ``close``, ordinate per data crescente e a partire dal giorno del segnale
    (``daily_bars[0]`` = giorno del segnale, ``[n]`` = T+n).

    Contratto PIT (no leakage):
        entry_price = open della prima barra intraday con ``timestamp >= signal_ts``.
        Se ``signal_ts`` e' prima dell'open, la prima barra >= ts e' quella di
        apertura (non si puo' tradare pre-market). Se ``signal_ts`` e' dopo la
        chiusura e le barre coprono piu' giorni, l'entry rolla naturalmente alla
        prima barra della seduta successiva: la funzione e' session-agnostica,
        usa solo le barre che le si danno.
        30m/60m = close della prima barra >= signal_ts + delta.
        EOD = close della barra giornaliera del giorno segnale (``daily_bars[0]``).
        T+n = close di ``daily_bars[n]``.

    Ogni orizzonte porta ``return`` (o ``None``) e ``missingness`` (lista di
    reason). Quando l'entry manca, tutti gli orizzonti sono ``None`` con
    ``entry_bar_missing``: non si inventa un anchor.
    """
    ts = _as_utc(signal_ts)
    if ts is None:
        return _all_missing(horizons, ["signal_ts_missing"])

    # --- entry: prima barra intraday >= signal_ts ---------------------------
    entry_price: float | None = None
    entry_bar_ts: str | None = None
    for bar in sorted(intraday_bars, key=lambda b: b.get("timestamp") or ""):
        bt = _as_utc(bar.get("timestamp"))
        if bt is None:
            continue
        if bt >= ts:
            entry_price = _float(bar.get("open"))
            entry_bar_ts = bt.isoformat()
            break

    entry_missing = entry_price is None or entry_price <= 0
    out: dict[str, Any] = {
        "schema_version": SIGNAL_DIAGNOSTICS_SCHEMA_VERSION,
        "horizons": list(horizons),
        "entry_price": entry_price if not entry_missing else None,
        "entry_bar_ts": entry_bar_ts,
        "entry_source": "intraday_open" if not entry_missing else None,
    }

    for h in horizons:
        out[h] = _horizon_return(
            h, ts, entry_price, entry_missing, intraday_bars, daily_bars
        )
    return out


def _all_missing(horizons: tuple[str, ...], reasons: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "schema_version": SIGNAL_DIAGNOSTICS_SCHEMA_VERSION,
        "horizons": list(horizons),
        "entry_price": None,
        "entry_bar_ts": None,
        "entry_source": None,
    }
    for h in horizons:
        out[h] = {"return": None, "exit_price": None, "exit_bar_ts": None,
                  "missingness": list(reasons)}
    return out


def _horizon_return(
    horizon: str,
    signal_ts: datetime,
    entry_price: float | None,
    entry_missing: bool,
    intraday_bars: list[dict],
    daily_bars: list[dict],
) -> dict[str, Any]:
    if entry_missing:
        return {"return": None, "exit_price": None, "exit_bar_ts": None,
                "missingness": ["entry_bar_missing"]}

    missingness: list[str] = []
    # --- orizzonti intraday: 30m / 60m -------------------------------------
    if horizon in _HORIZON_MINUTES:
        target = signal_ts + timedelta(minutes=_HORIZON_MINUTES[horizon])
        exit_price, exit_ts = _first_bar_close_after(intraday_bars, target)
        if exit_price is None:
            missingness.append("intraday_bar_missing_after_horizon")
            return _none_return(missingness)
        return _return_block(entry_price, exit_price, exit_ts, missingness)

    # --- orizzonti daily: EOD / T+1 / T+3 / T+5 ----------------------------
    n = _daily_index(horizon)  # EOD->0, T+1->1, T+3->3, T+5->5
    if n is None or len(daily_bars) <= n:
        missingness.append("daily_bar_missing")
        return _none_return(missingness)
    exit_price = _float(daily_bars[n].get("close"))
    exit_date = daily_bars[n].get("date")
    if exit_price is None or exit_price <= 0:
        missingness.append("daily_close_missing")
        return _none_return(missingness)
    return _return_block(entry_price, exit_price, exit_date, missingness)


def _daily_index(horizon: str) -> int | None:
    if horizon == "EOD":
        return 0
    if horizon.startswith("T+"):
        try:
            return int(horizon[2:])
        except ValueError:
            return None
    return None


def _first_bar_close_after(bars: list[dict], target: datetime) -> tuple[float | None, str | None]:
    """Close della prima barra con timestamp >= target."""
    for bar in sorted(bars, key=lambda b: b.get("timestamp") or ""):
        bt = _as_utc(bar.get("timestamp"))
        if bt is None or bt < target:
            continue
        close = _float(bar.get("close"))
        if close is None:
            continue
        return close, bt.isoformat()
    return None, None


def _return_block(entry: float, exit_price: float, exit_ts: str | None,
                   missingness: list[str]) -> dict[str, Any]:
    return {
        "return": exit_price / entry - 1.0 if entry and entry > 0 else None,
        "exit_price": exit_price,
        "exit_bar_ts": exit_ts,
        "missingness": missingness,
    }


def _none_return(missingness: list[str]) -> dict[str, Any]:
    return {"return": None, "exit_price": None, "exit_bar_ts": None,
            "missingness": missingness}


# ---------------------------------------------------------------------------
# IC, residualizzazione, hit/precision/recall, quintili, falsi positivi
# ---------------------------------------------------------------------------
# La IC Spearman e il p-value sono calcolati con ``src.backtest.metrics.
# signal_quality`` (gia' validato in #180 e usato da compute_s4_ic.py): non si
# reinventa la formula. Qui si aggiungono n, CI bootstrap e la residualizzazione
# vs benchmark di libro (SPY/settore), che e' la parte nuova richiesta da #283.

# IC con pochi punti e' rumore: sotto questa soglia la metrica e' debole.
_MIN_IC_N = 3
# Seed del bootstrap: fisso per riproducibilita'. Non e' una taratura, e' la
# determinazione di un intervallo di confidenza descrittivo.
_BOOTSTRAP_SEED = 20260803


def _pairs(scores, returns) -> list[tuple[float, float]]:
    """Coppie (score, return) con entrambi i valori finiti: drop dei missing."""
    out = []
    for s, r in zip(scores, returns):
        sf, rf = _float(s), _float(r)
        if sf is None or rf is None:
            continue
        out.append((sf, rf))
    return out


def residualize(
    signal_returns: list[float | None], benchmark_returns: list[float | None]
) -> list[float | None]:
    """Residuo beta=1: ``signal_fwd - benchmark_fwd`` sulla stessa finestra.

    Puro, elemento per elemento. Se uno dei due e' None il residuo e' None:
    non si inventa il benchmark mancante. Il benchmark e' il fattore sistematico
    (SPY o ETF settoriale) sulla STESSA finestra [signal_ts, signal_ts+orizzonte]:
    e' il ``book benchmark``, distinto dal ``matched control`` (ticker non
    segnalato) che vive in ``matched_controls``.
    """
    out: list[float | None] = []
    for s, b in zip(signal_returns, benchmark_returns):
        sf, bf = _float(s), _float(b)
        if sf is None or bf is None:
            out.append(None)
        else:
            out.append(sf - bf)
    return out


def rank_ic_with_ci(
    scores: list[float],
    returns: list[float | None],
    *,
    n_bootstrap: int = 1000,
    seed: int = _BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """Rank IC Spearman fra score e forward return, con n, p-value e CI bootstrap.

    Puro. Riporta sempre ``n`` (coppie valide) e marcatore ``weak`` quando n e'
    sotto la soglia minima: una IC su 2 punti non e' una stima, e non si spaccia
    per tale. Il CI e' bootstrap (percentile 2.5/97.5), seed fisso per
    riproducibilita' — e' un intervallo descrittivo, non una scelta operativa.
    """
    pairs = _pairs(scores, returns)
    n = len(pairs)
    if n < _MIN_IC_N:
        return {"ic": None, "n": n, "pvalue": None, "ci_lo": None, "ci_hi": None,
                "weak": True, "method": "spearman_bootstrap"}
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    ic = information_coefficient(xs, ys)
    pvalue = ic_pvalue(xs, ys)
    ci_lo, ci_hi = _bootstrap_ic_ci(pairs, n_bootstrap, seed)
    return {"ic": ic, "n": n, "pvalue": pvalue, "ci_lo": ci_lo, "ci_hi": ci_hi,
            "weak": False, "method": "spearman_bootstrap"}


def _spearman_fast(xs: np.ndarray, ys: np.ndarray) -> float | None:
    """Spearman veloce: Pearson sui rank. Usato solo dentro il bootstrap (1000x):
    la stima puntuale e il p-value restano su ``signal_quality`` (scipy), per DRY
    e coerenza col resto del codebase. Qui si evita di chiamare scipy.stats
    1000 volte per cella. Ritorna None su input costante (IC non definita)."""
    if np.std(xs) == 0 or np.std(ys) == 0:
        return None
    from scipy.stats import rankdata
    rx = rankdata(xs)
    ry = rankdata(ys)
    corr = float(np.corrcoef(rx, ry)[0, 1])
    return None if np.isnan(corr) else corr


def _bootstrap_ic_ci(
    pairs: list[tuple[float, float]], n_bootstrap: int, seed: int
) -> tuple[float | None, float | None]:
    """CI percentile (2.5/97.5) della IC via resampling con replacement.

    Usa ``_spearman_fast`` (Pearson sui rank) per le 1000 iterazioni: il CI e'
    descrittivo e non richiede la macchina pesante di ``spearmanr``. La stima
    puntuale resta su ``signal_quality``.
    """
    arr = np.asarray(pairs, dtype=float)
    n = len(arr)
    rng = np.random.default_rng(seed)
    ics = []
    for _ in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        sample = arr[idx]
        ic = _spearman_fast(sample[:, 0], sample[:, 1])
        if ic is not None:
            ics.append(ic)
    if len(ics) < 2:
        return None, None
    lo = float(np.percentile(ics, 2.5))
    hi = float(np.percentile(ics, 97.5))
    return lo, hi


def hit_rate(scores: list[float], returns: list[float | None]) -> dict[str, Any]:
    """Hit rate del segno: frazione di segnali con sign(score)==sign(return).

    Zero score o zero return contano come miss (non si predice niente). ``n`` e'
    il numero di coppie valide (entrambi finiti).
    """
    pairs = _pairs(scores, returns)
    n = len(pairs)
    if n == 0:
        return {"hit_rate": None, "n": 0}
    hits = sum(1 for s, r in pairs if s != 0 and r != 0 and (s > 0) == (r > 0))
    return {"hit_rate": hits / n, "n": n}


def precision_recall(
    rows: list[dict],
    threshold: float,
    *,
    mover_threshold: float,
    direction: str = "long",
) -> dict[str, Any]:
    """Precision/recall dei mover azionabili a una soglia di score.

    ``direction="long"`` (book long-only, l'azione catturabile): segnale positivo
    = score >= threshold, esito positivo = return >= +mover_threshold.
    ``direction="short"``: segnale positivo = score <= -threshold, esito = return
    <= -mover_threshold (descrittivo: il book long-only non potra' eseguirlo).

    La soglia mover e' quella DICHIARATA dal dossier (``soglia_mover``): non e' una
    nuova taratura. La soglia di score e' un punto di una griglia predefinita e
    descrittiva: nessuna soglia viene scelta qui.

    recall con denominatore 0 (nessun mover) -> None, non NaN: e' indefinito, non
    zero. precision con nessun segnale -> None.
    """
    tp = fp = fn = tn = 0
    for row in rows:
        score = _float(row.get("score"))
        ret = _float(row.get("return"))
        if score is None or ret is None:
            continue
        if direction == "long":
            signal = score >= threshold
            outcome = ret >= mover_threshold
        else:  # short
            signal = score <= -threshold
            outcome = ret <= -mover_threshold
        if signal and outcome:
            tp += 1
        elif signal and not outcome:
            fp += 1
        elif not signal and outcome:
            fn += 1
        else:
            tn += 1
    n_signals = tp + fp
    n_movers = tp + fn
    precision = tp / n_signals if n_signals else None
    recall = tp / n_movers if n_movers else None
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": precision, "recall": recall,
        "n_signals": n_signals, "n_movers": n_movers,
        "threshold": threshold, "mover_threshold": mover_threshold,
        "direction": direction,
    }


def quintile_analysis(
    scores: list[float], returns: list[float | None], *, n_buckets: int = 5
) -> list[dict[str, Any]]:
    """Bucketta per score quintile e riporta forward return medio per bucket.

    Puro, descrittivo. Ordina per score crescente, assegna bucket =
    ``floor(rank * n_buckets / n)`` (riempimento il piu' uniforme possibile). I
    bucket vuoti (pochi dati) hanno n=0 e mean_return=None. Ogni bucket porta n,
    mean_score, mean_return: una cella con pochi n non si spaccia per stima.
    """
    pairs = _pairs(scores, returns)
    n = len(pairs)
    if n == 0:
        return [_empty_bucket(i + 1) for i in range(n_buckets)]
    pairs.sort(key=lambda p: p[0])
    buckets: list[list[tuple[float, float]]] = [[] for _ in range(n_buckets)]
    for rank, (s, r) in enumerate(pairs):
        b = min(int(rank * n_buckets / n), n_buckets - 1)
        buckets[b].append((s, r))
    out = []
    for i, group in enumerate(buckets):
        if not group:
            out.append(_empty_bucket(i + 1))
            continue
        rets = [r for _, r in group]
        scs = [s for s, _ in group]
        out.append({
            "bucket": i + 1,
            "n": len(group),
            "mean_score": sum(scs) / len(scs),
            "mean_return": sum(rets) / len(rets),
        })
    return out


def _empty_bucket(i: int) -> dict[str, Any]:
    return {"bucket": i, "n": 0, "mean_score": None, "mean_return": None}


def false_positives(rows: list[dict], threshold: float) -> dict[str, Any]:
    """Falsi positivi: score alto (>= threshold) con rendimento avverso (< 0).

    Puro, descrittivo. ``mean_adverse_return`` e' la media dei rendimenti negativi
    dei falsi positivi (None se nessun FP). ``n_signals`` e' il totale dei segnali
    sopra soglia (denominatore della precision sui soli FP-di-segno).
    """
    adverse: list[float] = []
    n_signals = 0
    for row in rows:
        score = _float(row.get("score"))
        ret = _float(row.get("return"))
        if score is None or ret is None:
            continue
        if score >= threshold:
            n_signals += 1
            if ret < 0:
                adverse.append(ret)
    return {
        "n_fp": len(adverse),
        "mean_adverse_return": (sum(adverse) / len(adverse)) if adverse else None,
        "n_signals": n_signals,
        "threshold": threshold,
    }

# ---------------------------------------------------------------------------
# Matched controls, splits, score stability
# ---------------------------------------------------------------------------
# Il ``matched control`` e' un controllo NEGATIVO ticker-level: un ticker non
# segnalato, stesso giorno/settore, nearest per magnitudo di movimento. E'
# DISTINTO dal ``book benchmark`` (SPY/settore, fattore sistematico, in
# ``residualize``): due controlli separati, mai fusi (AC2 #283). Il matching e'
# DETERMINISTICO (nearest by |return|, tie-break per ticker): niente random,
# riproducibile al byte.


def matched_controls(
    signal_rows: list[dict],
    pool_rows: list[dict],
    *,
    horizon: str,
    sector_key: str = "sector",
    date_key: str = "data",
    return_key: str = "return",
) -> dict[str, Any]:
    """Per ogni segnale-mover, trova un ticker non segnalato matched e confronta
    il forward return allo stesso orizzonte.

    Puro. ``signal_rows`` e ``pool_rows`` portano ``ticker, data, sector, return``
    (movimento del giorno, usato per il matching) e ``forward_returns`` (dict
    per orizzonte, l'esito da confrontare). Il match e' con-replacement (ogni
    segnale sceglie indipendentemente il miglior controllo): descrittivo, non un
    esperimento controllato. Riproducibile perche' l'ordinamento e' deterministico.

    Restituisce ``matches`` (con ``delta = signal_fwd - matched_fwd``) e
    ``unmatched`` (nessun candidato stesso giorno/settore, o forward return
    mancante). Il summary porta ``mean_delta`` (None se nessun delta calcolabile).
    Il risultato NON porta campi SPY/residual: quelli vivono in ``residualize``.
    """
    signal_ids = {(r.get(date_key), r.get("ticker")) for r in signal_rows}
    pool_by_key: dict[tuple, list[dict]] = {}
    for r in pool_rows:
        pool_by_key.setdefault((r.get(date_key), r.get(sector_key)), []).append(r)

    matches: list[dict] = []
    unmatched: list[dict] = []
    deltas: list[float] = []

    for s in signal_rows:
        key = (s.get(date_key), s.get(sector_key))
        s_ret = _float(s.get(return_key))
        cands = [
            c for c in pool_by_key.get(key, [])
            if (c.get(date_key), c.get("ticker")) not in signal_ids
            and c.get("ticker") != s.get("ticker")
        ]
        if not cands or s_ret is None:
            unmatched.append({
                "signal_ticker": s.get("ticker"),
                "data": s.get(date_key),
                "missingness": ["no_matched_control"],
            })
            continue
        chosen = min(
            cands,
            key=lambda c: (abs((_float(c.get(return_key)) or 0.0) - s_ret), c.get("ticker") or ""),
        )
        s_fwd = _float((s.get("forward_returns") or {}).get(horizon))
        m_fwd = _float((chosen.get("forward_returns") or {}).get(horizon))
        match = {
            "signal_ticker": s.get("ticker"),
            "matched_ticker": chosen.get("ticker"),
            "data": s.get(date_key),
            "match_distance": abs((_float(chosen.get(return_key)) or 0.0) - s_ret),
            "signal_fwd": s_fwd,
            "matched_fwd": m_fwd,
            "missingness": [],
        }
        if s_fwd is None or m_fwd is None:
            match["delta"] = None
            match["missingness"].append("forward_return_missing")
        else:
            match["delta"] = s_fwd - m_fwd
            deltas.append(match["delta"])
        matches.append(match)

    return {
        "matches": matches,
        "unmatched": unmatched,
        "summary": {
            "n_matched": len(matches),
            "n_unmatched": len(unmatched),
            "mean_delta": (sum(deltas) / len(deltas)) if deltas else None,
            "n_delta_calcolabile": len(deltas),
            "matching": "deterministic_nearest_by_return_con_replacement",
            "control_kind": "ticker_level_non_signaled (separato dal book benchmark SPY/settore)",
        },
    }


def splits_by_dimension(
    rows: list[dict], dim_key: str, *, horizon: str
) -> dict[str, dict[str, Any]]:
    """Splits per source/model/fallback/extraction/ensemble_std_bucket: per ogni
    valore della dimensione, IC + hit rate con ``n`` per cella.

    Puro, descrittivo. Le celle piccole (n<_MIN_IC_N) sono marcate ``weak`` dalla
    ``rank_ic_with_ci`` e l'``n`` e' sempre riportato: la moltiplcita' delle celle
    e' dichiarata, non nascosta (AC3 #283). ``ensemble_std`` e' continuo: il
    pannello lo bucketizza (terzile) in ``ensemble_std_bucket`` prima di chiamare
    questa funzione, cosi' il split e' uniforme sulle dimensioni categoriche.
    """
    groups: dict[str, list[dict]] = {}
    for r in rows:
        v = r.get(dim_key)
        if v is None:
            continue
        groups.setdefault(str(v), []).append(r)

    out: dict[str, dict[str, Any]] = {}
    for v, grp in groups.items():
        scores = [r.get("score") for r in grp]
        fwd = [(r.get("forward_returns") or {}).get(horizon) for r in grp]
        out[v] = {
            "n": len(grp),
            "ic": rank_ic_with_ci(scores, fwd),
            "hit_rate": hit_rate(scores, fwd),
        }
    return out


def score_stability(ic_series: list[float | None]) -> dict[str, Any]:
    """Stability della IC nel tempo: mean/std/ICIR della serie di IC per giorno.

    Puro. Riporta ``n_days``, ``mean_ic``, ``std_ic`` (ddof=1), ``icir``
    (mean/std, via ``icir_from_series`` annualisation=1) e ``positive_fraction``
    (quota di giorni con IC>0). Con n<2, std e ICIR sono None: una deviazione su
    un punto non e' definita. La metrica e' descrittiva: dice se il segnale e'
    costante o se la sua prediczione va e viene, senza decidere nulla.
    """
    arr = [x for x in ic_series if x is not None]
    n = len(arr)
    if n == 0:
        return {"n_days": 0, "mean_ic": None, "std_ic": None, "icir": None,
                "positive_fraction": None}
    mean_ic = sum(arr) / n
    positive = sum(1 for x in arr if x > 0)
    if n < 2:
        std_ic = None
        icir = None
    else:
        std_ic = float(np.std(arr, ddof=1))
        raw_icir = icir_from_series(arr, annualisation=1)
        icir = None if (raw_icir is None or np.isnan(raw_icir)) else float(raw_icir)
    return {
        "n_days": n,
        "mean_ic": mean_ic,
        "std_ic": std_ic,
        "icir": icir,
        "positive_fraction": positive / n,
    }


# ---------------------------------------------------------------------------
# Panel per-day e rollup cross-day (shadow curves, moltiplcita')
# ---------------------------------------------------------------------------


_SPLIT_DIMENSIONS = (
    "source", "model", "fallback", "extraction_method", "ensemble_std_bucket",
)
_BENCHMARKS = ("raw", "spy_residual", "sector_residual")


def _benchmark_fwd(row: dict, horizon: str, kind: str) -> float | None:
    bench = (row.get("benchmark_returns") or {}).get(horizon) or {}
    return _float(bench.get(kind))


def build_signal_diagnostics_panel(
    signal_rows: list[dict],
    *,
    pool_rows: list[dict],
    mover_threshold: float,
    threshold_grid: tuple[float, ...] = DEFAULT_THRESHOLD_GRID,
) -> dict[str, Any]:
    """Pannello di diagnostica dei segnali per un giorno.

    Puro. ``signal_rows`` sono i segnali arricchiti (score, forward_returns per
    orizzonte, benchmark_returns per orizzonte, return del giorno, settore,
    source/model/fallback/extraction_method/ensemble_std_bucket). ``pool_rows``
    sono i ticker NON segnalati dello stesso giorno, per i matched controls.
    ``mover_threshold`` e' la soglia mover DICHIARATA dal dossier (non una nuova
    taratura): definisce l'up-mover azionabile in book long-only.

    Mappa issue -> blocco:
      * rank IC per orizzonte, raw + residualizzata vs SPY/settore (AC1).
      * hit/precision/recall: sweep sul mover del giorno (azione catturabile),
        singolo sweep sulla griglia predefinita, descrittivo (AC4).
      * quintili per orizzonte.
      * false positivi per orizzonte (score alto, forward return avverso).
      * matched controls per orizzonte (AC2), separati dal book benchmark.
      * splits per source/model/fallback/extraction/ensemble_std_bucket (AC3).
    """
    data = signal_rows[0].get("data") if signal_rows else None
    n_signals = len(signal_rows)
    n_movers = sum(1 for r in signal_rows if r.get("is_mover"))

    rank_ic: dict[str, Any] = {}
    quintiles: dict[str, Any] = {}
    false_pos: dict[str, Any] = {}
    matched: dict[str, Any] = {}
    missingness: list[str] = []

    for h in HORIZONS:
        scores = [r.get("score") for r in signal_rows]
        fwd = [(r.get("forward_returns") or {}).get(h) for r in signal_rows]
        spy = [_benchmark_fwd(r, h, "spy") for r in signal_rows]
        sector = [_benchmark_fwd(r, h, "sector") for r in signal_rows]

        if n_signals and all(f is None for f in fwd):
            missingness.append(f"all_forward_return_missing:{h}")

        rank_ic[h] = {
            "raw": rank_ic_with_ci(scores, fwd),
            "spy_residual": rank_ic_with_ci(scores, residualize(fwd, spy)),
            "sector_residual": rank_ic_with_ci(scores, residualize(fwd, sector)),
        }
        quintiles[h] = quintile_analysis(scores, fwd)
        # false positivi: score alto, forward return avverso (<0) a questo orizzonte.
        fp_rows = [{"score": s, "return": f} for s, f in zip(scores, fwd)]
        false_pos[h] = [false_positives(fp_rows, threshold=t) for t in threshold_grid]
        # matched controls: solo i mover del giorno, confronto forward return.
        movers = [r for r in signal_rows if r.get("is_mover")]
        matched[h] = matched_controls(movers, pool_rows, horizon=h)

    # hit/precision/recall: sweep sul mover del GIORNO (azione catturabile long).
    day_rows = [{"score": r.get("score"), "return": r.get("return")} for r in signal_rows]
    hit_pr = [
        precision_recall(day_rows, threshold=t, mover_threshold=mover_threshold,
                         direction="long")
        for t in threshold_grid
    ]

    # splits per dimensione, per orizzonte.
    splits: dict[str, Any] = {}
    for dim in _SPLIT_DIMENSIONS:
        splits[dim] = {h: splits_by_dimension(signal_rows, dim, horizon=h) for h in HORIZONS}

    return {
        "schema_version": SIGNAL_DIAGNOSTICS_SCHEMA_VERSION,
        "data": data,
        "n_signals": n_signals,
        "n_movers": n_movers,
        "mover_threshold": mover_threshold,
        "threshold_grid": list(threshold_grid),
        "rank_ic": rank_ic,
        "hit_precision_recall": hit_pr,
        "quintiles": quintiles,
        "false_positives": false_pos,
        "matched_controls": matched,
        "splits": splits,
        "missingness": missingness,
        "policy_output": "descriptive_only",
        "freeze": {
            "mode": "read_only_measurement",
            "live_thresholds_weights_flags_changed": False,
            "mover_threshold_source": "dossier.soglia_mover (declared, not tuned here)",
            "threshold_grid_is_predefined_and_descriptive": True,
        },
    }


def _bh_adjust(pvalues: list[float | None]) -> list[float | None]:
    """Benjamini-Hochberg FDR adjustment (descrittivo).

    Ritorna i p-value aggiustati per la moltiplcita' della famiglia. I None
    restano None. E' una correzione descrittiva: non seleziona nulla, rende il
    numero di test esplicito (AC3 #283).
    """
    m = sum(1 for p in pvalues if p is not None)
    if m == 0:
        return list(pvalues)
    indexed = sorted(
        [(i, p) for i, p in enumerate(pvalues) if p is not None],
        key=lambda ip: ip[1],
    )
    raw_adj = [None] * len(pvalues)
    prev = 1.0
    # dal piu' grande al piu' piccolo: p_adj = min(p_i * m / rank, prev)
    for rank_from_top, (orig_i, p) in enumerate(reversed(indexed), start=1):
        rank = m - rank_from_top + 1
        val = min(p * m / rank, prev)
        raw_adj[orig_i] = val
        prev = val
    return raw_adj


def build_signal_diagnostics_rollup(panels: list[dict]) -> dict[str, Any]:
    """Rollup cross-day: shadow curves (serie + cumulati), score stability e
    moltiplcita' (n_trials + BH descrittivo).

    Puro. Le shadow curve sono serie temporali descrittive della IC per giorno,
    per orizzonte e benchmark, con cumulato della media. La score stability e'
    la ICIR della serie di IC per giorno. La moltiplcita' dichiara ``n_trials``
    (orizzonti x benchmark x soglie x dimensioni) e aggiusta i p-value della
    famiglia di IC con Benjamini-Hochberg, marcata descrittiva: nessuna soglia
    viene scelta (AC3, AC4 #283).
    """
    ordered = sorted([p for p in panels if p.get("data")], key=lambda p: p["data"])

    shadow_curves: dict[str, Any] = {}
    stability: dict[str, Any] = {}
    for h in HORIZONS:
        shadow_curves[h] = {}
        stability[h] = {}
        for bench in _BENCHMARKS:
            series: list[dict] = []
            ic_values: list[float | None] = []
            cum = 0.0
            n_cum = 0
            for p in ordered:
                ic = (p.get("rank_ic", {}).get(h, {}).get(bench, {}) or {}).get("ic")
                if ic is not None:
                    cum += ic
                    n_cum += 1
                ic_values.append(ic)
                series.append({
                    "data": p["data"],
                    "ic": ic,
                    "cumulative_mean_ic": (cum / n_cum) if n_cum else None,
                })
            shadow_curves[h][bench] = series
            stability[h][bench] = score_stability(ic_values)

    # moltiplcita': famiglia di IC p-value (orizzonti x benchmark) + n_trials.
    pvalues: list[float | None] = []
    test_labels: list[str] = []
    for p in ordered:
        for h in HORIZONS:
            for bench in _BENCHMARKS:
                pv = (p.get("rank_ic", {}).get(h, {}).get(bench, {}) or {}).get("pvalue")
                pvalues.append(pv)
                test_labels.append(f"{p['data']}:{h}:{bench}")
    adjusted = _bh_adjust(pvalues)
    n_trials = (
        len(HORIZONS) * len(_BENCHMARKS) * len(DEFAULT_THRESHOLD_GRID)
        * len(_SPLIT_DIMENSIONS)
    )
    multiplicity = {
        "n_trials": n_trials,
        "n_ic_tests": sum(1 for pv in pvalues if pv is not None),
        "method": "benjamini_hochberg_descriptive",
        "adjusted_pvalues": [
            {"test": label, "raw_p": raw, "bh_adjusted_p": adj}
            for label, raw, adj in zip(test_labels, pvalues, adjusted)
        ],
        "policy": "descriptive_only_no_threshold_selected",
    }

    return {
        "schema_version": SIGNAL_DIAGNOSTICS_SCHEMA_VERSION,
        "n_giorni": len(ordered),
        "giorni": [p["data"] for p in ordered],
        "shadow_curves": shadow_curves,
        "score_stability": stability,
        "multiplicity": multiplicity,
        "policy_output": "descriptive_only",
        "freeze": {
            "mode": "read_only_measurement",
            "live_thresholds_weights_flags_changed": False,
        },
    }
