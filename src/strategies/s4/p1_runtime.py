"""Adattatore fra il mondo osservabile e la challenger P1 (#297).

Il modulo di decisione (`p1_time_only`) e' puro. Qui vive tutto cio' che tocca
il mondo: la finestra di prezzi eseguibili letta da Alpaca, lo stop congelato
riletto dalla riga di trade, e la scrittura append-only degli esiti.

Nessuna funzione di questo file puo' inviare un ordine: il client di trading
serve solo al calendario, e quello dati solo alle barre storiche.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from src.strategies.s4.lifecycle import MarketSession
from src.strategies.s4.p0_baseline import VersionedTradeCostModel
from src.strategies.s4.p0_runtime import _lifecycle_from_row
from src.strategies.s4.p1_time_only import (
    ExecutableQuote,
    P1MarketWindow,
    decide_p1,
    load_p1_policy_snapshot,
)

log = logging.getLogger(__name__)

# Non chiedere ad Alpaca dati piu' recenti di cosi': una barra ancora in
# formazione farebbe uscire P1 a un prezzo che sarebbe cambiato.
_FEED_DELAY_MIN = 20
# Se la scadenza cade in un giorno senza dati utilizzabili, il primo prezzo
# eseguibile successivo puo' essere sulla seduta dopo. Il contratto lo prevede
# (`exit_price_rule`), quindi la finestra deve arrivare fin li'.
_AFTER_CUTOFF_DAYS = 3

_D_HARD_MULTIPLIER = 1.5
_D_HARD_SIGMA_MULTIPLE = 5.0
_D_HARD_FLOOR = 0.12
_D_HARD_CAP = 0.20


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _d_hard_config() -> dict[str, float]:
    try:
        import yaml

        payload = yaml.safe_load(open("config/trading.yaml", "rb")) or {}
    except Exception as exc:  # noqa: BLE001 - config assente o illeggibile
        log.warning("#297: trading.yaml unavailable for d_hard: %s", exc)
        return {}
    for section in payload.values():
        if isinstance(section, dict) and "broker_disaster_stop" in section:
            return section["broker_disaster_stop"] or {}
    return payload.get("broker_disaster_stop") or {}


def d_hard_distance(row: dict[str, Any], cfg: dict[str, float]) -> float | None:
    """Distanza dello stop comune, ricostruita **come era all'ingresso**.

    `StopPolicy.d_hard` usa la sigma corrente; qui vale quella congelata sulla
    riga di trade. La differenza non e' un dettaglio: usare la volatilita' di
    oggi per decidere un'uscita di due giorni fa e' look-ahead, e falserebbe
    proprio il confronto che il trial deve misurare.

    Dalla riga di trade vengono **solo** `stop_d_init` e `stop_vol_at_entry`.
    I confini restano quelli di `broker_disaster_stop`, come in
    `StopPolicy.d_hard`: `stop_floor` e `stop_cap` sulla stessa riga sono i
    confini dello stop **protettivo** di sleeve (S4: 0.03-0.08), un'altra cosa.
    Clipparci il disaster stop darebbe a P1 una soglia molto piu' stretta di
    quella comune — una violazione di `identical_across_policies`, con P1 che
    esce per rischio dove nessun'altra policy lo farebbe.

    Senza `stop_d_init` la distanza non e' ricostruibile e vale `None`: la
    decisione lo dichiara con `D_HARD_NOT_EVALUABLE` invece di inventare uno
    stop che nessun prezzo puo' bucare.
    """
    d_init = row.get("stop_d_init")
    if d_init is None:
        return None
    sigma = row.get("stop_vol_at_entry")
    base = max(
        float(cfg.get("multiplier", _D_HARD_MULTIPLIER)) * float(d_init),
        float(cfg.get("sigma_multiple", _D_HARD_SIGMA_MULTIPLE)) * float(sigma or 0.0),
    )
    floor = float(cfg.get("floor_pct", _D_HARD_FLOOR))
    cap = float(cfg.get("cap_pct", _D_HARD_CAP))
    return min(max(base, floor), cap)


def _cutoff(
    due_session, sessions: list[MarketSession]
) -> tuple[datetime | None, datetime | None]:
    """Close effettiva della seduta di scadenza: half-day e festivi inclusi.

    Il contratto dice `half_days_and_holidays: seguono la close effettiva del
    calendario`, quindi il confine non si deduce da un orario fisso.
    """
    if due_session is None:
        return None, None
    for session in sessions:
        if session.session_date == due_session:
            close_at = _utc(session.close_at)
            return close_at, close_at
    return None, None


def build_window(
    bars, cutoff_at: datetime | None, *, now: datetime
) -> P1MarketWindow:
    """Traduce le barre in prezzi eseguibili, senza il closing print teorico.

    Il prezzo di ogni barra e' il suo `close` — l'ultimo scambio davvero
    avvenuto in quel minuto — e il `low` serve solo a sapere se lo stop e'
    stato bucato dentro la barra. La finestra e' `complete` solo quando il
    cutoff e' passato *e* i dati lo coprono: dichiararla completa in anticipo
    farebbe uscire P1 su una seduta ancora aperta.
    """
    quotes = tuple(
        ExecutableQuote(at=_utc(at), price=float(close), low=float(low))
        for at, close, low in bars
        if close is not None and low is not None
    )
    complete = cutoff_at is not None and _utc(now) >= _utc(cutoff_at)
    return P1MarketWindow(
        quotes=quotes,
        session_close_at=cutoff_at,
        cutoff_at=cutoff_at,
        complete=complete,
    )


def _fetch_bars(data_client, symbol: str, start: datetime, end: datetime):
    from alpaca.data.enums import Adjustment
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    if end <= start:
        return []
    request = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Minute,
        start=start,
        end=end,
        adjustment=Adjustment.ALL,
    )
    payload = data_client.get_stock_bars(request)
    bars = getattr(payload, "data", {}).get(symbol, []) if payload is not None else []
    return [
        (bar.timestamp, bar.close, bar.low)
        for bar in bars
        if getattr(bar, "timestamp", None) is not None
    ]


def project_p1_candidates(
    store,
    data_client,
    sessions: list[MarketSession],
    *,
    observed_at: datetime | None = None,
) -> int:
    """Proietta P1 sugli intenti aperti; sul broker soltanto letture storiche."""
    rows = store.fetch_s4_p1_candidates()
    if not rows:
        return 0
    now = _utc(observed_at or datetime.now(UTC))
    snapshot = load_p1_policy_snapshot()
    cost_model = VersionedTradeCostModel()
    cfg = _d_hard_config()

    events = []
    for row in rows:
        lifecycle = _lifecycle_from_row(row)
        cutoff_at, _ = _cutoff(lifecycle.due_session, sessions)
        start = lifecycle.filled_at or lifecycle.observed_at
        end = min(
            now - timedelta(minutes=_FEED_DELAY_MIN),
            (cutoff_at or now) + timedelta(days=_AFTER_CUTOFF_DAYS),
        )
        try:
            bars = _fetch_bars(data_client, lifecycle.symbol, _utc(start), end)
        except Exception as exc:  # noqa: BLE001 - il client Alpaca non ha una base comune
            log.warning("#297: bars unavailable for %s: %s", lifecycle.symbol, exc)
            bars = []
        events.append(
            decide_p1(
                lifecycle,
                build_window(bars, cutoff_at, now=now),
                snapshot,
                cost_model,
                d_hard_distance=d_hard_distance(row, cfg),
                observed_at=now,
            )
        )

    store.write_s4_exit_policy_events(events)
    return len(events)
