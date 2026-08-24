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