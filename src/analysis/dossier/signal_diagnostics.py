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

import numpy as np

from src.backtest.metrics.signal_quality import (
    ic_pvalue,
    information_coefficient,
)

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


def _bootstrap_ic_ci(
    pairs: list[tuple[float, float]], n_bootstrap: int, seed: int
) -> tuple[float | None, float | None]:
    """CI percentile (2.5/97.5) della IC via resampling con replacement."""
    arr = np.asarray(pairs, dtype=float)
    n = len(arr)
    rng = np.random.default_rng(seed)
    ics = []
    for _ in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        sample = arr[idx]
        xs, ys = sample[:, 0], sample[:, 1]
        if np.std(xs) == 0 or np.std(ys) == 0:
            continue  # campione degenere (costante): IC non definita, salta
        ic = information_coefficient(xs.tolist(), ys.tolist())
        if ic is not None and not (isinstance(ic, float) and np.isnan(ic)):
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