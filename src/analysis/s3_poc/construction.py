"""Costruzione del portafoglio della manica S3 nel POC (#84).

Top decile long-only (il bottom decile si esclude, non si shorta), sizing
inverse-vol su 60 sedute, normalizzazione alla manica, cap 10% per security
con ridistribuzione iterativa fra i non cappati. La cassa resta solo quando
l'allocazione piena e' matematicamente impossibile (N x cap < 1).
"""
from __future__ import annotations

import math

import pandas as pd

from src.analysis.s3_poc.dataset import PitDataset
from src.analysis.s3_poc.manifest import S3PocManifest


def select_top_decile(
    signals: dict[str, float], n_deciles: int, long_decile: int
) -> list[str]:
    """Decile = ceil(rank * n_deciles / N), rank crescente sul segnale.

    Stessa formula di src.strategies.s3.signal.compute_cross_sectional_ranks.
    """
    ordered = sorted(signals.items(), key=lambda kv: (kv[1], kv[0]))
    n = len(ordered)
    if n == 0:
        return []
    selected = [
        sec for rank, (sec, _) in enumerate(ordered, start=1)
        if math.ceil(rank * n_deciles / n) == long_decile
    ]
    return selected


def apply_iterative_cap(weights: dict[str, float], cap: float) -> dict[str, float]:
    """Cap iterativo con ridistribuzione proporzionale fra i non cappati.

    Water-filling: si scala la massa dei non cappati finche' la somma
    converge a min(S, N x cap), dove S e' la somma in ingresso (1 per la
    manica). Quando N x cap < S l'allocazione piena e' matematicamente
    impossibile: la somma resta sotto S e il residuo e' cassa.
    """
    if cap <= 0:
        raise ValueError("cap deve essere positivo")
    total = sum(weights.values())
    target = min(total, cap * len(weights))

    out: dict[str, float] = {}
    free = dict(weights)
    while free:
        free_total = sum(free.values())
        scale = (target - cap * len(out)) / free_total
        newly_capped = {s: w for s, w in free.items() if w * scale > cap + 1e-15}
        if not newly_capped:
            for s, w in free.items():
                out[s] = w * scale
            break
        for s in newly_capped:
            out[s] = cap
            del free[s]
    return out


def inverse_vol_weights(
    ds: PitDataset,
    manifest: S3PocManifest,
    as_of: pd.Timestamp,
    securities: tuple[str, ...],
) -> dict[str, float]:
    """Pesi 1/vol (60 sedute trailing), normalizzati, cap iterativo 10%."""
    as_of = pd.Timestamp(as_of)
    window = manifest.portfolio.vol_window_sessions
    idx = ds.close.index.get_indexer([as_of])[0]
    vol: dict[str, float] = {}
    for sec in securities:
        prices = ds.close[sec].iloc[idx - window : idx + 1].dropna()
        if len(prices) < window // 2:  # storia minima per stimare la vol
            continue
        ret = prices.pct_change().dropna()
        if len(ret) < 2 or ret.std() <= 0:
            continue
        vol[sec] = float(ret.std())

    if not vol:
        return {}
    raw = {s: 1.0 / v for s, v in vol.items()}
    total = sum(raw.values())
    normalized = {s: w / total for s, w in raw.items()}
    return apply_iterative_cap(normalized, cap=manifest.portfolio.max_weight)
