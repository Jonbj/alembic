"""Motore di backtest mensile della manica S3 del POC (#84).

Regole congelate nel manifest, qui eseguite:

- segnale al close dell'ultima seduta del mese, fill all'open della seduta
  successiva; i fill same-bar sono vietati per costruzione (il piano entra
  in ``pending`` alla seduta del segnale e viene consumato solo alla
  seduta dopo);
- fallback sul close della stessa seduta di esecuzione quando l'open non
  e' affidabile (flag ``open_reliable``) o e' mancante; se anche il close
  manca il singolo nome si salta (esclusione locale, il mese non si
  cancella);
- costi letti SOLO dal manifest congelato: half-spread + impact
  square-root (riuso del modello di produzione) + commissioni per azione
  + fee SEC/FINRA sulle vendite, scalati dal moltiplicatore di scenario;
- portafoglio in azioni con drift intra-mese (i pesi sono target al
  ribilancio, non rendimenti pesati statici);
- delisting come rendimento economico esplicito sulla data di delisting:
  la posizione vale ``ultimo_close x (1 + delisting_return)`` e va in
  cassa; un delisting con ``missing_status`` non e' valutabile: la
  posizione resta all'ultimo close, l'evento viene registrato e la manica
  non e' decision-grade (fail-closed);
- breadth sotto ``min_breadth``: il mese resta in cassa e il ribilancio
  viene marcato insufficiente.

Lo stato del portafoglio vive interamente dentro ``run_sleeve``: ogni
finestra walk-forward parte da capitale iniziale e non eredita nulla,
quindi l'ordine di esecuzione delle finestre non puo' cambiare i
risultati.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd

from src.analysis.s3_poc.construction import inverse_vol_weights, select_top_decile
from src.analysis.s3_poc.dataset import PitDataset
from src.analysis.s3_poc.eligibility import eligible_at
from src.analysis.s3_poc.manifest import S3PocManifest
from src.analysis.s3_poc.signals import variant_signal
from src.backtest.costs.impact_model import SquareRootImpactModel

_DUST_SHARES = 1e-9  # sotto questa frazione di azione il trade e' rumore float


@dataclass(frozen=True)
class RebalanceRecord:
    """Un ribilancio eseguito: segnale, esecuzione, pesi, fill e costi."""

    signal_date: pd.Timestamp
    execution_date: pd.Timestamp
    eligible_count: int
    breadth_sufficient: bool
    selected: tuple[str, ...]
    weights: dict[str, float]
    fill_prices: dict[str, float]
    traded_notional_usd: float
    cost_usd: float
    skipped_execution: tuple[str, ...]


@dataclass(frozen=True)
class SleeveResult:
    """Risultato di una manica (variante) su un periodo."""

    variant: str
    start: pd.Timestamp
    end: pd.Timestamp
    nav: pd.Series
    returns: pd.Series
    rebalances: tuple[RebalanceRecord, ...]
    unresolved_delistings: tuple[dict, ...]
    cost_multiplier: float
    months_in_cash: int
    decision_grade: bool


@dataclass
class _Plan:
    """Piano calcolato alla seduta del segnale, consumato all'esecuzione."""

    eligible_count: int
    breadth_sufficient: bool
    selected: tuple[str, ...]
    weights: dict[str, float]


def _month_ends(period: pd.DatetimeIndex) -> list[pd.Timestamp]:
    s = period.to_series()
    return list(s.groupby([period.year, period.month]).last())


def _trade_cost_usd(
    delta_shares: float,
    fill_price: float,
    adv_usd: float,
    manifest: S3PocManifest,
    impact: SquareRootImpactModel,
    multiplier: float,
) -> float:
    """Costo di un ordine: componenti di RealisticCostModel, tarate dal
    manifest del POC. Il moltiplicatore di scenario scala ogni componente."""
    c = manifest.costs
    order_usd = abs(delta_shares) * fill_price
    bps = c.spread_bps / 2.0 + impact.impact_bps(order_usd, adv_usd)
    cost = order_usd * bps / 1e4
    cost += c.commission_per_share * abs(delta_shares)
    if delta_shares < 0:  # fee regolamentari solo sulle vendite
        cost += abs(delta_shares) * fill_price * c.sec_fee_per_share_sale
        cost += abs(delta_shares) * c.finra_taf_per_share_sale
    return cost * multiplier


def _adv_usd(ds: PitDataset, sec: str, as_of: pd.Timestamp) -> float:
    """ADV in dollari: 20 sedute trailing di close x volume fino al segnale."""
    dollar = ds.close[sec] * ds.volume[sec]
    return float(dollar.loc[:as_of].tail(20).mean())


def run_sleeve(
    ds: PitDataset,
    manifest: S3PocManifest,
    variant: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    cost_multiplier: float = 1.0,
) -> SleeveResult:
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    sessions = ds.sessions
    period = sessions[(sessions >= start) & (sessions <= end)]
    close_ffill = ds.close.ffill()
    impact = SquareRootImpactModel(k=manifest.costs.impact_k)

    delist = {
        row.security_id: row
        for row in ds.delistings.itertuples(index=False)
    }

    # calendario: segnale a fine mese, esecuzione alla prima seduta dopo,
    # solo se dentro il periodo (nessun fill oltre la finestra valutata)
    exec_of: dict[pd.Timestamp, pd.Timestamp] = {}
    for t in _month_ends(period):
        dopo = sessions[sessions > t]
        if len(dopo) == 0 or dopo[0] > end:
            continue
        exec_of[t] = dopo[0]
    signal_dates = set(exec_of)

    cash = manifest.portfolio.initial_capital_usd
    shares: dict[str, float] = {}
    nav_values: list[float] = []
    rebalances: list[RebalanceRecord] = []
    unresolved: list[dict] = []
    months_in_cash = 0
    pending: dict[pd.Timestamp, _Plan] = {}

    for d in period:
        # 1. piano al close del segnale (i fill arriveranno solo dopo)
        if d in signal_dates:
            elig = eligible_at(ds, manifest, d)
            if not elig.sufficient:
                pending[exec_of[d]] = _Plan(
                    eligible_count=len(elig.eligible), breadth_sufficient=False,
                    selected=(), weights={},
                )
            else:
                signals = variant_signal(ds, manifest, d, elig.eligible, variant)
                selected = tuple(select_top_decile(
                    signals,
                    n_deciles=manifest.portfolio.n_deciles,
                    long_decile=manifest.portfolio.long_decile,
                ))
                weights = inverse_vol_weights(ds, manifest, d, selected)
                pending[exec_of[d]] = _Plan(
                    eligible_count=len(elig.eligible), breadth_sufficient=True,
                    selected=selected, weights=weights,
                )

        # 2. esecuzione all'open (fallback close) della seduta successiva
        if d in pending:
            plan = pending.pop(d)
            signal_date = _signal_of(d, exec_of)
            fills: dict[str, float] = {}
            skipped: list[str] = []
            for sec in plan.weights:
                op = ds.open.loc[d, sec] if sec in ds.open.columns else float("nan")
                cl = ds.close.loc[d, sec] if sec in ds.close.columns else float("nan")
                reliable = (
                    bool(ds.open_reliable.loc[d, sec])
                    if sec in ds.open_reliable.columns else False
                )
                if reliable and pd.notna(op) and op > 0:
                    fills[sec] = float(op)
                elif pd.notna(cl) and cl > 0:
                    fills[sec] = float(cl)
                else:
                    skipped.append(sec)

            # NAV di esecuzione: posseduto marcato al fill (o ultimo close)
            nav_exec = cash + sum(
                q * fills.get(sec, close_ffill.loc[d, sec]) for sec, q in shares.items()
            )
            new_shares: dict[str, float] = {}
            cost_usd = 0.0
            notional = 0.0
            for sec in set(shares) | set(plan.weights):
                current = shares.get(sec, 0.0)
                if sec in skipped:
                    if current > 0:
                        new_shares[sec] = current
                    continue
                target = nav_exec * plan.weights.get(sec, 0.0)
                price = fills.get(sec, close_ffill.loc[d, sec])
                if not math.isfinite(price) or price <= 0:
                    if current > 0:
                        new_shares[sec] = current
                    continue
                wanted = target / price
                delta = wanted - current
                if abs(delta) > _DUST_SHARES:
                    cost_usd += _trade_cost_usd(
                        delta, price, _adv_usd(ds, sec, signal_date),
                        manifest, impact, cost_multiplier,
                    )
                    notional += abs(delta) * price
                new_shares[sec] = wanted
            held_value = sum(
                q * (fills.get(sec, close_ffill.loc[d, sec]) if q > 0 else 0.0)
                for sec, q in new_shares.items()
            )
            cash = nav_exec - held_value - cost_usd
            shares = {sec: q for sec, q in new_shares.items() if q > _DUST_SHARES}
            rebalances.append(RebalanceRecord(
                signal_date=signal_date,
                execution_date=d,
                eligible_count=plan.eligible_count,
                breadth_sufficient=plan.breadth_sufficient,
                selected=plan.selected,
                weights=dict(plan.weights),
                fill_prices=fills,
                traded_notional_usd=notional,
                cost_usd=cost_usd,
                skipped_execution=tuple(skipped),
            ))
            if not plan.breadth_sufficient:
                months_in_cash += 1

        # 3. delisting: rendimento economico esplicito sulla data stessa
        for sec in list(shares):
            row = delist.get(sec)
            if row is None or pd.Timestamp(row.delisting_date) != d:
                continue
            proceeds = shares[sec] * close_ffill.loc[d, sec]
            if bool(row.missing_status) or pd.isna(row.delisting_return):
                unresolved.append({
                    "security_id": sec,
                    "delisting_date": pd.Timestamp(row.delisting_date),
                    "missing_status": True,
                })
            else:
                proceeds *= 1.0 + float(row.delisting_return)
            cash += proceeds
            del shares[sec]

        # 4. mark to market
        nav_values.append(cash + sum(q * close_ffill.loc[d, sec] for sec, q in shares.items()))

    nav = pd.Series(nav_values, index=period, name="nav")
    returns = nav.pct_change().dropna()
    return SleeveResult(
        variant=variant,
        start=start,
        end=end,
        nav=nav,
        returns=returns,
        rebalances=tuple(rebalances),
        unresolved_delistings=tuple(unresolved),
        cost_multiplier=cost_multiplier,
        months_in_cash=months_in_cash,
        decision_grade=not unresolved,
    )


def _signal_of(execution_date: pd.Timestamp, exec_of: dict[pd.Timestamp, pd.Timestamp]) -> pd.Timestamp:
    for segnale, esecuzione in exec_of.items():
        if esecuzione == execution_date:
            return segnale
    raise ValueError(f"nessuna seduta segnale per l'esecuzione {execution_date}")


def _add_months(day: pd.Timestamp, months: int) -> pd.Timestamp:
    m = day.month - 1 + months
    year = day.year + m // 12
    month = m % 12 + 1
    return pd.Timestamp(year=year, month=month, day=1)


def _month_diff(start: pd.Timestamp, end: pd.Timestamp) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month) + 1


def walk_forward_windows(
    manifest: S3PocManifest,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Finestre OOS 60/12/12 dal manifest: la finestra k copre i mesi
    [IS + k*step, IS + k*step + OOS) del periodo. Solo finestre OOS
    complete: l'ultima mensilita' incompleta non si valuta."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    wf = manifest.walkforward
    n = _month_diff(start, end)
    windows = []
    k = 0
    while wf.in_sample_months + (k + 1) * wf.oos_months <= n:
        first = _add_months(start, wf.in_sample_months + k * wf.step_months)
        last_month = _add_months(
            start, wf.in_sample_months + k * wf.step_months + wf.oos_months - 1
        )
        last = last_month + pd.offsets.MonthEnd(0)
        windows.append((first, last))
        k += 1
    return windows


def run_walk_forward(
    ds: PitDataset,
    manifest: S3PocManifest,
    variant: str,
    period_start: pd.Timestamp,
    period_end: pd.Timestamp,
    cost_multiplier: float = 1.0,
) -> list[SleeveResult]:
    """Una manica per finestra OOS, stato fresco per costruzione."""
    return [
        run_sleeve(ds, manifest, variant, ws, we, cost_multiplier)
        for ws, we in walk_forward_windows(manifest, period_start, period_end)
    ]
